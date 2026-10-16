"""Luna Asset Loader — one ordered set of reference images, many consumers.

Loads up to 9 images and hands them out three ways at once:

  image_1 … image_N   each at its ORIGINAL size, in card order, for the native
                      MiniMax H3 sockets (ref_image_0 … ref_image_8, or slots
                      1 and 2 as first_frame / last_frame in FL2VA)
  images              one conformed IMAGE batch, for prompt writers that only
                      ever flatten it anyway (Luna Agent Chat, LLM Prompt)
  width / height      image 1's dimensions, to drive the generation nodes
  asset_brief         "<Picture 1> = 1920x1056 (20:11) …" for the prompt writer

Why originals and a batch, rather than one or the other: an IMAGE batch cannot
hold mixed sizes, and H3's REF2VA path deliberately keeps each reference at its
own aspect ratio — conforming them there would destroy information the model
wants. The numbered outputs stay untouched; only the batch is conformed.

Ordering is the whole point. Card order here is the same order H3 numbers its
references, so slot N is <Picture N> everywhere downstream, and the brief states
that mapping explicitly rather than leaving a prompt writer to guess.

Per-image resize is modelled on ComfyUI-Pixaroma
(https://github.com/pixaroma/ComfyUI-Pixaroma), MIT, Copyright (c) 2026 pixaroma.

The `asset_state` schema comes from that pack's `RESIZE_DEFAULTS` in
`nodes/_resize_helpers.py`: the key names and their defaults — `mode`
(off | max_mp | longest_side | scale_factor), `ratio_action`, `crop_anchor`,
`pad_color`, `snap`, `allow_upscale`, `resample` — are theirs, as is the idea of
keeping the whole thing as a JSON state blob rather than a row of widgets. Credit
where it is due: that design is why nine images can each carry their own settings
without the node growing nine sets of controls.

The code here was written against that schema rather than copied from it, and
differs where this node's job differs: one state per image instead of one per
node, `allow_upscale` defaulting to False because MiniMax H3 never upscales a
reference, `snap` documented against H3's CANVAS_MULTIPLE of 32, and the order
fixed as aspect -> size -> snap.

Sound cards (v3, 2026-10-16). A sound card holds a song and the window of it the
shot uses: start, duration, and what to do when the window runs off the end
(silence or loop). The window is stored in `media_state` (JSON) and comes out on
`audio`, exactly as long as asked — when the `seconds` input is wired, that is the
duration, so the song always matches the shot length. Window maths: media_io.

Outputs `audio`, `refs` and `timeline` sit at slots 4-6, BEFORE image_N. The
frontend shrinks the node by removing trailing image_N slots, and ComfyUI maps an
output to the returned tuple by index, so nothing may sit after the image block.
Workflows saved before these three existed are migrated in the frontend before
the graph is configured (js/luna_asset_loader.js, migrateWorkflowJSON) — see the
2026-10-16 decision in STATUS for why it cannot happen later.
"""

from __future__ import annotations

import hashlib
import json
import math
import os

import numpy as np
import torch
from PIL import Image, ImageOps

import folder_paths
import node_helpers

from .asset_timeline import (check_placements, h3_tags, newest_video, normalize_sound_role, shot_frames,
                             tail_start, target_fps, target_grid, thinning_error)
from .media_io import (FPS, clip_bytes, clip_soundtrack, decode_clip, filmstrip_jpeg, grid_frames, strip_annotation,
                       load_audio, load_audio_window, probe_media, song_shot_count, song_shot_start)

MAX_IMAGES = 9  # MiniMax H3's own reference ceiling
MAX_SOUNDS = 3  # MiniMax H3 takes three standalone sounds
MAX_VIDEOS = 3  # MiniMax H3 takes three reference clips
MEMORY_CAP = 6 * 1024 ** 3   # refuse a clip bigger than this BEFORE decoding it

# Aspect ratios a reader is likely to have a name for. Reported alongside the
# exact ratio, never instead of it: 832x1216 is exactly 13:19, and calling it
# "2:3" without saying so is how a wrong frame shape ends up in a prompt.
_COMMON_AR = [(1, 1), (2, 3), (3, 2), (3, 4), (4, 3), (4, 5), (5, 4),
              (9, 16), (16, 9), (1, 2), (2, 1), (21, 9)]


def _describe_ar(w: int, h: int) -> str:
    ratio = w / h
    a, b = min(_COMMON_AR, key=lambda c: abs(c[0] / c[1] - ratio))
    nearest = f"{a}:{b}"
    orient = "portrait" if ratio < 0.99 else ("landscape" if ratio > 1.01 else "square")

    g = math.gcd(w, h) or 1
    ew, eh = w // g, h // g
    if (ew, eh) == (a, b):
        return f"{w}x{h} ({nearest}, {orient})"
    if max(ew, eh) <= 32:
        # A small exact ratio is worth naming: 832x1216 really is 13:19, and
        # calling it 2:3 unqualified is how a wrong frame shape reaches a prompt.
        return f"{w}x{h} (exactly {ew}:{eh}, nearest standard {nearest}, {orient})"
    # 1672x941 reduces to 1672:941, which tells nobody anything. Give the decimal.
    return f"{w}x{h} ({ratio:.2f}:1, nearest standard {nearest}, {orient})"


def _split_paths(raw: str) -> list[str]:
    """One entry per line. The card UI will write this same field later."""
    out: list[str] = []
    for line in (raw or "").replace("\r", "\n").split("\n"):
        line = line.strip().strip('"')
        if line:
            out.append(line)
    return out


def _load(path: str, st: dict | None = None) -> tuple[torch.Tensor, tuple[int, int]]:
    """One image -> ([1, H, W, C] float 0-1, original (w, h)).

    The ORIGINAL size is returned alongside because the brief reports what you
    supplied, not what the loader produced — otherwise a resize would quietly
    rewrite the record of what your source actually was.
    """
    resolved = folder_paths.get_annotated_filepath(path)
    if not resolved or not os.path.isfile(resolved):
        raise RuntimeError(
            f"[Luna Asset Loader] Image not found: {path}. Put it in ComfyUI's "
            f"input folder and use the file name, one per line."
        )
    img = node_helpers.pillow(Image.open, resolved)
    img = ImageOps.exif_transpose(img).convert("RGB")
    original = img.size
    if st:
        img = _apply_state(img, st)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...], original


# Per-image resize state. The key names follow ComfyUI-Pixaroma's LoadImageMini
# state (MIT, compatible with this pack) so the two feel the same to use; the
# implementation below is our own and covers only what H3 work needs.
#
# mode defaults to "off" — nothing is resized unless asked. That default is the
# whole point: H3's REF2VA path keeps each reference's own aspect ratio, so
# conforming references by default would destroy information the model wants.
_DEFAULT_ITEM = {
    "mode": "off",           # off | max_mp | longest_side | scale_factor
    "max_mp": 2.0,
    "longest_side": 1024,
    "scale_factor": 1.0,
    "ratio": "",             # "" keeps the source aspect; else "16:9", "2:3", …
    "ratio_action": "crop",  # crop | pad
    "crop_anchor": "center",
    "pad_color": "#000000",
    "snap": 0,               # 0 = off; 32 matches H3's CANVAS_MULTIPLE
    "allow_upscale": False,  # H3 never upscales a reference; the loader is the
                             # only place it can happen, so make it deliberate
}


def _parse_media(raw: str) -> dict:
    """media_state JSON -> {"audio": [card, ...]}. A card: file, start, duration
    (seconds, 0 = to the end of the file) and fill ("silence" | "loop")."""
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        raise RuntimeError("[Luna Asset Loader] media_state is not valid JSON. "
                           "Clear the sound cards and add them again.")
    cards = []
    for c in (data.get("audio") or [])[:MAX_SOUNDS]:
        if not isinstance(c, dict) or not c.get("file"):
            continue
        # Sound 1 is the song and drives the shot unless told otherwise; later
        # sounds are references for MiniMax H3 unless placed on the shot.
        role = normalize_sound_role(c.get("role"), len(cards))
        cards.append({
            "role": role,
            "at": max(0, int(c.get("at") or 0)),
            "file": str(c["file"]),
            "start": max(0.0, float(c.get("start") or 0.0)),
            "duration": max(0.0, float(c.get("duration") or 0.0)),
            "fill": "loop" if c.get("fill") == "loop" else "silence",
            # Song position: "free" = the window is where start says; "shot" = the
            # window follows the shot number from song_start, `overlap` frames shared.
            "position": "shot" if c.get("position") == "shot" else "free",
            "song_start": max(0.0, float(c.get("song_start") or 0.0)),
            "shot": max(1, int(c.get("shot") or 1)),
            "overlap": max(0, int(c.get("overlap") if c.get("overlap") is not None else 22)),
        })
    clips = []
    for c in (data.get("video") or [])[:MAX_VIDEOS]:
        if not isinstance(c, dict) or not c.get("file"):
            continue
        fps = c.get("fps", "target")
        clips.append({
            "role": "guide" if c.get("role") == "guide" else "ref",
            "at": max(0, int(c.get("at") or 0)),
            "file": str(c["file"]),
            "start": max(0.0, float(c.get("start") or 0.0)),
            "frames": max(1, int(c.get("frames") or 124)),
            # "target" = the target model's rate (24 for MiniMax H3), "source" = as filmed
            "fps": fps if fps in ("target", "source") else max(1.0, float(fps)),
            "count": "free" if c.get("count") == "free" else "target",
            "size": c.get("size") if c.get("size") in ("canvas", "edge", "source") else "canvas",
            "fit": c.get("fit") if c.get("fit") in ("crop", "pad", "stretch") else "crop",
            "nth": max(1, int(c.get("nth") or 1)),
            "sound": "drop" if c.get("sound") == "drop" else "keep",
            "precision": "fp32" if c.get("precision") == "fp32" else "fp16",
        })
    # Picture roles, in card order (index-aligned with image_paths). Missing = reference.
    pics = []
    for p in (data.get("pictures") or [])[:MAX_IMAGES]:
        p = p if isinstance(p, dict) else {}
        pics.append({"role": "key" if p.get("role") == "key" else "ref", "at": max(0, int(p.get("at") or 0))})
    shot = data.get("shot") if isinstance(data.get("shot"), dict) else {}
    # The continuation: the end of the previous shot, anchored at frame 0 of this one.
    c = data.get("continuation") if isinstance(data.get("continuation"), dict) else {}
    cont = {
        "on": bool(c.get("on")),
        "from": c.get("from") if c.get("from") in ("folder", "file", "input") else "folder",
        "folder": str(c.get("folder") or ""),
        "file": str(c.get("file") or ""),
        "take": "last" if c.get("take") == "last" else "frames",
        "frames": max(1, int(c.get("frames") or 22)),
    }
    # Node-wide settings from the ⚙ panel.
    st = data.get("settings") if isinstance(data.get("settings"), dict) else {}
    settings = {
        "target": st.get("target") if st.get("target") in ("h3", "ltx", "general") else "h3",
        "memory_gb": min(64.0, max(1.0, float(st.get("memory_gb") or MEMORY_CAP / 1024 ** 3))),
    }
    return {"audio": cards, "video": clips, "pictures": pics,
            "shot_frames": max(1, int(shot.get("frames") or 124)), "continuation": cont, "settings": settings}


def _clock(t: float) -> str:
    m, s = divmod(max(0.0, t), 60.0)
    return f"{int(m)}:{s:05.2f}"


def _parse_state(raw: str, count: int) -> list[dict]:
    """JSON -> one settled state dict per image.

    Accepts {"all": {...}} to apply one state to every image, {"items": [...]}
    for per-image control, or both, where items win. Anything malformed falls
    back to defaults rather than failing the run — a bad state string should not
    cost a render.
    """
    base = dict(_DEFAULT_ITEM)
    items: list[dict] = []
    try:
        parsed = json.loads(raw) if raw and raw.strip() else {}
        if isinstance(parsed, dict):
            shared = parsed.get("all")
            if isinstance(shared, dict):
                base.update({k: v for k, v in shared.items() if k in _DEFAULT_ITEM})
            listed = parsed.get("items")
            if isinstance(listed, list):
                items = [x if isinstance(x, dict) else {} for x in listed]
    except Exception:
        pass

    out = []
    for i in range(count):
        st = dict(base)
        if i < len(items):
            st.update({k: v for k, v in items[i].items() if k in _DEFAULT_ITEM})
        out.append(st)
    return out


def _snap(v: int, step: int) -> int:
    return max(step, round(v / step) * step) if step and step > 1 else max(1, v)


def _apply_state(img: Image.Image, st: dict) -> Image.Image:
    """Conform aspect first, then size, then snap. Order matters: cropping after
    scaling would undo the size you just asked for."""
    if st.get("mode") == "off" and not st.get("ratio") and not st.get("snap"):
        return img

    w, h = img.size

    # 1. aspect — crop away or pad out to the requested ratio
    ratio = str(st.get("ratio") or "").strip()
    if ratio and ":" in ratio:
        try:
            rw, rh = (float(x) for x in ratio.split(":", 1))
            target = rw / rh
        except Exception:
            target = None
        if target and abs(w / h - target) > 0.001:
            if st.get("ratio_action") == "pad":
                nw, nh = (w, round(w / target)) if w / h > target else (round(h * target), h)
                canvas = Image.new("RGB", (max(nw, w), max(nh, h)), st.get("pad_color") or "#000000")
                canvas.paste(img, ((max(nw, w) - w) // 2, (max(nh, h) - h) // 2))
                img = canvas
            else:
                nw, nh = (round(h * target), h) if w / h > target else (w, round(w / target))
                anchor = str(st.get("crop_anchor") or "center")
                left = 0 if "left" in anchor else (w - nw if "right" in anchor else (w - nw) // 2)
                top = 0 if "top" in anchor else (h - nh if "bottom" in anchor else (h - nh) // 2)
                img = img.crop((left, top, left + nw, top + nh))
            w, h = img.size

    # 2. size
    mode = str(st.get("mode") or "off")
    scale = 1.0
    if mode == "max_mp":
        budget = float(st.get("max_mp", 2.0)) * 1_000_000
        if budget > 0:
            scale = math.sqrt(budget / (w * h))
    elif mode == "longest_side":
        scale = float(st.get("longest_side", 1024)) / max(w, h)
    elif mode == "scale_factor":
        scale = float(st.get("scale_factor", 1.0))
    if not st.get("allow_upscale", False):
        scale = min(1.0, scale)

    step = int(st.get("snap") or 0)
    nw, nh = _snap(round(w * scale), step), _snap(round(h * scale), step)
    if (nw, nh) != (w, h):
        img = img.resize((max(1, nw), max(1, nh)), Image.LANCZOS)
    return img


def _conform(frames: list[torch.Tensor]) -> torch.Tensor:
    """Mixed sizes -> one batch, matched to frame 1.

    Only the batch output is conformed. Its consumers re-encode every frame to
    JPEG individually anyway, so resampling here costs nothing downstream, and
    a batch is the only shape a normal IMAGE socket accepts.
    """
    h, w = int(frames[0].shape[1]), int(frames[0].shape[2])
    out = []
    for f in frames:
        if int(f.shape[1]) == h and int(f.shape[2]) == w:
            out.append(f)
            continue
        arr = (f[0].cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
        resized = Image.fromarray(arr, mode="RGB").resize((w, h), Image.LANCZOS)
        out.append(torch.from_numpy(np.asarray(resized, dtype=np.float32) / 255.0)[None, ...])
    return torch.cat(out, dim=0)


class LunaAssetLoader:
    DESCRIPTION = (
        "Load up to 9 ordered reference images and a song through one node. Numbered "
        "outputs keep each image at its original size for the MiniMax H3 reference sockets; "
        "the `images` batch feeds prompt writers. Card order is <Picture 1>, <Picture 2>, and "
        "so on, and asset_brief states that mapping so nothing has to guess it.\n\n"
        "Upload a sound file and it becomes a sound card. Select it to see the whole song: "
        "drag the window to choose the part the shot uses, drag its edges or type Start and "
        "Duration. Wire `seconds` (for example from the canvas node) and the duration is "
        "locked to the shot length; only the start moves. `audio` delivers exactly that window."
    )
    CATEGORY = "Luna/Load"
    FUNCTION = "load"

    # Fixed outputs FIRST, growable image_N last. The frontend removes trailing
    # slots to shrink the node, and ComfyUI maps outputs to the returned tuple by
    # INDEX — so anything that must keep its meaning has to sit at an index that
    # never moves. With image_N first, dropping image_3 would silently hand
    # image_3's tensor to `images`. audio/refs/timeline (v3) are fixed too, so they
    # sit at 4-6; old saves are moved up by the frontend migration.
    RETURN_TYPES = ("IMAGE", "INT", "INT", "STRING", "AUDIO", "LUNA_H3_REFS", "LUNA_TIMELINE") \
        + ("IMAGE",) * MAX_IMAGES
    RETURN_NAMES = ("images", "width", "height", "asset_brief", "audio", "refs", "timeline") + tuple(
        f"image_{i + 1}" for i in range(MAX_IMAGES)
    )
    # ComfyUI shows these when you hover an output socket, and the ⓘ panel lists
    # them too — one definition, both places, so they cannot disagree.
    OUTPUT_TOOLTIPS = (
        "Every loaded picture as ONE IMAGE batch, conformed to image 1's size "
        "because a batch cannot hold mixed dimensions. For prompt writers "
        "(Luna Agent Chat, LLM Prompt) which flatten it to individual JPEGs anyway. Empty when only "
        "clips or sounds are loaded.",
        "Image 1's width AFTER its resize, for driving the generation nodes. With no pictures loaded: the wired width, else 0.",
        "Image 1's height AFTER its resize. With no pictures loaded: the wired height, else 0.",
        "A one-line inventory — '<Picture 1> = 1920x1056 (20:11, landscape); ...' — "
        "plus a warning when pictures 1 and 2 differ in aspect ratio, which FL2VA "
        "silently fixes by stretching the first frame and cropping the last. "
        "Feed it to a prompt writer so it knows which reference is which.",
        "The song window from sound card 1: exactly the duration you set, or exactly the "
        "seconds input when it is wired. Wire it to the save node so the finished video has "
        "the same sound, or to an audio-sync node to make the picture follow it.",
        "Every picture as a MiniMax H3 reference (<Picture 1> … in card order), for Luna H3 "
        "Refs Out, which splits it into the sampler's ref_image sockets.",
        "What sits on the shot timeline and where, in frames. Today: the song, locked from "
        "frame 0. Pictures and clips join it in later versions of this node.",
    ) + tuple(
        f"Picture {i + 1} at its ORIGINAL size (only the batch is conformed), "
        f"in card order. Wire to the MiniMax H3 ref_image_{i} socket — or in FL2VA, "
        f"{'first_frame' if i == 0 else 'last_frame' if i == 1 else f'reference {i + 1}'}. "
        f"Empty when fewer than {i + 1} images are loaded."
        for i in range(MAX_IMAGES)
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_paths": ("STRING", {
                    "multiline": True, "default": "",
                    "tooltip": "One image file name per line, from ComfyUI's input folder. Order is everything: line 1 is <Picture 1>, line 2 is <Picture 2>, and so on. In FL2VA the first two lines are the first and last frame.",
                }),
                "image_count": ("INT", {
                    "default": 2, "min": 1, "max": MAX_IMAGES,
                    "tooltip": "How many numbered outputs the node shows. Set it with the Image slots stepper at the top left of the node, beside the four fixed outputs (click the number to type one); it sits there because it is the one spot that does not slide down as sockets are added. It also follows the cards — uploading, removing or typing a file name sets it. Every change applies immediately; there is nothing to press. A socket you have wired is never removed, so disconnect it first if you want to go below it. Fewer outputs than images is useful, not a mistake: the extra pictures stay loaded and you can drag one up into an active slot, leaving the rest parked. Sockets beyond the number of loaded images stay empty.",
                }),
            },
            "optional": {
                "asset_state": ("STRING", {
                    "default": "", "multiline": True,
                    "tooltip": "Per-image resize, as JSON. Empty = every image passed through untouched, which is what REF2VA wants. {\"all\": {...}} applies one state to every image; {\"items\": [{...}, ...]} sets them individually and wins over \"all\". Keys: mode (off|max_mp|longest_side|scale_factor), max_mp, longest_side, scale_factor, ratio (\"16:9\"), ratio_action (crop|pad), crop_anchor, pad_color, snap (32 for H3), allow_upscale. Example — conform the first two frames for FL2VA and leave the references alone: {\"items\":[{\"ratio\":\"16:9\",\"snap\":32},{\"ratio\":\"16:9\",\"snap\":32}]}",
                }),
                # Added LAST on purpose: saved workflows keep their widget values by
                # position, and a widget appended at the end shifts nothing.
                "media_state": ("STRING", {
                    "default": "",
                    "tooltip": "The sound cards, as JSON, written by the card UI: {\"audio\": [{\"file\": \"song.mp3\", \"start\": 42.5, \"duration\": 5.17, \"fill\": \"silence\"}]}. start and duration are seconds; duration 0 = to the end of the file; fill is what happens when the window runs past the end (silence or loop).",
                }),
                "seconds": ("FLOAT", {
                    "forceInput": True,
                    "tooltip": "The shot length in seconds. Wired, it sets the song window's duration, so the song always matches the shot; the window then only moves. Unwired, the duration on the sound card is used.",
                }),
                "shot": ("INT", {
                    "forceInput": True,
                    "tooltip": "Which shot of the song this run makes, counting from 1. Only used when the sound card's Position is 'By shot number': shot n starts where shot n-1 started plus the shot length minus the overlap. Unwired, the shot number on the sound card is used.",
                }),
                "width": ("INT", {
                    "forceInput": True,
                    "tooltip": "The generation width, for example from the canvas node. Video cards set to 'Match canvas' are cut to width x height. Unwired, they keep their shape at a 768 short edge.",
                }),
                "height": ("INT", {
                    "forceInput": True,
                    "tooltip": "The generation height. See width.",
                }),
                "previous_frames": ("IMAGE", {
                    "tooltip": "The previous shot's frames, for a continuation whose source is 'Input': its last frames open this shot, so the motion carries on across the cut.",
                }),
            },
        }

    @classmethod
    def IS_CHANGED(cls, image_paths, image_count, asset_state="", media_state="", **kwargs):
        # Hash the file contents, not just the names: re-uploading a changed
        # picture under the same name must re-run the graph. Songs are big, so
        # they are keyed on size and modification time instead.
        m = hashlib.sha256()
        m.update(f"{image_count}|{asset_state}|{media_state}".encode("utf-8"))
        for p in _split_paths(image_paths):
            resolved = folder_paths.get_annotated_filepath(p)
            m.update(p.encode("utf-8"))
            if resolved and os.path.isfile(resolved):
                with open(resolved, "rb") as fh:
                    m.update(fh.read())
        try:
            media = _parse_media(media_state)
            cards = media["audio"] + media["video"]
        except RuntimeError:
            cards = []
        for c in cards:
            resolved = folder_paths.get_annotated_filepath(c["file"])
            if resolved and os.path.isfile(resolved):
                s = os.stat(resolved)
                m.update(f"{c['file']}|{s.st_size}|{s.st_mtime_ns}".encode("utf-8"))
        # A continuation from an output folder must re-run when a newer shot lands there.
        try:
            cont = _parse_media(media_state)["continuation"]
            # ... and when the picked continuation file is overwritten under the same name.
            if cont["on"] and cont["from"] in ("folder", "file"):
                src = _output_newest(cont["folder"]) if cont["from"] == "folder" else _media_file(cont["file"])
                if src:
                    s = os.stat(src)
                    m.update(f"{src}|{s.st_size}|{s.st_mtime_ns}".encode("utf-8"))
        except (RuntimeError, OSError, ValueError):
            pass
        return m.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, image_paths, image_count, **kwargs):
        paths = _split_paths(image_paths)
        if len(paths) > MAX_IMAGES:
            return (f"MiniMax H3 takes at most {MAX_IMAGES} reference images, "
                    f"but {len(paths)} lines are listed.")
        return True

    def load(self, image_paths, image_count, asset_state="", media_state="", seconds=None, shot=None,
             width=None, height=None, previous_frames=None):
        paths = _split_paths(image_paths)
        media = _parse_media(media_state)
        cards, clips = media["audio"], media["video"]
        if not paths and not cards and not clips:
            raise RuntimeError(
                "[Luna Asset Loader] Nothing loaded. Press Upload and add pictures, clips or a song."
            )
        shot_len = shot_frames(seconds, media["shot_frames"])

        # --- load everything -------------------------------------------------
        audio, song, song_line = self._song(cards, seconds, shot)
        settings = media["settings"]
        decoded = self._clips(clips, width, height, settings)
        extra_sounds = self._sounds(cards)
        carry, carry_line = self._continuation(media["continuation"], cards, song, width, height, previous_frames,
                                               settings)
        frames, dims, originals = [], [], []
        if paths:
            states = _parse_state(asset_state, len(paths))
            loaded = [_load(p, st) for p, st in zip(paths, states)]
            frames = [f for f, _ in loaded]
            originals = [o for _, o in loaded]
            dims = [(int(f.shape[2]), int(f.shape[1])) for f in frames]  # (w, h) as delivered

        # --- roles, tags, placements --------------------------------------------
        pic = [media["pictures"][i] if i < len(media["pictures"]) else {"role": "ref", "at": 0}
               for i in range(len(paths))]
        tags = h3_tags([p["role"] for p in pic],
                       [{"role": c["role"], "sound": d["sound"] is not None} for c, d in zip(clips, decoded)],
                       [c["role"] for c in cards])
        placed = [(f"Picture card {i + 1}", p["at"], 1) for i, p in enumerate(pic) if p["role"] == "key"]
        placed += [(f"Clip V{k + 1} ({c['file']})", c["at"], int(d["batch"].shape[0]))
                   for k, (c, d) in enumerate(zip(clips, decoded)) if c["role"] == "guide"]
        placed += [(f"Sound A{j + 1} ({c['file']})", c["at"], 1)
                   for j, c in enumerate(cards) if c["role"] in ("guide", "lock")]
        if carry is not None:
            placed.append(("The continuation", 0, int(carry["frames" if carry["kind"] == "video" else "image"].shape[0])))
        errors = check_placements(shot_len, placed, settings["target"])
        if errors:
            raise RuntimeError("[Luna Asset Loader] " + " ".join(errors) + " Drag it on the shot timeline.")

        # --- references for MiniMax H3 ---------------------------------------------
        ref_pics = [i for i, p in enumerate(pic) if p["role"] == "ref"]
        ref_clips = [k for k, c in enumerate(clips) if c["role"] == "ref"]
        ref_sounds = [j for j, c in enumerate(cards) if c["role"] == "ref"]
        refs = {"images": [frames[i] for i in ref_pics],
                "videos": [decoded[k]["batch"] for k in ref_clips],
                "video_audios": [decoded[k]["sound"] for k in ref_clips],
                "audios": [extra_sounds[j][0] for j in ref_sounds if extra_sounds.get(j)],
                "width": dims[0][0] if dims else 0, "height": dims[0][1] if dims else 0}

        # --- the brief ---------------------------------------------------------------
        parts = []
        if ref_pics:
            lines = []
            for i in ref_pics:
                (w, h), (ow, oh) = dims[i], originals[i]
                entry = f"{tags['pictures'][i]} = {_describe_ar(w, h)}"
                if len(ref_pics) != len(paths):
                    entry += f" (picture card {i + 1})"
                if (w, h) != (ow, oh):
                    # Say what it was as well as what it became. A prompt writer told
                    # only the resized number cannot tell a deliberate crop from an
                    # accident, and neither can you reading it back later.
                    entry += f" [resized from {ow}x{oh}]"
                lines.append(entry)
            parts.append("Reference images, in order: " + "; ".join(lines) + ".")
        # FL2VA forces both frames to the exact generation size — the first with
        # crop disabled, so a mismatched aspect is STRETCHED, and the last with a
        # centre crop, so it is CUT. Neither errors, so say it here or nobody
        # finds out until they watch the render.
        # Relative, not absolute: snapping to a /32 grid moves the aspect ratio by
        # up to ~1% by itself, so a tight absolute threshold would warn on every
        # snapped pair. 2% is above that noise floor and still catches a stretch
        # you would see.
        if len(dims) >= 2:
            r0, r1 = dims[0][0] / dims[0][1], dims[1][0] / dims[1][1]
            if abs(r0 - r1) / max(r0, r1) > 0.02:
                warn = (f"WARNING: picture cards 1 and 2 have different aspect ratios "
                        f"({_describe_ar(*dims[0])} vs {_describe_ar(*dims[1])}). Fine for "
                        f"REF2VA, which keeps each aspect. In FL2VA the first frame gets "
                        f"stretched and the last centre-cropped.")
                print(f"[Luna Asset Loader] {warn}")
                parts.append(warn)
        for k in ref_clips:
            line = f"{tags['videos'][k]} = {decoded[k]['line']}"
            if k in tags["video_audio"]:
                line += f"; its sound is {tags['video_audio'][k]}"
            elif clips[k]["sound"] == "keep":
                line += "; it has no sound"
            parts.append(line + ".")
        for j in ref_sounds:
            if extra_sounds.get(j):
                parts.append(f"{tags['sounds'][j]} = {extra_sounds[j][1]}.")
        if refs["audios"] and not refs["images"] and not refs["videos"]:
            parts.append("WARNING: MiniMax H3 does not accept reference sounds without a reference "
                         "picture or clip.")
        on_shot = self._shot_lines(pic, clips, decoded, cards, song)
        if carry_line:
            on_shot.insert(0, carry_line)
        if on_shot:
            parts.append(f"On the shot ({shot_len} frames, {shot_len / FPS:.2f} s): " + "; ".join(on_shot) + ".")
        if song_line:
            parts.append(song_line)
        brief = " ".join(parts)
        refs["brief"] = brief
        print(f"[Luna Asset Loader] {brief}")

        timeline = self._timeline(shot_len, pic, frames, clips, decoded, cards, extra_sounds, audio, song)
        if carry is not None:
            timeline["items"].insert(0, carry)
        numbered: list = [frames[i] if i < len(frames) else None for i in range(MAX_IMAGES)]
        if dims:
            w, h = dims[0]
        else:
            # No pictures: hand on the canvas size when it is wired rather than a
            # silent 0x0; `images` and image_N stay empty (never black frames).
            w = int(width) if width and int(width) > 0 else 0
            h = int(height) if height and int(height) > 0 else 0
            if not (w and h):
                print("[Luna Asset Loader] No pictures loaded and no width/height wired: width and height are 0.")
        result = (_conform(frames) if frames else None, w, h, brief, audio, refs, timeline) + tuple(numbered)
        return {"ui": {"luna_asset_audio": [song] if song else []}, "result": result}

    @staticmethod
    def _clips(clips, width, height, settings=None):
        """Video cards -> [{"batch", "sound", "info", "line"}], in card order."""
        out = []
        settings = settings or {"target": "h3", "memory_gb": MEMORY_CAP / 1024 ** 3}
        cap, grid_t = settings["memory_gb"] * 1024 ** 3, target_grid(settings["target"])
        box = (int(width), int(height)) if width and height and int(width) > 0 and int(height) > 0 else None
        for k, c in enumerate(clips, 1):
            path = _media_file(c["file"])
            if not path:
                raise RuntimeError(f"[Luna Asset Loader] Clip not found in the input folder: {c['file']}")
            grid = grid_t if c["count"] == "target" else "free"
            bad = thinning_error("target" if grid != "free" else "free", c["nth"])
            if bad:
                raise RuntimeError(f"[Luna Asset Loader] Clip V{k} ({c['file']}): {bad}")
            info = probe_media(path)
            if not info.get("video"):
                raise RuntimeError(f"[Luna Asset Loader] {c['file']} has no picture, only sound.")
            fps = (target_fps(settings["target"], info["fps"]) if c["fps"] == "target"
                   else (info["fps"] or FPS) if c["fps"] == "source" else c["fps"])
            frames = grid_frames(c["frames"], grid)
            if c["size"] == "canvas" and box:
                size, (ow, oh) = ("box", box[0], box[1]), box
            elif c["size"] == "source":
                size, (ow, oh) = ("source",), (info["width"], info["height"])
            else:   # 768 short edge, also the fallback when no canvas size is wired
                size = ("edge", 768)
                s = min(1.0, 768.0 / min(info["width"], info["height"]))
                ow, oh = int(round(info["width"] * s)), int(round(info["height"] * s))
                ow, oh = max(2, ow - ow % 2), max(2, oh - oh % 2)   # media_io._target_size's even rule
            cost = clip_bytes(-(-frames // c["nth"]), ow, oh, c["precision"])
            if cost > cap:
                raise RuntimeError(
                    f"[Luna Asset Loader] Clip V{k} ({c['file']}) would need {cost / 1024 ** 3:.1f} GB as "
                    f"{frames} frames at {ow}x{oh} {c['precision']} — more than the {cap / 1024 ** 3:g} GB "
                    f"this node allows (⚙ Memory cap). Shorten it, use fp16 or a smaller size, or raise the cap"
                    + ("." if grid != "free" else ", or take every 2nd frame."))
            batch, got = decode_clip(path, c["start"], frames, fps, size, c["fit"], c["nth"], c["precision"], grid)
            sound = clip_soundtrack(path, got["start"], got["seconds"]) if c["sound"] == "keep" else None
            line = (f"{got['name']} from {_clock(got['start'])}, {got['frames']} frames "
                    f"({got['seconds']:.2f} s) at {got['fps']:g} fps, {got['width']}x{got['height']}")
            how = {"canvas": c["fit"] if box else "768 short edge", "edge": "768 short edge", "source": "as filmed"}[c["size"]]
            line += f" (from {got['source_size'][0]}x{got['source_size'][1]} at {got['source_fps']:g} fps, {how})"
            if got["short"]:
                line += f"; the clip ran out, so {got['frames'] * got['nth']} of the {frames} frames asked for"
            out.append({"batch": batch, "sound": sound, "info": got, "line": line})
        return out

    @staticmethod
    def _song(cards, seconds, shot=None):
        """Sound card 1 -> (AUDIO or None, info dict or None, one brief line)."""
        if not cards:
            return None, None, ""
        c = cards[0]
        path = _media_file(c["file"])
        if not path:
            raise RuntimeError(f"[Luna Asset Loader] Song not found in the input folder: {c['file']}")
        wired = seconds is not None and float(seconds) > 0
        want = float(seconds) if wired else c["duration"]
        start, describe, n = c["start"], None, None
        if c["position"] == "shot":
            if want <= 0:
                raise RuntimeError(
                    "[Luna Asset Loader] 'By shot number' needs a shot length: wire `seconds` "
                    "or give the sound card a Duration.")
            n = int(shot) if shot is not None and int(shot) > 0 else c["shot"]
            try:
                start = song_shot_start(c["song_start"], n, want, c["overlap"])
            except ValueError as e:
                raise RuntimeError(f"[Luna Asset Loader] {e} Lower the overlap.") from None

            def describe(total_s, _n=n):
                count = song_shot_count(total_s, c["song_start"], want, c["overlap"])
                return (f"[Luna Asset Loader] Shot {_n} would start at {_clock(start)}, after "
                        f"{c['file']} ends ({_clock(total_s)}). This song has {count} shot(s) of "
                        f"{want:.2f} s with a {c['overlap']}-frame overlap, starting at "
                        f"{_clock(c['song_start'])}.")
        audio, info = load_audio_window(path, start, want, c["fill"], describe)
        info["wired"] = wired
        line = (f"Song: {info['name']} {_clock(info['start'])}-{_clock(info['start'] + info['seconds'])} "
                f"({info['seconds']:.2f} s).")
        if n is not None:
            info["shot"] = n
            info["shots"] = song_shot_count(info["total"], c["song_start"], want, c["overlap"])
            info["overlap"] = c["overlap"]
            line = (f"Song: {info['name']}, shot {n} of {info['shots']}, "
                    f"{_clock(info['start'])}-{_clock(info['start'] + info['seconds'])} "
                    f"({info['seconds']:.2f} s"
                    + (f", sharing its first {c['overlap']} frames with shot {n - 1}" if n > 1 and c["overlap"] else "")
                    + ").")
        if info["filled"] > 0.0005:
            line += (f" The file ran out after {info['taken']:.2f} s; the last {info['filled']:.2f} s "
                     f"{'loop back to its start' if info['mode'] == 'loop' else 'are silence'}.")
            print(f"[Luna Asset Loader] {line}")
        return audio, info, line

    @staticmethod
    def _continuation(cont, cards, song, width, height, previous_frames, settings=None):
        """The end of the previous shot -> (timeline item at frame 0, brief line), or (None, "").

        As many frames as the song's overlap when the song is cut by shot number, so
        sound and picture overlap by the same amount at every cut; otherwise the
        count stored on the continuation. Shot 1 has nothing before it."""
        if not cont["on"]:
            return None, ""
        if song and song.get("shot") == 1:
            return None, "shot 1: no continuation (nothing comes before it)"
        n = 1 if cont["take"] == "last" else (song["overlap"] if song and song.get("shot") else cont["frames"])
        n = max(1, int(n))
        if cont["from"] == "input":
            if previous_frames is None:
                raise RuntimeError("[Luna Asset Loader] The continuation's source is 'Input', but "
                                   "previous_frames is not wired.")
            tail = previous_frames[-n:]
            if n > 1 and tail.shape[0] < n:
                raise RuntimeError(f"[Luna Asset Loader] previous_frames has {tail.shape[0]} frame(s); "
                                   f"the continuation needs {n}.")
            name, src = "previous_frames", "the previous_frames input"
        else:
            path = _output_newest(cont["folder"]) if cont["from"] == "folder" else _media_file(cont["file"])
            if not path:
                where = (f"the output folder '{cont['folder'] or '(output)'}'" if cont["from"] == "folder"
                         else f"the input folder ('{cont['file']}')")
                raise RuntimeError(f"[Luna Asset Loader] The continuation found no video in {where}.")
            info = probe_media(path)
            box = (int(width), int(height)) if width and height and int(width) > 0 and int(height) > 0 else None
            size = ("box", box[0], box[1]) if box else ("edge", 768)
            target = (settings or {}).get("target", "h3")
            fps = target_fps(target, info.get("fps")) if n > 1 else (info.get("fps") or FPS)
            tail, got = decode_clip(path, tail_start(info.get("duration", 0.0), fps, n, info.get("fps")), n, fps,
                                    size, "crop", 1, "fp32", target_grid(target) if n > 1 else "free")
            if n > 1 and got["frames"] < n:
                raise RuntimeError(f"[Luna Asset Loader] {got['name']} gave {got['frames']} frame(s) for the "
                                   f"continuation; it needs {n}.")
            tail = tail[-n:]
            name, src = got["name"], got["name"]
        if n == 1:
            return ({"kind": "picture", "card": "continuation", "at": 0, "file": name, "image": tail[-1:]},
                    f"frame 0: the last frame of {src} (continuation)")
        return ({"kind": "video", "card": "continuation", "at": 0, "file": name, "frames": tail, "audio": None},
                f"frames 0-{n - 1}: the last {n} frames of {src} (continuation — the motion carries on)")

    @staticmethod
    def _sounds(cards):
        """Sound cards 2-3 that are references or guides -> {index: (AUDIO, description)}.
        Cut to their window, never filled: a reference ends where it ends."""
        out = {}
        for j, c in enumerate(cards):
            # Sound 1 as a guide or locked uses the song window (`audio`); as a
            # reference it is loaded here like any other reference sound.
            if c["role"] not in ("ref", "guide") or (j == 0 and c["role"] != "ref"):
                continue
            path = _media_file(c["file"])
            if not path:
                raise RuntimeError(f"[Luna Asset Loader] Sound not found in the input folder: {c['file']}")
            clip, info = load_audio(path, c["start"], c["duration"])
            out[j] = (clip, f"{info['name']} {_clock(info['start'])}-{_clock(info['start'] + info['seconds'])} "
                            f"({info['seconds']:.2f} s)")
        return out

    @staticmethod
    def _shot_lines(pic, clips, decoded, cards, song):
        """What sits on the shot, in frame order, in words."""
        rows = []
        for i, p in enumerate(pic):
            if p["role"] == "key":
                rows.append((p["at"], f"frame {p['at']}: picture card {i + 1} as a keyframe"))
        for k, (c, d) in enumerate(zip(clips, decoded)):
            if c["role"] == "guide":
                n = int(d["batch"].shape[0])
                rows.append((c["at"], f"frames {c['at']}-{c['at'] + n - 1}: clip V{k + 1} ({d['info']['name']})"
                                      + (" with its sound" if d["sound"] is not None else "")))
        for j, c in enumerate(cards):
            if c["role"] == "lock":
                rows.append((c["at"], f"from frame {c['at']}: sound A{j + 1} locked — the picture follows it"))
            elif c["role"] == "guide":
                rows.append((c["at"], f"from frame {c['at']}: sound A{j + 1} as a guide"))
        return [text for _, text in sorted(rows, key=lambda r: r[0])]

    @staticmethod
    def _timeline(shot_len, pic, frames, clips, decoded, cards, extra_sounds, audio, song):
        """Everything placed on the shot, with its frames/sound attached, for a node
        that applies it (guides, the locked song). Frames are at H3's 24 fps."""
        items = []
        for i, p in enumerate(pic):
            if p["role"] == "key":
                items.append({"kind": "picture", "card": i + 1, "at": p["at"], "image": frames[i]})
        for k, (c, d) in enumerate(zip(clips, decoded)):
            if c["role"] == "guide":
                items.append({"kind": "video", "card": k + 1, "at": c["at"], "file": d["info"]["name"],
                              "frames": d["batch"], "audio": d["sound"]})
        for j, c in enumerate(cards):
            if c["role"] not in ("lock", "guide"):
                continue
            item = {"kind": "audio", "role": c["role"], "card": j + 1, "at": c["at"], "file": c["file"],
                    "audio": audio if j == 0 else extra_sounds[j][0]}
            if j == 0 and song:
                item.update({"start": round(song["start"], 4), "seconds": round(song["seconds"], 4)})
                if song.get("shot") is not None:
                    item.update({"shot": song["shot"], "shots": song["shots"], "overlap_frames": song["overlap"]})
            items.append(item)
        items.sort(key=lambda it: it["at"])
        return {"version": 2, "fps": FPS, "frames": shot_len, "items": items}


def _inside(root_dir: str, rel: str, kind: str = "file"):
    """`rel` resolved inside `root_dir`, or None. The name is screened BEFORE
    anything touches the disk: on Windows merely resolving \\\\host\\share opens
    SMB, and the routes and /prompt take any caller's input. A junction or link
    that leads outside the folder (even onto another drive) is refused too."""
    if not isinstance(rel, str) or "\x00" in rel:
        return None
    if rel and (os.path.isabs(rel) or rel.startswith(("\\", "/")) or ":" in rel
                or ".." in rel.replace("\\", "/").split("/")):
        return None
    root = os.path.realpath(root_dir)
    path = os.path.realpath(os.path.join(root, rel))
    try:
        if os.path.commonpath([root, path]) != root:
            return None
    except ValueError:   # different drives: certainly not inside
        return None
    ok = os.path.isfile(path) if kind == "file" else os.path.isdir(path)
    return path if ok else None


def _input_file(name: str):
    """A file name from the browser -> a real file inside ComfyUI's input folder, or None."""
    if not name or not isinstance(name, str):
        return None
    return _inside(folder_paths.get_input_directory(), strip_annotation(name)[0])


def _media_file(name: str):
    """A sound or clip named in media_state -> a real file, or None. Plain names live
    in the input folder; a trailing ' [output]' / ' [temp]' tag (ComfyUI's own
    annotation) selects those folders. Nothing outside them is ever read."""
    if not name or not isinstance(name, str):
        return None
    bare, tag = strip_annotation(name)
    root = {"output": folder_paths.get_output_directory(),
            "temp": folder_paths.get_temp_directory()}.get(tag, folder_paths.get_input_directory())
    return _inside(root, bare)


def _output_newest(folder: str):
    """The newest video in a folder under ComfyUI's output folder ('' = the output
    folder itself), or None. The folder name is screened like _input_file's."""
    base = _inside(folder_paths.get_output_directory(), (folder or "").strip().strip("/\\"), "dir")
    if not base:
        return None
    files = [(n, os.path.getmtime(os.path.join(base, n))) for n in os.listdir(base)
             if os.path.isfile(os.path.join(base, n))]
    name = newest_video(files)
    return os.path.join(base, name) if name else None


import asyncio

try:
    from aiohttp import web
    from server import PromptServer
except ImportError:   # imported outside ComfyUI (tests): no routes
    PromptServer = None

if PromptServer is not None:
    @PromptServer.instance.routes.get("/lunasave/media-info")
    async def _luna_media_info(request):
        """Size, frame rate, length and sound of a clip, for the video card."""
        path = _input_file(request.query.get("file", ""))
        if not path:
            return web.json_response({"error": "not found"}, status=404)
        try:
            # Decoding off the event loop: a long file must not stall the whole server.
            return web.json_response(await asyncio.get_running_loop().run_in_executor(None, probe_media, path))
        except Exception as e:
            return web.json_response({"error": f"cannot read: {type(e).__name__}"}, status=415)

    @PromptServer.instance.routes.get("/lunasave/newest-video")
    async def _luna_newest(request):
        """Which video the continuation would take from an output folder, right now."""
        path = _output_newest(request.query.get("folder", ""))
        if not path:
            return web.json_response({"name": None})
        info = {"name": os.path.basename(path), "mtime": os.path.getmtime(path)}
        try:
            pm = await asyncio.get_running_loop().run_in_executor(None, probe_media, path)
            info.update({k: v for k, v in pm.items() if k in ("duration", "fps", "width", "height")})
        except Exception:
            pass
        return web.json_response(info)

    @PromptServer.instance.routes.get("/lunasave/filmstrip")
    async def _luna_filmstrip(request):
        """Evenly spaced frames side by side, as one JPEG, for the film strip."""
        path = _input_file(request.query.get("file", ""))
        if not path:
            return web.Response(status=404)
        try:
            n = int(request.query.get("n", "12"))
        except ValueError:
            n = 12
        try:
            data = await asyncio.get_running_loop().run_in_executor(None, filmstrip_jpeg, path, n)
        except Exception:
            return web.Response(status=415)
        return web.Response(body=data, content_type="image/jpeg",
                            headers={"Cache-Control": "max-age=3600"})


NODE_CLASS_MAPPINGS = {"LunaAssetLoader": LunaAssetLoader}
NODE_DISPLAY_NAME_MAPPINGS = {"LunaAssetLoader": "Luna Asset Loader"}
