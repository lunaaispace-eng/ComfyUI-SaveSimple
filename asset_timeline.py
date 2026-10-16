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


def check_placements(shot: int, items: list) -> list:
    """Messages for every (label, at, length) that does not fit in a `shot`-frame
    shot. Empty = all fit. A clip must END inside the shot, not just start there."""
    errors = []
    for label, at, length in items:
        at, length = int(at), max(1, int(length))
        if at < 0 or at + length > shot:
            last = shot - length
            errors.append(
                f"{label} is placed at frame {at} and runs {length} frame(s), but the shot has "
                f"{shot} (frames 0-{shot - 1})"
                + (f"; it fits from frame 0 to {last}." if last >= 0 else "; it is longer than the shot.")
            )
    return errors


def shot_frames(seconds, stored: int) -> int:
    """The shot length in frames: the wired `seconds` when there is one, else the
    length stored on the node."""
    if seconds is not None and float(seconds) > 0:
        return int(round(float(seconds) * FPS))
    return max(1, int(stored))
