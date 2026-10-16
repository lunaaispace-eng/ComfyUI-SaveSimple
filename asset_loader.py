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

from .media_io import FPS, load_audio_window

MAX_IMAGES = 9  # MiniMax H3's own reference ceiling
MAX_SOUNDS = 3  # MiniMax H3 takes three standalone sounds

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
        cards.append({
            "file": str(c["file"]),
            "start": max(0.0, float(c.get("start") or 0.0)),
            "duration": max(0.0, float(c.get("duration") or 0.0)),
            "fill": "loop" if c.get("fill") == "loop" else "silence",
        })
    return {"audio": cards}


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
        "(Luna Agent Chat, LLM Prompt) which flatten it to individual JPEGs anyway.",
        "Image 1's width AFTER its resize, for driving the generation nodes.",
        "Image 1's height AFTER its resize.",
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
            cards = _parse_media(media_state)["audio"]
        except RuntimeError:
            cards = []
        for c in cards:
            resolved = folder_paths.get_annotated_filepath(c["file"])
            if resolved and os.path.isfile(resolved):
                s = os.stat(resolved)
                m.update(f"{c['file']}|{s.st_size}|{s.st_mtime_ns}".encode("utf-8"))
        return m.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, image_paths, image_count, **kwargs):
        paths = _split_paths(image_paths)
        if len(paths) > MAX_IMAGES:
            return (f"MiniMax H3 takes at most {MAX_IMAGES} reference images, "
                    f"but {len(paths)} lines are listed.")
        return True

    def load(self, image_paths, image_count, asset_state="", media_state="", seconds=None):
        paths = _split_paths(image_paths)
        cards = _parse_media(media_state)["audio"]
        if not paths and not cards:
            raise RuntimeError(
                "[Luna Asset Loader] Nothing loaded. Press Upload and add pictures or a song."
            )

        audio, song, song_line = self._song(cards, seconds)
        if not paths:
            # A song on its own is a real use (the picture comes from elsewhere), so
            # this is not an error — but the picture outputs stay empty, never black.
            brief = song_line
            refs = {"images": [], "videos": [], "video_audios": [], "audios": [],
                    "brief": brief, "width": 0, "height": 0}
            print(f"[Luna Asset Loader] no pictures; {song_line}")
            return {"ui": {"luna_asset_audio": [song]},
                    "result": (None, 0, 0, brief, audio, refs, self._timeline(song, seconds))
                    + (None,) * MAX_IMAGES}

        states = _parse_state(asset_state, len(paths))
        loaded = [_load(p, st) for p, st in zip(paths, states)]
        frames = [f for f, _ in loaded]
        originals = [o for _, o in loaded]
        dims = [(int(f.shape[2]), int(f.shape[1])) for f in frames]  # (w, h) as delivered

        lines = []
        for i, ((w, h), (ow, oh)) in enumerate(zip(dims, originals)):
            entry = f"<Picture {i + 1}> = {_describe_ar(w, h)}"
            if (w, h) != (ow, oh):
                # Say what it was as well as what it became. A prompt writer told
                # only the resized number cannot tell a deliberate crop from an
                # accident, and neither can you reading it back later.
                entry += f" [resized from {ow}x{oh}]"
            lines.append(entry)
        brief = "Reference images, in order: " + "; ".join(lines) + "."

        # FL2VA forces both frames to the exact generation size — the first with
        # crop disabled, so a mismatched aspect is STRETCHED, and the last with a
        # centre crop, so it is CUT. Neither errors, so say it here or nobody
        # finds out until they watch the render.
        # Relative, not absolute: snapping to a /32 grid moves the aspect ratio by
        # up to ~1% by itself, so a tight absolute threshold would warn on every
        # snapped pair. 2% is above that noise floor and still catches a stretch
        # you would see.
        r0 = dims[0][0] / dims[0][1] if len(dims) >= 1 else 0
        r1 = dims[1][0] / dims[1][1] if len(dims) >= 2 else 0
        if len(dims) >= 2 and abs(r0 - r1) / max(r0, r1) > 0.02:
            warn = (f"WARNING: <Picture 1> and <Picture 2> have different aspect ratios "
                    f"({_describe_ar(*dims[0])} vs {_describe_ar(*dims[1])}). Fine for "
                    f"REF2VA, which keeps each aspect. In FL2VA the first frame gets "
                    f"stretched and the last centre-cropped.")
            print(f"[Luna Asset Loader] {warn}")
            brief += " " + warn

        numbered: list = [frames[i] if i < len(frames) else None for i in range(MAX_IMAGES)]
        w, h = dims[0]
        if song_line:
            brief += " " + song_line
        refs = {"images": frames, "videos": [], "video_audios": [], "audios": [],
                "brief": brief, "width": w, "height": h}
        print(f"[Luna Asset Loader] {len(frames)} image(s), showing {image_count} output(s); "
              f"<Picture 1> = {w}x{h}" + (f"; {song_line}" if song_line else ""))
        result = (_conform(frames), w, h, brief, audio, refs, self._timeline(song, seconds)) \
            + tuple(numbered)
        return {"ui": {"luna_asset_audio": [song] if song else []}, "result": result}

    @staticmethod
    def _song(cards, seconds):
        """Sound card 1 -> (AUDIO or None, info dict or None, one brief line)."""
        if not cards:
            return None, None, ""
        c = cards[0]
        path = folder_paths.get_annotated_filepath(c["file"])
        if not path or not os.path.isfile(path):
            raise RuntimeError(f"[Luna Asset Loader] Song not found in the input folder: {c['file']}")
        wired = seconds is not None and float(seconds) > 0
        want = float(seconds) if wired else c["duration"]
        audio, info = load_audio_window(path, c["start"], want, c["fill"])
        info["wired"] = wired
        line = (f"Song: {info['name']} {_clock(info['start'])}-{_clock(info['start'] + info['seconds'])} "
                f"({info['seconds']:.2f} s).")
        if info["filled"] > 0.0005:
            line += (f" The file ran out after {info['taken']:.2f} s; the last {info['filled']:.2f} s "
                     f"{'loop back to its start' if info['mode'] == 'loop' else 'are silence'}.")
            print(f"[Luna Asset Loader] {line}")
        return audio, info, line

    @staticmethod
    def _timeline(song, seconds):
        """Placements on the shot, in frames at H3's 24 fps. v1 holds only the song."""
        items = []
        if song:
            items.append({"kind": "audio", "role": "lock", "at": 0, "file": song["name"],
                          "start": round(song["start"], 4), "seconds": round(song["seconds"], 4)})
        shot = float(seconds) if seconds is not None and float(seconds) > 0 else None
        return {"version": 1, "fps": FPS,
                "frames": int(round(shot * FPS)) if shot else None, "items": items}


NODE_CLASS_MAPPINGS = {"LunaAssetLoader": LunaAssetLoader}
NODE_DISPLAY_NAME_MAPPINGS = {"LunaAssetLoader": "Luna Asset Loader"}
