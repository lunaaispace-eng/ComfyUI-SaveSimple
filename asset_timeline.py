"""Shot timeline rules for the Luna Asset Loader. Pure Python, no ComfyUI imports.

Every asset on the node has a role. A REFERENCE is something MiniMax H3 is shown
and named in the prompt (<Picture n>, <Video n>, <Audio n>) with no particular
time. An asset ON THE SHOT is anchored at a frame of the video being generated
(a keyframe picture, a guide clip, a guide or locked sound).

The catch these rules exist for: H3 numbers ONLY the references, in order. Put
picture 1 on the shot as a keyframe and the picture on card 2 becomes <Picture 1>
in the prompt. The card UI and asset_brief both say which tag each card really has.

Sound numbering follows MiniMax H3's own presentation order (nodes_minimax_h3.py):
each reference clip's kept soundtrack is the <Audio j> right before its <Video k>,
and standalone reference sounds come after every clip.
"""

from __future__ import annotations

FPS = 24


def h3_tags(pic_roles: list, clips: list, sound_roles: list) -> dict:
    """Card index -> H3 tag, for the cards that are references.

    pic_roles: "ref" | "key" per picture card. clips: {"role": "ref"|"guide",
    "sound": bool (a kept soundtrack exists)} per video card. sound_roles:
    "ref" | "lock" | "guide" per sound card."""
    pictures, videos, video_audio, sounds = {}, {}, {}, {}
    for i, role in enumerate(pic_roles):
        if role == "ref":
            pictures[i] = f"<Picture {len(pictures) + 1}>"
    audio_no = 0
    for i, c in enumerate(clips):
        if c.get("role") != "ref":
            continue
        if c.get("sound"):
            audio_no += 1
            video_audio[i] = f"<Audio {audio_no}>"
        videos[i] = f"<Video {len(videos) + 1}>"
    for i, role in enumerate(sound_roles):
        if role == "ref":
            audio_no += 1
            sounds[i] = f"<Audio {audio_no}>"
    return {"pictures": pictures, "videos": videos, "video_audio": video_audio, "sounds": sounds}


def target_fps(target: str, source_fps: float) -> float:
    """The frame rate 'Target' means: MiniMax H3 hardcodes 24, LTX's conditioning
    defaults to 25 (comfy_extras/nodes_lt.py LTXVConditioning), General keeps the
    source's own rate."""
    return {"h3": 24.0, "ltx": 25.0}.get(target, float(source_fps or 24.0))


def target_grid(target: str) -> str:
    """The clip-length grid 'Target' means: H3 17k+5, LTX 8k+1, General none."""
    return {"h3": "h3", "ltx": "ltx"}.get(target, "free")


def check_placements(shot: int, items: list, target: str = "h3") -> list:
    """Messages for every (label, at, length) that does not fit in a `shot`-frame
    shot. Empty = all fit. A clip must END inside the shot, not just start there.
    LTX also anchors a multi-frame guide only at frame 0 or 8k+1 (LTXVAddGuide
    rounds anything else, silently moving it)."""
    errors = []
    for label, at, length in items:
        at, length = int(at), max(1, int(length))
        if target == "ltx" and length > 1 and at != 0 and (at - 1) % 8:
            lo = ((at - 1) // 8) * 8 + 1
            errors.append(f"{label} starts at frame {at}, but LTX anchors a clip only at frame 0 or 8k+1; "
                          f"the nearest are {lo} or {lo + 8}.")
            continue
        if at < 0 or at + length > shot:
            last = shot - length
            errors.append(
                f"{label} is placed at frame {at} and runs {length} frame(s), but the shot has "
                f"{shot} (frames 0-{shot - 1})"
                + (f"; it fits from frame 0 to {last}." if last >= 0 else "; it is longer than the shot.")
            )
    return errors


def normalize_sound_role(role, index: int) -> str:
    """Only sound 1 (the song) can be locked to the shot — the shot has one sound
    track. A later sound asked to lock becomes a guide; missing roles default to
    lock for the song and reference for the rest."""
    if role == "lock":
        return "lock" if index == 0 else "guide"
    if role in ("guide", "ref"):
        return role
    return "lock" if index == 0 else "ref"


def thinning_error(count: str, nth: int) -> str:
    """Every Nth frame on the MiniMax H3 grid would hand H3 a clip it plays at the
    wrong speed (it assumes 24 fps) with a soundtrack of the original length."""
    if count == "target" and int(nth) > 1:
        return ("Every Nth frame makes MiniMax H3 play the clip faster (it assumes 24 fps), and its "
                "sound no longer matches. Keep every frame, or set Frames to Free.")
    return ""


VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")


def newest_video(files: list):
    """[(name, mtime), ...] -> the most recently written video's name, or None.
    How the continuation finds the shot that was just saved."""
    vids = [(name, mtime) for name, mtime in files if str(name).lower().endswith(VIDEO_EXTS)]
    return max(vids, key=lambda f: f[1])[0] if vids else None


def tail_start(duration_s: float, fps: float, frames: int, source_fps: float | None = None) -> float:
    """Where to start so `frames` frames at `fps` END on the clip's very last frame.

    The last source frame sits one source frame before the end, and the last of
    the output frames is (frames - 1) output frames after the start. Ending
    anywhere else would cut away from an image the previous shot never ended on."""
    last = float(duration_s) - 1.0 / float(source_fps or fps)
    return max(0.0, last - (int(frames) - 1) / float(fps))


def shot_frames(seconds, stored: int) -> int:
    """The shot length in frames: the wired `seconds` when there is one, else the
    length stored on the node."""
    if seconds is not None and float(seconds) > 0:
        return int(round(float(seconds) * FPS))
    return max(1, int(stored))
