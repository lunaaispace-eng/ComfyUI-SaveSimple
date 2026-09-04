"""Video and audio decoding for the Luna Asset Loader's reference clips.

MiniMax H3's LOCAL reference node — `MiniMaxH3ReferenceToVideo` in ComfyUI's
`comfy_extras/nodes_minimax_h3.py` — is not the cloud API node of the same
display name. The difference decides everything in this file:

  * `ref_video_0..2` takes an **IMAGE frame batch**, not a VIDEO object. There
    is no lazy trim; frames have to be decoded here.
  * It hardcodes `FPS = 24` when it builds Qwen's timestamps
    (`sample_idx = range(0, n, FPS // 2)`, `timestamps = i / 2.0`). It never
    resamples. Hand it 30 fps footage raw and the model is told the wrong times
    and reads the motion at the wrong speed, silently. So resampling to 24 is
    not an option here, it is a correctness requirement.
  * It crops each clip DOWN to the model's grid (`while n % 17 != 5: n -= 1`)
    with a floor of 5 frames, so the only lengths that survive are 5, 22, 39 …
    362 — 0.21 s to 15.08 s.

Frames are decoded at a reduced size on purpose. `adapt_canvas()` in that same
core file scales every reference to a 768 short edge under a 768*1344 cap before
encoding, so decoding 1080p first only buys a bigger tensor: 362 frames of
1920x1080 float32 is ~9 GB, and the H3 pipeline already runs near the RAM
ceiling on this machine. Decoding straight to a 768 short edge costs ~1.2 GB for
the same clip and loses nothing the model would have kept.

`av` is imported at module level by core's `comfy_extras/nodes_video.py`, so it
is always present in a working ComfyUI; this adds no dependency.
"""

from __future__ import annotations

import os

import numpy as np
import torch

# H3's own numbers, read out of comfy_extras/nodes_minimax_h3.py rather than
# remembered — getting one wrong yields a clip subtly out of step, not an error.
FPS = 24
FRAME_STEP = 17
FRAME_PLUS = 5
TRAINED_MAX_FRAMES = 362          # ~15.08 s, the top of the trained range
REF_VIDEO_SHORT_EDGE = 768        # BASE_SHORT_EDGE; adapt_canvas lands here anyway

VIDEO_EXTS = {"mp4", "mov", "mkv", "webm", "avi", "m4v", "mpg", "mpeg", "wmv", "flv"}
AUDIO_EXTS = {"wav", "mp3", "flac", "ogg", "opus", "m4a", "aac", "wma", "aiff"}


def snap_frames_down(n: int) -> int:
    """Largest valid H3 clip length not exceeding `n`, or 0 if there is none.

    Used once the frames are in hand, where down is the only direction
    available: padding a reference clip would invent motion the source never
    had. 0 is returned rather than raising so the caller can name the file in
    the error.
    """
    n = int(n)
    if n < FRAME_PLUS:
        return 0
    while n % FRAME_STEP != FRAME_PLUS:
        n -= 1
    return n


def snap_frames_nearest(n: int) -> int:
    """The valid clip length closest to `n` — the target BEFORE decoding.

    Rounding down unconditionally is wrong when the request sits just under a
    grid point: 5 s is 120 frames, and the grid offers 107 (4.46 s) below and
    124 (5.17 s) above. Taking 107 throws away three quarters of a second of
    footage that was sitting right there, to honour a boundary the model does
    not have. Nearest costs at most half a grid step either way and lands on
    5.17 s for the request everyone actually makes.

    The frames still have to exist. When the source runs out first the caller
    falls back to `snap_frames_down` on what it got, so this can only ever ask —
    never invent.
    """
    n = max(FRAME_PLUS, int(n))
    lo = snap_frames_down(n) or FRAME_PLUS
    hi = lo if lo == n else lo + FRAME_STEP
    if hi > TRAINED_MAX_FRAMES:
        return min(lo, TRAINED_MAX_FRAMES)
    return hi if (n - lo) > (hi - n) else lo


def _target_size(width: int, height: int, short_edge: int) -> tuple[int, int]:
    """Scale down so the short edge is `short_edge`. Never upscales.

    Even dimensions only — several swscale paths assume it, and H3 rounds to a
    multiple of 32 afterwards regardless, so precision here buys nothing.
    """
    if short_edge <= 0 or min(width, height) <= short_edge:
        tw, th = width, height
    else:
        scale = short_edge / float(min(width, height))
        tw, th = int(round(width * scale)), int(round(height * scale))
    return max(2, tw - (tw % 2)), max(2, th - (th % 2))


def decode_video(path: str, start_s: float = 0.0, seconds: float = 0.0,
                 short_edge: int = REF_VIDEO_SHORT_EDGE):
    """One video file -> ([N, H, W, 3] float 0-1 at 24 fps, info dict).

    `start_s` is where the window opens, `seconds` how long it runs (0 = as much
    as H3 can take). The returned frame count is already snapped to H3's grid.

    Resampling is nearest-hold against a 24 fps timeline: a target time is
    advanced by 1/24 and the current source frame is emitted whenever it has
    reached it, so 30 fps drops frames and 12 fps duplicates them. That is what
    every loader in this ecosystem does (VHS `force_rate`, Pixaroma `force_fps`)
    and it keeps motion in real time, which is the only thing H3's timestamps
    care about.
    """
    import av  # core imports this at module level; never an optional dep here

    want = TRAINED_MAX_FRAMES
    if seconds and seconds > 0:
        want = min(want, snap_frames_nearest(int(round(float(seconds) * FPS))))

    frames: list[np.ndarray] = []
    with av.open(path) as container:
        if not container.streams.video:
            raise RuntimeError(
                f"[Luna Asset Loader] {os.path.basename(path)} has no video stream."
            )
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"

        src_w = int(stream.codec_context.width or 0)
        src_h = int(stream.codec_context.height or 0)
        if not src_w or not src_h:
            raise RuntimeError(
                f"[Luna Asset Loader] Could not read the frame size of "
                f"{os.path.basename(path)}."
            )
        tw, th = _target_size(src_w, src_h, short_edge)
        src_fps = float(stream.average_rate) if stream.average_rate else float(FPS)

        start_s = max(0.0, float(start_s or 0.0))
        if start_s > 0 and stream.time_base:
            # Seek is keyframe-accurate, so it lands at or before the request;
            # the time filter below does the exact trim.
            try:
                container.seek(int(start_s / stream.time_base), stream=stream)
            except Exception:
                # A stream without a seek index still decodes from the top, just
                # slower. Better than refusing the file.
                pass

        next_t = start_s
        step = 1.0 / FPS
        for frame in container.decode(stream):
            t = float(frame.pts * stream.time_base) if frame.pts is not None else next_t
            if t + 1e-9 < start_s:
                continue
            if t + 1e-9 < next_t:
                continue
            rgb = frame.reformat(width=tw, height=th, format="rgb24").to_ndarray()
            # A source slower than 24 fps holds one frame over several targets.
            while next_t <= t + 1e-9 and len(frames) < want:
                frames.append(rgb)
                next_t += step
            if len(frames) >= want:
                break

    if not frames:
        raise RuntimeError(
            f"[Luna Asset Loader] No frames decoded from {os.path.basename(path)} "
            f"at start {start_s:.2f}s. The start point may be past the end of the clip."
        )

    n = snap_frames_down(len(frames))
    if n == 0:
        raise RuntimeError(
            f"[Luna Asset Loader] {os.path.basename(path)} gave only {len(frames)} "
            f"frame(s) at 24 fps; MiniMax H3 needs at least {FRAME_PLUS} "
            f"(~0.21 s). Widen the window or pick a longer clip."
        )
    dropped = len(frames) - n
    frames = frames[:n]

    arr = np.stack(frames).astype(np.float32) / 255.0
    return torch.from_numpy(arr), {
        "frames": n,
        "seconds": n / FPS,
        "width": tw,
        "height": th,
        "source_size": (src_w, src_h),
        "source_fps": src_fps,
        "start": start_s,
        "snapped_off": dropped,
        "name": os.path.basename(path),
    }


def _decode_audio(path: str):
    """(waveform [C, L], sample_rate). Core's loader first, torchaudio as backup.

    Core's `comfy_extras.nodes_audio.load` is a private helper and exactly the
    kind of thing that gets renamed, so any failure — not just ImportError —
    falls through, since an optional dependency that imports fine can still fail
    at call time.
    """
    try:
        from comfy_extras.nodes_audio import load as _core_load
        return _core_load(path)
    except Exception:
        import torchaudio
        return torchaudio.load(path)


def load_audio(path: str, start_s: float = 0.0, seconds: float = 0.0):
    """One audio file -> ({"waveform": [1, C, L], "sample_rate": sr}, info dict).

    Trimming is plain sample slicing, the same arithmetic core's
    `TrimAudioDuration` uses. It never pads: a window that runs off the end is
    simply shorter, and the info dict says so, because inventing silence at the
    tail of a REFERENCE would teach the model that the clip ends quiet.
    """
    waveform, sample_rate = _decode_audio(path)
    if waveform.ndim == 1:
        waveform = waveform.unsqueeze(0)          # [L] -> [1, L]
    total = int(waveform.shape[-1])
    sr = int(sample_rate or 1)

    start = max(0, min(total, int(round(max(0.0, float(start_s or 0.0)) * sr))))
    if seconds and seconds > 0:
        end = min(total, start + int(round(float(seconds) * sr)))
    else:
        end = total
    if start >= end:
        raise RuntimeError(
            f"[Luna Asset Loader] The window on {os.path.basename(path)} contains no "
            f"audio: it starts at {start / sr:.2f}s but the file is only "
            f"{total / sr:.2f}s long."
        )

    clip = waveform[..., start:end]
    asked = float(seconds) if seconds and seconds > 0 else (end - start) / sr
    return {"waveform": clip.unsqueeze(0), "sample_rate": sr}, {
        "seconds": (end - start) / sr,
        "asked": asked,
        "short": (end - start) / sr + 1e-3 < asked,
        "sample_rate": sr,
        "channels": int(clip.shape[0]),
        "start": start / sr,
        "name": os.path.basename(path),
    }
