"""Luna H3 Reference Loader — every MiniMax H3 reference, picked from dropdowns.

The full-fat sibling of Luna Asset Loader. That node stays exactly as it is: nine
ordered images, a card UI, per-image resize. This one covers all four of H3's
reference families — pictures, clips, clip soundtracks, standalone audio — and
hands them over as a single `refs` link that Luna H3 Refs Out fans back into the
model's own sockets.

Each slot is a dropdown with an upload button, the same widget Load Image and
Load Video use (`image_upload` / `video_upload` / `audio_upload` — the legacy
keys that `comfy_api.latest.io.UploadType` maps onto). No filenames are typed.

Five outputs, not twenty-three, and that is the point of the split. ComfyUI maps
outputs to the returned tuple by index and type-checks links against a fixed
`RETURN_TYPES`, so a node whose visible sockets grow and shrink can only shrink
from the END. Mixing IMAGE and AUDIO families into one growable run cannot work:
at three images shown, the slot that used to be `image_4` would have to carry an
AUDIO while still declared IMAGE, and the backend rejects it. Carrying everything
in one `refs` link sidesteps the whole problem — the fan-out node has fixed
sockets because it has no counts to follow.

WHAT H3 ACTUALLY TAKES, read out of `comfy_extras/nodes_minimax_h3.py`:

  ref_image_0..8        IMAGE, one frame. Sized by the model (`ref_image_size`).
  ref_video_0..2        IMAGE **frame batch**, not a VIDEO object.
  ref_video_audio_0..2  AUDIO, paired to ref_video_N by socket-name suffix.
  ref_audio_0..2        AUDIO, standalone.

Note that is the LOCAL node. The cloud API node in `comfy_api_nodes/nodes_minimax.py`
shares its display name, takes VIDEO objects, and has only three families — an
easy and expensive confusion. The giveaway is `audio_vae`, which API nodes lack.

Prompt tags are 1-based per type (`<Picture 1>`, `<Video 1>`, `<Audio 1>`) while
the sockets are 0-based (`ref_image_0`). That mismatch is H3's own; `asset_brief`
states the mapping so nothing downstream has to guess it.
"""

from __future__ import annotations

import hashlib
import os

import folder_paths

from .asset_loader import _conform, _describe_ar, _load
from .media_io import FPS, decode_video, load_audio

MAX_IMAGES = 9
MAX_VIDEOS = 3
MAX_AUDIOS = 3

NONE = "(none)"


def _input_files(kinds: list[str]) -> list[str]:
    """Files of the given content types in ComfyUI's input folder, `(none)` first.

    `(none)` rather than an empty string: a blank entry in a dropdown reads as a
    rendering fault, and an unset slot is a normal state here — most graphs use
    two or three references, not fifteen.
    """
    input_dir = folder_paths.get_input_directory()
    os.makedirs(input_dir, exist_ok=True)
    try:
        files = folder_paths.filter_files_content_types(os.listdir(input_dir), kinds)
    except Exception:
        files = []
    return [NONE] + sorted(files)


def _picked(value) -> str:
    return "" if not value or value == NONE else str(value)


class LunaH3ReferenceLoader:
    DESCRIPTION = (
        "Every MiniMax H3 reference in one node: up to 9 pictures, 3 video clips with "
        "their soundtracks, and 3 standalone audio files. Each slot is a dropdown with an "
        "upload button — nothing is typed.\n\n"
        "Clips are decoded to 24 fps because H3 assumes that rate and never resamples, then "
        "cut to the frame counts it accepts (5, 22, 39 … 362 — about 0.2 s to 15 s). Give a "
        "clip a start and a length to use one moment out of a longer file; its soundtrack "
        "follows the same window automatically.\n\n"
        "Everything leaves through the single `refs` output. Drop a Luna H3 Refs Out node "
        "beside the H3 node and wire `refs` to it, and it fans back out into H3's own "
        "sockets — so this node can sit anywhere on the canvas behind one wire.\n\n"
        "asset_brief is the inventory a prompt writer needs: which reference is <Picture 2>, "
        "how long <Video 1> is, and the fact that a clip's soundtrack takes an <Audio> number "
        "BEFORE any standalone file does."
    )
    CATEGORY = "Luna/Load"
    FUNCTION = "load"

    RETURN_TYPES = ("LUNA_H3_REFS", "IMAGE", "INT", "INT", "STRING")
    RETURN_NAMES = ("refs", "images", "width", "height", "asset_brief")
    OUTPUT_TOOLTIPS = (
        "Everything loaded here, as one link. Wire it to Luna H3 Refs Out beside the "
        "MiniMax H3 node.",
        "The pictures as ONE IMAGE batch, conformed to picture 1's size because a batch "
        "cannot hold mixed dimensions. For prompt writers, which flatten it anyway. Empty "
        "of meaning if no pictures are loaded.",
        "Picture 1's width, for driving the generation nodes. 0 when no picture is loaded.",
        "Picture 1's height. 0 when no picture is loaded.",
        "The inventory — what each <Picture>, <Video> and <Audio> tag refers to, how long "
        "the clips are, and any warning worth acting on. Feed it to a prompt writer.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        images = _input_files(["image"])
        # Core's Load Audio lists video files too, because a video carries a
        # soundtrack you may want on its own. Kept, for the same reason.
        videos = _input_files(["video"])
        audios = _input_files(["audio", "video"])

        opt: dict = {}
        for i in range(MAX_IMAGES):
            opt[f"image_{i + 1}"] = (images, {
                "image_upload": True, "default": NONE,
                "tooltip": f"Picture {i + 1} — H3's ref_image_{i}, and <Picture {i + 1}> in "
                           f"the prompt. Order is everything: it is the numbering the model "
                           f"uses. Upload, drag a file on, or pick from the list.",
            })
        for i in range(MAX_VIDEOS):
            opt[f"video_{i + 1}"] = (videos, {
                "video_upload": True, "default": NONE,
                "tooltip": f"Clip {i + 1} — H3's ref_video_{i}, and <Video {i + 1}> in the "
                           f"prompt. Decoded to 24 fps and cut to the model's frame grid. "
                           f"Its soundtrack, if it has one, comes out on ref_video_audio_{i} "
                           f"trimmed to exactly the same window.",
            })
            opt[f"video_{i + 1}_start"] = ("FLOAT", {
                "default": 0.0, "min": 0.0, "max": 86400.0, "step": 0.05,
                "tooltip": "Seconds into the file where this clip starts. 0 = the beginning.",
            })
            opt[f"video_{i + 1}_seconds"] = ("FLOAT", {
                "default": 0.0, "min": 0.0, "max": 15.1, "step": 0.05,
                "tooltip": "How long to take, in seconds. 0 = as much as H3 will accept "
                           "(15.08 s). The result lands on the nearest length the model "
                           "allows, so 5 s becomes 5.17 s (124 frames) — asset_brief reports "
                           "what you actually got. If the file runs out first you simply get "
                           "less; nothing is padded.",
            })
        for i in range(MAX_AUDIOS):
            opt[f"audio_{i + 1}"] = (audios, {
                "audio_upload": True, "default": NONE,
                "tooltip": f"Standalone sound {i + 1} — H3's ref_audio_{i}. Music or a noise "
                           f"the video should reference, NOT a clip's own soundtrack (that "
                           f"comes from the video file automatically). Careful with the "
                           f"numbering: H3 counts clip soundtracks first, so with one "
                           f"soundtracked video this is <Audio {i + 2}>, not <Audio {i + 1}>.",
            })
            opt[f"audio_{i + 1}_start"] = ("FLOAT", {
                "default": 0.0, "min": 0.0, "max": 86400.0, "step": 0.05,
                "tooltip": "Seconds into the file where this excerpt starts.",
            })
            opt[f"audio_{i + 1}_seconds"] = ("FLOAT", {
                "default": 0.0, "min": 0.0, "max": 3600.0, "step": 0.05,
                "tooltip": "How long to take, in seconds. 0 = to the end of the file. "
                           "A window running past the end is simply shorter — never padded, "
                           "because invented silence would teach the model the sound stops.",
            })
        return {"required": {}, "optional": opt}

    @classmethod
    def IS_CHANGED(cls, **kw):
        """Re-run when a chosen file's bytes change, not just its name.

        Pictures are hashed; clips are keyed on mtime and size. A 15 s 1080p file
        is tens of megabytes and this runs on every graph validation, so hashing
        one would stall the editor — and re-exporting a video in place under the
        same name is not the routine act that overwriting a picture is.
        """
        m = hashlib.sha256()
        for key in sorted(kw):
            value = kw[key]
            m.update(f"{key}={value}|".encode("utf-8"))
            if not isinstance(value, str) or value in ("", NONE):
                continue
            try:
                path = folder_paths.get_annotated_filepath(value)
                if not path or not os.path.isfile(path):
                    continue
                if key.startswith("image_"):
                    with open(path, "rb") as fh:
                        m.update(fh.read())
                else:
                    st = os.stat(path)
                    m.update(f"{st.st_mtime_ns}:{st.st_size}".encode("utf-8"))
            except OSError:
                continue
        return m.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, **kw):
        for key, value in kw.items():
            name = _picked(value) if isinstance(value, str) else ""
            if not name:
                continue
            if key.split("_")[0] in ("image", "video", "audio") and key.count("_") == 1:
                if not folder_paths.exists_annotated_filepath(name):
                    return f"{key}: file not found — {name}"
        return True

    def load(self, **kw):
        # --- pictures --------------------------------------------------------
        frames: list = []
        dims: list = []
        for i in range(MAX_IMAGES):
            name = _picked(kw.get(f"image_{i + 1}"))
            if not name:
                continue
            # No black frames and no silent renumbering: a slot left empty in the
            # middle would push every later picture down a number, so the gap is
            # closed here in the order the slots appear and the brief says what
            # ended up where.
            tensor, _original = _load(name)
            frames.append(tensor)
            dims.append((int(tensor.shape[2]), int(tensor.shape[1])))

        # --- clips -----------------------------------------------------------
        videos: list = []
        video_audios: list = []
        v_info: list = []
        for i in range(MAX_VIDEOS):
            name = _picked(kw.get(f"video_{i + 1}"))
            if not name:
                continue
            path = folder_paths.get_annotated_filepath(name)
            if not path or not os.path.isfile(path):
                raise RuntimeError(f"[Luna H3 Reference Loader] Video not found: {name}")
            clip, info = decode_video(path,
                                      float(kw.get(f"video_{i + 1}_start", 0.0) or 0.0),
                                      float(kw.get(f"video_{i + 1}_seconds", 0.0) or 0.0))
            videos.append(clip)
            # The soundtrack rides the window the video ENDED UP with, not the one
            # that was asked for: the frame count was snapped to H3's grid, so
            # info["seconds"] is the only length that keeps picture and sound
            # describing the same moment.
            try:
                track, _ = load_audio(path, info["start"], info["seconds"])
            except Exception:
                track = None          # a silent clip is normal, not an error
            video_audios.append(track)
            v_info.append(info)

        # --- standalone audio ------------------------------------------------
        audios: list = []
        a_info: list = []
        for i in range(MAX_AUDIOS):
            name = _picked(kw.get(f"audio_{i + 1}"))
            if not name:
                continue
            path = folder_paths.get_annotated_filepath(name)
            if not path or not os.path.isfile(path):
                raise RuntimeError(f"[Luna H3 Reference Loader] Audio not found: {name}")
            clip, info = load_audio(path,
                                    float(kw.get(f"audio_{i + 1}_start", 0.0) or 0.0),
                                    float(kw.get(f"audio_{i + 1}_seconds", 0.0) or 0.0))
            audios.append(clip)
            a_info.append(info)

        if not frames and not videos and not audios:
            raise RuntimeError(
                "[Luna H3 Reference Loader] Nothing selected. Pick at least one picture, "
                "clip or sound — every dropdown is still on (none)."
            )
        # H3's own rule, worth failing on rather than discovering in the sampler:
        # reference audio is meaningless without something to attach it to.
        if audios and not frames and not videos:
            raise RuntimeError(
                "[Luna H3 Reference Loader] Reference audio needs a picture or a clip to go "
                "with it — MiniMax H3 will not accept audio references on their own."
            )

        brief = _build_brief(frames, dims, v_info, video_audios, a_info)
        batch = _conform(frames) if frames else None
        w, h = dims[0] if dims else (0, 0)
        refs = {
            "images": frames,
            "videos": videos,
            "video_audios": video_audios,
            "audios": audios,
            "brief": brief,
            "width": w,
            "height": h,
        }
        print(f"[Luna H3 Reference Loader] {len(frames)} picture(s), {len(videos)} clip(s), "
              f"{sum(1 for t in video_audios if t is not None)} soundtrack(s), "
              f"{len(audios)} standalone audio")
        return (refs, batch, w, h, brief)


def _build_brief(frames, dims, v_info, video_audios, a_info) -> str:
    """The inventory string, in H3's own presentation order.

    The audio numbering is the part nothing else states and the part that goes
    wrong silently. In `MiniMaxH3ReferenceToVideo.execute`, a clip's soundtrack
    appends its `{"type": "audio"}` presentation item IMMEDIATELY BEFORE its
    video, and standalone audios append after every video. Ordinals are 1-based
    per type, so one soundtracked clip makes the first standalone file <Audio 2>.
    A prompt writer that assumes otherwise names the wrong sound every time.
    """
    parts: list[str] = []
    for i, (w, h) in enumerate(dims, start=1):
        parts.append(f"<Picture {i}> = {_describe_ar(w, h)}")

    audio_ordinal = 0
    for k, (info, track) in enumerate(zip(v_info, video_audios), start=1):
        if track is not None:
            audio_ordinal += 1
            parts.append(f"<Audio {audio_ordinal}> = the soundtrack of <Video {k}>, "
                         f"{info['seconds']:.2f} s")
        entry = (f"<Video {k}> = {info['seconds']:.2f} s, {info['frames']} frames at "
                 f"{FPS} fps, {_describe_ar(info['width'], info['height'])}")
        sw, sh = info["source_size"]
        if abs(info["source_fps"] - FPS) > 0.01:
            entry += f" [resampled from {info['source_fps']:.3f} fps]"
        if (sw, sh) != (info["width"], info["height"]):
            entry += f" [decoded down from {sw}x{sh}]"
        if info["start"] > 0:
            entry += f" [from {info['start']:.2f} s of {info['name']}]"
        parts.append(entry)

    for info in a_info:
        audio_ordinal += 1
        entry = (f"<Audio {audio_ordinal}> = {info['seconds']:.2f} s, "
                 f"{info['sample_rate'] / 1000:.1f} kHz, "
                 f"{'stereo' if info['channels'] >= 2 else 'mono'}")
        if info["start"] > 0:
            entry += f" [from {info['start']:.2f} s of {info['name']}]"
        if info["short"]:
            entry += f" [asked for {info['asked']:.2f} s; the file ended first]"
        parts.append(entry)

    brief = "References, in the order MiniMax H3 numbers them: " + "; ".join(parts) + "."

    # Advisory, never fatal. The node cannot see which of its outputs are wired,
    # so three loaded clips may be one wired clip; it reports and leaves the
    # judgement there. Same precedent as the Asset Loader's FL2VA warning.
    warnings: list[str] = []
    for k, info in enumerate(v_info, start=1):
        if info["seconds"] < 2.0:
            warnings.append(f"<Video {k}> is only {info['seconds']:.2f} s; H3's reference "
                            f"clips are documented as 2-15 s")
    total = sum(i["seconds"] for i in v_info)
    if total > 15.0:
        warnings.append(f"the clips total {total:.1f} s, over H3's 15 s budget "
                        f"(only what you actually wire counts)")
    if len(dims) >= 2:
        r0, r1 = dims[0][0] / dims[0][1], dims[1][0] / dims[1][1]
        # Relative, not absolute: a /32 snap moves an aspect ratio by up to ~1%
        # on its own, so a tight threshold would warn on every snapped pair.
        if abs(r0 - r1) / max(r0, r1) > 0.02:
            warnings.append(f"<Picture 1> and <Picture 2> have different aspect ratios "
                            f"({_describe_ar(*dims[0])} vs {_describe_ar(*dims[1])}) — fine "
                            f"for REF2VA, but in FL2VA the first frame is stretched and the "
                            f"last centre-cropped")
    if warnings:
        brief += " WARNING: " + "; ".join(warnings) + "."
        print(f"[Luna H3 Reference Loader] {'; '.join(warnings)}")
    return brief


NODE_CLASS_MAPPINGS = {"LunaH3ReferenceLoader": LunaH3ReferenceLoader}
NODE_DISPLAY_NAME_MAPPINGS = {"LunaH3ReferenceLoader": "Luna H3 Reference Loader"}
