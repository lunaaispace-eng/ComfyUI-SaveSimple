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

import math
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


# --- the video card ------------------------------------------------------------
# A clip is chosen by start (seconds) and length (frames at the OUTPUT rate), then
# resampled, sized and thinned as the card says. Kept pure where possible so the
# rules can be tested without a video file.

def grid_frames(n: int, grid: str) -> int:
    """Nearest frame count the target accepts: free, H3 (17k+5) or LTX (8k+1)."""
    n = max(1, int(n))
    if grid == "h3":
        return snap_frames_nearest(n)
    if grid == "ltx":
        return max(1, int(round((n - 1) / 8.0)) * 8 + 1)
    return n


def pick_frames(src_times: list, out_fps: float, start_s: float, count: int) -> list:
    """Source frame index for each output frame: the latest source frame at or
    before each output time (sample and hold), so 30 -> 24 fps drops frames,
    12 -> 24 holds them, and motion stays in real time. Stops where the source
    ends instead of holding the last frame forever."""
    if not src_times or count <= 0 or out_fps <= 0:
        return []
    gaps = sorted(b - a for a, b in zip(src_times, src_times[1:]) if b > a)
    dt = gaps[len(gaps) // 2] if gaps else 1.0 / out_fps
    end = src_times[-1] + dt
    out, j = [], -1
    for k in range(int(count)):
        target = float(start_s) + k / float(out_fps)
        if target >= end - 1e-9:
            break
        while j + 1 < len(src_times) and src_times[j + 1] <= target + 1e-9:
            j += 1
        out.append(max(j, 0))
    return out


class FramePicker:
    """pick_frames, one source frame at a time, so the decoder keeps only the
    frames it will deliver. feed(t, id) returns the ids picked so far (every
    nth output frame); finish() resolves what is left once the source ends."""

    def __init__(self, out_fps: float, start_s: float, count: int, nth: int = 1):
        self.fps, self.start, self.count, self.nth = float(out_fps), float(start_s), int(count), max(1, int(nth))
        self.k, self.prev, self.prev_t, self.gaps = 0, None, None, []

    @property
    def done(self) -> bool:
        return self.k >= self.count

    def _target(self) -> float:
        return self.start + self.k / self.fps

    def _emit(self, ident, out: list):
        if self.k % self.nth == 0:
            out.append(ident)
        self.k += 1

    def feed(self, t: float, ident) -> list:
        out = []
        # every target strictly before this frame is held by the previous frame
        while not self.done and self._target() + 1e-9 < t:
            self._emit(self.prev if self.prev is not None else ident, out)
        if self.prev_t is not None and t > self.prev_t:
            self.gaps.append(t - self.prev_t)
        self.prev, self.prev_t = ident, t
        return out

    def finish(self) -> list:
        out = []
        if self.prev is None:
            return out
        gaps = sorted(self.gaps)
        dt = gaps[len(gaps) // 2] if gaps else 1.0 / self.fps
        end = self.prev_t + dt
        while not self.done and self._target() < end - 1e-9:
            self._emit(self.prev, out)
        return out


def strip_annotation(name: str) -> tuple:
    """'song.mp3 [input]' -> ('song.mp3', 'input'). Only a trailing ComfyUI folder
    tag is removed, so a real name like 'clip [v2].mp4' survives intact."""
    for tag in ("input", "output", "temp"):
        suffix = f" [{tag}]"
        if name.endswith(suffix):
            return name[: -len(suffix)], tag
    return name, None


def fit_box(src_w: int, src_h: int, tw: int, th: int, fit: str) -> tuple:
    """(scaled_w, scaled_h, x, y). crop: cover the box, (x, y) = where to cut from;
    pad: fit inside, (x, y) = where to paste into the box; stretch: the box itself."""
    if fit == "stretch":
        return int(tw), int(th), 0, 0
    s = (max if fit == "crop" else min)(tw / float(src_w), th / float(src_h))
    w, h = int(round(src_w * s)), int(round(src_h * s))
    if fit == "crop":
        return w, h, (w - tw) // 2, (h - th) // 2
    return w, h, (tw - w) // 2, (th - h) // 2


def clip_bytes(frames: int, width: int, height: int, precision: str = "fp16") -> int:
    """What the frames cost as an IMAGE tensor, RGB."""
    return int(frames) * int(width) * int(height) * 3 * (2 if precision == "fp16" else 4)


# --- Luna Load Video -----------------------------------------------------------
# Where the videos come from: a picked/uploaded file, a typed path or web link, or
# a folder. These helpers are pure so the rules are tested without disk or network.

def is_url(text: str) -> bool:
    return isinstance(text, str) and text.strip().lower().startswith(("http://", "https://"))


def clean_path(text: str) -> str:
    """A pasted path as Windows hands it over: quotes and spaces off the ends."""
    return (text or "").strip().strip('"').strip("'").strip()


def _natural(name: str):
    """'clip2' before 'clip10': digit runs compare as numbers."""
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def folder_videos(names, count: int = 0) -> list:
    """The video files among `names`, in natural name order, the first `count` (0 = all)."""
    vids = sorted((n for n in names if n.rsplit(".", 1)[-1].lower() in VIDEO_EXTS and "." in n), key=_natural)
    return vids[:count] if int(count or 0) > 0 else vids


def download_name(url: str) -> str:
    """A stable, safe file name for a downloaded link: its own name plus a short hash
    of the whole URL, so two links with the same file name never overwrite each other
    and the same link is downloaded once."""
    import hashlib
    import re
    from urllib.parse import unquote, urlparse
    path = unquote(urlparse(url.strip()).path)
    base = os.path.basename(path) or "video"
    stem, dot, ext = base.rpartition(".")
    if not dot or ext.lower() not in VIDEO_EXTS:
        stem, ext = base, "mp4"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")[:60] or "video"
    tag = hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:10]
    return f"{stem}_{tag}.{ext.lower()}"

# What a load will give, worked out from the file's probe BEFORE decoding, so the
# node face can show it and the run can refuse an oversized clip up front.

def grid_count(n: int, grid: str, available: int) -> int:
    """Frame count on the grid: nearest to `n`, never past `available`, 0 if none fits.
    Unlike grid_frames there is no 362 cap — a loader may hand H3 more than it was
    trained on; the node says so instead of cutting silently."""
    n, available = max(1, int(n)), int(available)
    if grid == "h3":
        lo = snap_frames_down(n) or FRAME_PLUS
        hi = lo if lo == n else lo + FRAME_STEP
        pick = hi if (n - lo) > (hi - n) else lo
        return pick if pick <= available else snap_frames_down(available)
    if grid == "ltx":
        pick = max(1, int(round((n - 1) / 8.0)) * 8 + 1)
        return pick if pick <= available else (((available - 1) // 8) * 8 + 1 if available >= 1 else 0)
    return min(n, available)


def plan_load(src: dict, start_s: float = 0.0, frames: int = 0, fps: float = 0.0,
              width: int = 0, height: int = 0, fit: str = "crop", grid: str = "free",
              nth: int = 1, precision: str = "fp32") -> dict:
    """The load, decided from `src` (probe_media's dict). Raises ValueError with a
    plain reason when nothing sensible can be loaded.

    frames 0 = to the end of the file. fps 0 = the source's rate. width/height 0 =
    keep; one of them set = scale to it, keeping the shape; both = fit that box.
    grid "h3" plays at 24 fps and cuts to 17k+5, "ltx" to 8k+1."""
    sw, sh = int(src.get("width") or 0), int(src.get("height") or 0)
    if not sw or not sh:
        raise ValueError("the frame size could not be read")
    src_fps = float(src.get("fps") or 0.0) or float(FPS)
    duration = float(src.get("duration") or 0.0)
    start_s = max(0.0, float(start_s or 0.0))
    fps = float(fps or 0.0)
    if grid == "h3":
        if fps not in (0.0, float(FPS)):
            raise ValueError(f"the H3 grid plays at {FPS} fps; set fps to 0 or {FPS}")
        fps = float(FPS)
    out_fps = fps or src_fps
    if duration and start_s >= duration:
        raise ValueError(f"start {start_s:.2f} s is at or past the end of the file ({duration:.2f} s)")
    available = int(math.floor((duration - start_s) * out_fps + 1e-6)) if duration else int(frames or 0)
    if available <= 0:
        raise ValueError("the file's length could not be read; set frames")
    asked = int(frames or 0)
    n = min(asked, available) if asked > 0 else available
    if grid in ("h3", "ltx"):
        n = grid_count(n, grid, available)
        if n <= 0:
            need = FRAME_PLUS if grid == "h3" else 1
            raise ValueError(f"only {available} frame(s) from {start_s:.2f} s; the grid needs at least {need}")

    w, h = int(width or 0), int(height or 0)
    if w > 0 and h > 0:
        size, ow, oh = ("box", w, h), w, h
    elif w > 0:
        oh = max(2, int(round(sh * w / float(sw))) // 2 * 2)
        size, ow, fit = ("box", w, oh), w, "stretch"
    elif h > 0:
        ow = max(2, int(round(sw * h / float(sh))) // 2 * 2)
        size, oh, fit = ("box", ow, h), h, "stretch"
    else:
        size, ow, oh = ("source",), sw, sh

    nth = max(1, int(nth or 1))
    delivered = -(-n // nth)
    notes = []
    if asked > available:
        notes.append(f"asked {asked} frames, the file has {available} from {start_s:.2f} s")
    elif asked > 0 and n != asked:
        notes.append(f"asked {asked} frames, the grid gives {n}")
    if grid == "h3" and n > TRAINED_MAX_FRAMES:
        notes.append(f"{n} frames is past H3's trained {TRAINED_MAX_FRAMES}")
    return {
        "frames": n, "delivered": delivered, "fps": out_fps, "out_fps": out_fps / nth,
        "seconds": n / out_fps, "size": size, "fit": fit, "width": ow, "height": oh,
        "bytes": clip_bytes(delivered, ow, oh, precision), "available": available,
        "source": {"width": sw, "height": sh, "fps": src_fps, "duration": duration,
                   "audio": bool(src.get("audio"))},
        "notes": notes,
    }


def probe_media(path: str) -> dict:
    """What a file holds, for the card UI: video size/fps/length, sound or not."""
    import av
    out = {"name": os.path.basename(path), "video": False, "audio": False}
    with av.open(path) as c:
        if c.duration:
            out["duration"] = c.duration / 1_000_000.0
        if c.streams.video:
            v = c.streams.video[0]
            fps = float(v.average_rate) if v.average_rate else 0.0
            dur = float(v.duration * v.time_base) if v.duration and v.time_base else out.get("duration", 0.0)
            out.update(video=True, width=int(v.codec_context.width or 0), height=int(v.codec_context.height or 0),
                       fps=fps, duration=dur, frames=int(v.frames or round(dur * fps)))
        if c.streams.audio:
            a = c.streams.audio[0]
            out.update(audio=True, sample_rate=int(a.rate or 0), channels=int(a.channels or 0))
    return out


def decode_clip(path: str, start_s: float, frames: int, out_fps: float | None = None,
                size: tuple = ("source",), fit: str = "crop", nth: int = 1,
                precision: str = "fp16", grid: str = "free", who: str = "Luna Asset Loader"):
    """One video window -> ([N, H, W, 3] float, info).

    start_s: where the clip opens in the source. frames: how many output frames,
    counted at out_fps (None = the source's own rate). size: ("source",),
    ("edge", short_edge) or ("box", w, h) with `fit` crop | pad | stretch.
    nth > 1 keeps every nth output frame. When the source runs out first, the
    clip is cut DOWN to the grid's last valid length — never padded."""
    import av

    nth = max(1, int(nth))
    with av.open(path) as container:
        if not container.streams.video:
            raise RuntimeError(f"[{who}] {os.path.basename(path)} has no video stream.")
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        sw, sh = int(stream.codec_context.width or 0), int(stream.codec_context.height or 0)
        if not sw or not sh:
            raise RuntimeError(f"[{who}] Could not read the frame size of {os.path.basename(path)}.")
        src_fps = float(stream.average_rate) if stream.average_rate else float(FPS)
        fps = float(out_fps) if out_fps else src_fps

        if size[0] == "box":
            tw, th = int(size[1]), int(size[2])
            scw, sch, ox, oy = fit_box(sw, sh, tw, th, fit)
        elif size[0] == "edge":
            tw, th = _target_size(sw, sh, int(size[1]))
            scw, sch, ox, oy = tw, th, 0, 0
        else:
            tw, th, scw, sch, ox, oy = sw, sh, sw, sh, 0, 0

        start_s = max(0.0, float(start_s or 0.0))
        stop_s = start_s + int(frames) / fps + 2.0 / src_fps
        if start_s > 0 and stream.time_base:
            try:   # keyframe-accurate; the time test below trims exactly
                container.seek(int(start_s / stream.time_base), stream=stream)
            except Exception:
                pass
        # Only what is delivered is kept: the output tensor is allocated once and
        # filled frame by frame, and a source frame is held only while it may still
        # be picked (the review of 2026-10-16 measured ~20 GB peak for a 4K clip the
        # old keep-everything-then-stack path let through a 6 GB cap).
        dtype = torch.float16 if precision == "fp16" else torch.float32
        out = torch.empty((-(-int(frames) // nth), th, tw, 3), dtype=dtype)
        picker = FramePicker(fps, start_s, int(frames), nth)
        n_out, held, held_id, last_t = 0, None, -1, None

        def to_img(frame):
            img = frame.reformat(width=scw, height=sch, format="rgb24").to_ndarray()
            if fit == "crop" and size[0] == "box":
                return img[oy:oy + th, ox:ox + tw]
            if fit == "pad" and size[0] == "box":
                box = np.zeros((th, tw, 3), dtype=np.uint8)
                box[oy:oy + sch, ox:ox + scw] = img
                return box
            return img

        def put(img):
            nonlocal n_out
            out[n_out].copy_(torch.from_numpy(np.ascontiguousarray(img))).div_(255.0)
            n_out += 1

        fid = 0
        for frame in container.decode(stream):
            t = float(frame.pts * stream.time_base) if frame.pts is not None else (last_t + 1 / src_fps if last_t is not None else 0.0)
            last_t = t
            if t + 1.0 / src_fps < start_s:
                continue
            if t > stop_s or picker.done:
                break
            img = to_img(frame)
            for ident in picker.feed(t, fid):
                put(held if ident == held_id else img)
            held, held_id = img, fid
            fid += 1
        for ident in picker.finish():
            put(held)
        targets = picker.k   # output frames resolved before thinning

    if n_out == 0:
        raise RuntimeError(
            f"[{who}] No frames in {os.path.basename(path)} from {start_s:.2f}s — "
            f"the start may be past the end of the clip.")
    got = targets
    if got < int(frames) and grid != "free":
        keep = snap_frames_down(got) if grid == "h3" else max(1, ((got - 1) // 8) * 8 + 1)
        if keep == 0:
            raise RuntimeError(
                f"[{who}] {os.path.basename(path)} gave only {got} frame(s) from "
                f"{start_s:.2f}s; MiniMax H3 needs at least {FRAME_PLUS}.")
        targets = keep
        n_out = min(n_out, -(-keep // nth))
    t = out[:n_out]
    return t, {
        "name": os.path.basename(path), "frames": n_out, "asked": int(frames),
        "short": got < int(frames), "seconds": targets / fps, "fps": fps / nth, "source_fps": src_fps,
        "width": tw, "height": th, "source_size": (sw, sh), "start": start_s, "nth": nth,
    }


def clip_soundtrack(path: str, start_s: float, seconds: float):
    """The clip's own sound for exactly its window, or None when the file has none."""
    import av
    with av.open(path) as c:
        if not c.streams.audio:
            return None
    waveform, sr = _decode_audio(path)
    if waveform.ndim == 1:
        waveform = waveform.unsqueeze(0)
    plan = plan_window(int(waveform.shape[-1]), int(sr), start_s, seconds)
    if plan["take"] <= 0:
        return None
    # Cut, never filled: a reference's sound ends where its picture ends.
    plan = {**plan, "want": plan["take"], "fill": 0}
    return {"waveform": apply_window(waveform, plan).unsqueeze(0), "sample_rate": int(sr)}


def filmstrip_jpeg(path: str, count: int = 12, height: int = 72) -> bytes:
    """`count` evenly spaced frames side by side, for the card UI's film strip."""
    import io

    import av
    from PIL import Image

    count = max(1, min(48, int(count)))
    tiles = []
    with av.open(path) as c:
        v = c.streams.video[0]
        dur = (v.duration * v.time_base) if v.duration and v.time_base else (c.duration or 0) / 1_000_000.0
        dur = float(dur or 0.0)
        w = int(round((v.codec_context.width or 16) * height / float(v.codec_context.height or 9)))
        w = max(8, min(w, 4 * height))   # an extreme aspect must not build a giant strip
        for k in range(count):
            t = dur * (k + 0.5) / count
            try:
                c.seek(int(t / v.time_base), stream=v)
                frame = next(c.decode(v))
                tiles.append(frame.to_image().resize((w, height)))
            except Exception:
                tiles.append(Image.new("RGB", (w, height), (20, 21, 26)))
    strip = Image.new("RGB", (w * len(tiles), height))
    for i, im in enumerate(tiles):
        strip.paste(im, (i * w, 0))
    buf = io.BytesIO()
    strip.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


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


# --- the song window -----------------------------------------------------------
# A reference sound is cut and never padded (load_audio below). A SONG that drives
# a shot is different: its window must be exactly as long as the shot, so a window
# that runs off the end is filled the way the user chose — silence or the file
# again from its start — and the node says it happened. The window idea and the
# silence/loop choice follow ComfyUI-Pixaroma's Load Audio (MIT, (c) 2026 pixaroma,
# nodes/_audio_window_helpers.py); this implementation is the pack's own.

def plan_window(total: int, sample_rate: int, start_s: float, want_s: float) -> dict:
    """Samples to skip, want, take from the file and fill. want_s <= 0 = to the end."""
    sr = int(sample_rate or 1)
    start = max(0, min(int(total), int(round(max(0.0, float(start_s or 0.0)) * sr))))
    want = int(round(float(want_s) * sr)) if want_s and want_s > 0 else int(total) - start
    take = max(0, min(want, int(total) - start))
    return {"start": start, "want": want, "take": take, "fill": want - take}


def apply_window(waveform: torch.Tensor, plan: dict, when_short: str = "silence") -> torch.Tensor:
    """[C, L] -> [C, plan['want']]. The tail is zeros, or the file repeated from 0."""
    start, take, fill = plan["start"], plan["take"], plan["fill"]
    parts = [waveform[:, start:start + take]]
    if fill > 0:
        if when_short == "loop" and waveform.shape[-1] > 0:
            reps = -(-fill // waveform.shape[-1])          # ceil
            parts.append(waveform.repeat(1, reps)[:, :fill])
        else:
            parts.append(waveform.new_zeros(waveform.shape[0], fill))
    return torch.cat(parts, dim=-1)


# --- a song cut into shots ---------------------------------------------------------
# A music video is many shots of one song. Shot n starts where shot n-1 started plus
# the shot length minus the overlap, so neighbouring shots share `overlap` frames of
# song — the same frames the continuation carries over in the picture, so sound and
# picture line up at every cut. Overlap is counted in frames at H3's 24 fps.

def _shot_step(shot_s: float, overlap_frames: int, fps: int = FPS) -> float:
    step = float(shot_s) - int(overlap_frames) / float(fps)
    if step <= 0:
        raise ValueError(
            f"The overlap ({int(overlap_frames)} frames = {int(overlap_frames) / fps:.2f} s) is as "
            f"long as the shot ({float(shot_s):.2f} s), so the song would never move on.")
    return step


def song_shot_start(song_start_s: float, shot: int, shot_s: float, overlap_frames: int,
                    fps: int = FPS) -> float:
    """Where in the song shot `shot` (1-based) begins."""
    return float(song_start_s) + (max(1, int(shot)) - 1) * _shot_step(shot_s, overlap_frames, fps)


def song_shot_count(total_s: float, song_start_s: float, shot_s: float, overlap_frames: int,
                    fps: int = FPS) -> int:
    """How many shots start inside the song. The last may run past the end and be filled."""
    if float(song_start_s) >= float(total_s):
        return 0
    return int(math.ceil((float(total_s) - float(song_start_s)) / _shot_step(shot_s, overlap_frames, fps)))


def load_audio_window(path: str, start_s: float, seconds: float, when_short: str = "silence",
                      describe_empty=None):
    """One sound file -> ({"waveform": [1, C, L], "sample_rate": sr}, info), exactly `seconds` long.

    `describe_empty(total_s)` words the error when the window starts past the end —
    a caller that knows WHY (a shot number past the song) can say so."""
    waveform, sample_rate = _decode_audio(path)
    if waveform.ndim == 1:
        waveform = waveform.unsqueeze(0)
    sr = int(sample_rate or 1)
    plan = plan_window(int(waveform.shape[-1]), sr, start_s, seconds)
    if plan["take"] <= 0:
        total_s = waveform.shape[-1] / sr
        raise RuntimeError(describe_empty(total_s) if describe_empty else (
            f"[Luna Asset Loader] The window on {os.path.basename(path)} contains no audio: "
            f"it starts at {plan['start'] / sr:.2f}s but the file is only "
            f"{total_s:.2f}s long. Drag the window back into the song."
        ))
    info_total = waveform.shape[-1] / sr
    clip = apply_window(waveform, plan, when_short)
    return {"waveform": clip.unsqueeze(0), "sample_rate": sr}, {
        "name": os.path.basename(path),
        "start": plan["start"] / sr,
        "seconds": plan["want"] / sr,
        "taken": plan["take"] / sr,
        "filled": plan["fill"] / sr,
        "mode": "loop" if when_short == "loop" else "silence",
        "sample_rate": sr,
        "channels": int(clip.shape[0]),
        "total": info_total,
    }


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
