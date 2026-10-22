"""Luna Load Video — upload or pick a video, watch it on the node, load it as a
frame batch plus its sound and the numbers about it.

Derived from Load Video Pixaroma (ComfyUI-Pixaroma, MIT, (c) 2026 pixaroma,
nodes/node_load_video.py + js/load_video/index.js). Kept from it: the job, the seven
outputs and their order (video_frames, audio, frame_count, fps, width, height,
duration), a player on the node that plays the source before any run, one side set
= scale keeping the shape. Changed here:
  * decoding is this pack's own media_io.decode_clip (streams into one preallocated
    tensor), not Pixaroma's helpers;
  * the window is a start in SECONDS plus a frame count (Pixaroma: skip N frames,
    load the first M);
  * both sides set = a fit of your choice (crop / pad / stretch), not crop only;
  * frame grid (H3 17k+5 at 24 fps, LTX 8k+1), every Nth frame, sound keep/drop,
    fp16/fp32 and a memory cap that refuses before decoding — those five sit in the
    node's ⚙ panel; the everyday ones are on the face and fold with the chevron;
  * the face shows what the run will load (frames, size, time, memory) beforehand,
    from the same plan the run uses (media_io.plan_load).
2026-10-22: three sources (Peter's ask, after VHS Load Video (Path) / Load Images
(Path), GPL-3.0, read only — nothing taken from their code): the picked/uploaded
file, a typed or wired path or http(s) link (a link is downloaded once into
input/luna_downloads), or a folder with a video count. Every output is a list, so a
folder gives one downstream run per video, each at its own size and length; a
single video is a list of one and behaves as before. New last output `video`: the
file untouched, as ComfyUI's VIDEO.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import urllib.request

import folder_paths

from .asset_loader import _input_file
from .media_io import (clean_path, clip_soundtrack, decode_clip, download_name, folder_videos, is_url,
                       plan_load, probe_media)

NODE = "Luna Load Video"
GRIDS = {"free": "free", "H3 (24 fps, 17k+5)": "h3", "LTX (8k+1)": "ltx"}
SOURCES = ["upload", "path / URL", "folder"]
DOWNLOADS = "luna_downloads"            # subfolder of ComfyUI's input folder
MAX_DOWNLOAD = 8 * 1024 ** 3            # a link larger than this is refused

try:   # ComfyUI's own VIDEO type, for the untouched `video` output
    from comfy_api.latest import InputImpl as _InputImpl
except Exception:   # outside ComfyUI (tests) or an older core
    _InputImpl = None


def _videos():
    input_dir = folder_paths.get_input_directory()
    os.makedirs(input_dir, exist_ok=True)
    try:
        files = folder_paths.filter_files_content_types(os.listdir(input_dir), ["video"])
    except Exception:
        files = []
    return sorted(files)


def _beside_input(path: str) -> str:
    """A relative path is read from ComfyUI's input folder; an absolute one as it is."""
    path = os.path.expanduser(clean_path(path))
    return path if os.path.isabs(path) else os.path.join(folder_paths.get_input_directory(), path)


def _download(url: str) -> str:
    """A web link -> a file in input/luna_downloads, fetched once (the name carries a
    hash of the whole link). Written to a .part file first, so a broken download never
    passes for a video."""
    url = url.strip()
    folder = os.path.join(folder_paths.get_input_directory(), DOWNLOADS)
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, download_name(url))
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return dest
    part = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ComfyUI Luna Load Video)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as fh:
            size = int(r.headers.get("Content-Length") or 0)
            if size > MAX_DOWNLOAD:
                raise RuntimeError(f"the file is {size / 1e9:.1f} GB, over the {MAX_DOWNLOAD / 1e9:.0f} GB limit")
            got = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                got += len(chunk)
                if got > MAX_DOWNLOAD:
                    raise RuntimeError(f"the download passed the {MAX_DOWNLOAD / 1e9:.0f} GB limit")
                fh.write(chunk)
        shutil.move(part, dest)
    except Exception as e:
        if os.path.exists(part):
            os.remove(part)
        raise RuntimeError(f"[{NODE}] Could not download {url}: {e}") from None
    return dest


def _sources(source, video="", path="", folder="", video_count=0, fetch=True) -> list:
    """The video file(s) this run loads, in order. `fetch=False` never downloads (for
    IS_CHANGED / VALIDATE_INPUTS): a link is then returned as the link itself."""
    if source == "path / URL":
        text = clean_path(path)
        if not text:
            raise RuntimeError(f"[{NODE}] Source is 'path / URL' but no path or link is given.")
        if is_url(text):
            return [_download(text) if fetch else text]
        full = _beside_input(text)
        if not os.path.isfile(full):
            raise RuntimeError(f"[{NODE}] File not found: {full}")
        return [full]
    if source == "folder":
        text = clean_path(folder)
        if not text:
            raise RuntimeError(f"[{NODE}] Source is 'folder' but no folder is given.")
        full = _beside_input(text)
        if not os.path.isdir(full):
            raise RuntimeError(f"[{NODE}] Folder not found: {full}")
        names = folder_videos([n for n in os.listdir(full) if os.path.isfile(os.path.join(full, n))], video_count)
        if not names:
            raise RuntimeError(f"[{NODE}] No video files in {full}.")
        return [os.path.join(full, n) for n in names]
    if not video:
        raise RuntimeError(f"[{NODE}] No video selected — upload one or pick one from the list.")
    full = folder_paths.get_annotated_filepath(video)
    if not full or not os.path.isfile(full):
        raise RuntimeError(f"[{NODE}] File not found: {video}")
    return [full]


def _plan(src, start, frames, fps, width, height, fit, frame_grid, every_nth, precision):
    return plan_load(src, start, frames, fps, width, height, fit, GRIDS.get(frame_grid, "free"),
                     every_nth, precision)


def _summary(plan: dict, cap_gb: float) -> dict:
    gb = plan["bytes"] / 1e9
    return {"frames": plan["delivered"], "fps": plan["out_fps"], "width": plan["width"],
            "height": plan["height"], "seconds": plan["seconds"], "gb": gb,
            "over": gb > cap_gb, "cap_gb": cap_gb, "notes": plan["notes"], "source": plan["source"]}


class LunaLoadVideo:
    DESCRIPTION = (
        "Load a video as a batch of frames, with its sound and its numbers. Upload or pick "
        "a file and it plays on the node straight away; the line under the player says what "
        "a run will load (frames, size, length, memory) before you run.\n\n"
        "source picks where videos come from: upload (the list and the upload button), "
        "path / URL (a path on this PC, or an http(s) link downloaded once into "
        "input/luna_downloads), or folder (its videos in name order, up to video_count; "
        "everything after this node then runs once per video).\n\n"
        "On the node: where to start (seconds), how many frames (0 = to the end), the frame "
        "rate (0 = the file's own), and a size — one side set scales keeping the shape, "
        "both sides fit that box by crop, pad or stretch. The chevron folds these away.\n\n"
        "In ⚙: a frame grid (H3: 24 fps and 17k+5 frames; LTX: 8k+1), every Nth frame, keep "
        "or drop the sound, fp32/fp16, and a memory cap that refuses an oversized load "
        "before decoding.\n\n"
        "The sound is cut to exactly the loaded frames' time. The first seven outputs match "
        "Load Video Pixaroma's, in the same order; `video` is the file itself, untouched, "
        "for VIDEO nodes such as Save Video."
    )
    CATEGORY = "Luna/Load"
    FUNCTION = "load"

    # `video` is appended LAST: saved workflows link outputs by slot number.
    RETURN_TYPES = ("IMAGE", "AUDIO", "INT", "FLOAT", "INT", "INT", "FLOAT", "VIDEO")
    RETURN_NAMES = ("video_frames", "audio", "frame_count", "fps", "width", "height", "duration", "video")
    # Lists, so a folder runs everything downstream once per video. One video = a
    # list of one, which ComfyUI treats exactly like a plain value.
    OUTPUT_IS_LIST = (True,) * 8
    OUTPUT_TOOLTIPS = (
        "The video as a batch of frames, after start, length, frame rate, grid and size.",
        "The video's sound for exactly the loaded frames. None when the file has no sound "
        "or Sound is set to Drop in ⚙.",
        "How many frames were loaded.",
        "Frames per second of the loaded frames (the frame rate set here, divided by Every Nth).",
        "Frame width in pixels, after any resize.",
        "Frame height in pixels, after any resize.",
        "Length of the loaded part in seconds.",
        "The video file itself, untouched, as ComfyUI's VIDEO: whole file, original size, "
        "frame rate and sound; start, frames, fps and size do not apply. For Save Video, "
        "Get Video Components and other VIDEO nodes.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "source": (SOURCES, {
                "default": "upload",
                "tooltip": "Where the video comes from. upload: the file picked below (or "
                           "uploaded). path / URL: a path on this PC or an http(s) link "
                           "(downloaded once into input/luna_downloads). folder: every video in a "
                           "folder, up to video_count; everything after this node then runs once "
                           "per video."}),
            # No "video_upload": the frontend would add a second player of its own.
            # The upload button and drag-and-drop come from js/luna_load_video.js.
            "video": (_videos(), {
                "tooltip": "The video, from ComfyUI's input folder. Upload one, drag a file onto "
                           "the node, or pick from the list. Used when source is upload."}),
            "path": ("STRING", {
                "default": "",
                "tooltip": "Used when source is 'path / URL': a video file path (D:\\clips\\a.mp4; a "
                           "relative path is read from the input folder) or an http(s) link to a "
                           "video file. Quotes from 'Copy as path' are fine. Wire a STRING here to "
                           "drive it from another node."}),
            "folder": ("STRING", {
                "default": "",
                "tooltip": "Used when source is 'folder': a folder path (relative = inside the input "
                           "folder). Its videos load in name order (clip2 before clip10)."}),
            "video_count": ("INT", {
                "default": 0, "min": 0, "max": 1000, "step": 1,
                "tooltip": "Used when source is 'folder': how many videos to load, from the first in "
                           "name order. 0 = all of them."}),
            "start": ("FLOAT", {
                "default": 0.0, "min": 0.0, "max": 86400.0, "step": 0.01,
                "tooltip": "Seconds into the file where loading starts. 0 = the beginning. The "
                           "sound starts at the same point."}),
            "frames": ("INT", {
                "default": 0, "min": 0, "max": 100000, "step": 1,
                "tooltip": "How many frames to load, counted at the frame rate below. 0 = to the "
                           "end of the file. With a frame grid in ⚙ it lands on the nearest "
                           "count the grid allows."}),
            "fps": ("FLOAT", {
                "default": 0.0, "min": 0.0, "max": 240.0, "step": 1.0,
                "tooltip": "Frame rate to load at, by dropping or repeating frames so motion stays "
                           "in real time. 0 = the file's own rate. The H3 grid in ⚙ needs 0 or 24."}),
            "width": ("INT", {
                "default": 0, "min": 0, "max": 8192, "step": 2,
                "tooltip": "Resize as frames load. 0 = keep. Only width set = scale to it keeping "
                           "the shape. Width and height both set = fit that box (see fit)."}),
            "height": ("INT", {
                "default": 0, "min": 0, "max": 8192, "step": 2,
                "tooltip": "Resize as frames load. 0 = keep. Only height set = scale to it keeping "
                           "the shape. Width and height both set = fit that box (see fit)."}),
            "fit": (["crop", "pad", "stretch"], {
                "default": "crop",
                "tooltip": "Only when width AND height are set. crop: fill the box, cut the "
                           "overflow. pad: fit inside, black bars. stretch: distort to the box."}),
            # ⚙ panel — hidden on the face, edited in the settings panel.
            "frame_grid": (list(GRIDS), {
                "default": "free",
                "tooltip": "Frame counts a model accepts. H3: 24 fps and 5, 22, 39 … frames "
                           "(17k+5). LTX: 1, 9, 17 … (8k+1). free: any count."}),
            "every_nth": ("INT", {
                "default": 1, "min": 1, "max": 100, "step": 1,
                "tooltip": "Keep every Nth loaded frame. 1 = all. The fps output divides by it."}),
            "audio": (["keep", "drop"], {
                "default": "keep",
                "tooltip": "keep: the sound for exactly the loaded frames. drop: no sound out."}),
            "precision": (["fp32", "fp16"], {
                "default": "fp32",
                "tooltip": "fp32 is what every node expects. fp16 halves the memory; use it only "
                           "when the next node accepts half-precision frames."}),
            "memory_cap_gb": ("FLOAT", {
                "default": 6.0, "min": 0.5, "max": 128.0, "step": 0.5,
                "tooltip": "A load that would need more memory than this is refused before "
                           "decoding, with the numbers. Lower frames, size or use fp16."}),
        }}

    def load(self, source="upload", video="", path="", folder="", video_count=0, start=0.0, frames=0,
             fps=0.0, width=0, height=0, fit="crop", frame_grid="free", every_nth=1, audio="keep",
             precision="fp32", memory_cap_gb=6.0):
        files = _sources(source, video, path, folder, video_count)

        # Every file planned (and the memory summed) before any is decoded: a folder
        # that would not fit is refused whole, not after filling memory with half of it.
        plans = []
        for f in files:
            src = probe_media(f)
            if not src.get("video"):
                raise RuntimeError(f"[{NODE}] {os.path.basename(f)} has no video stream.")
            try:
                plans.append(_plan(src, start, frames, fps, width, height, fit, frame_grid, every_nth, precision))
            except ValueError as e:
                raise RuntimeError(f"[{NODE}] {os.path.basename(f)}: {e}.") from None
        total = sum(p["bytes"] for p in plans) / 1e9
        if total > float(memory_cap_gb):
            what = (f"{plans[0]['delivered']} frames at {plans[0]['width']}x{plans[0]['height']} {precision}"
                    if len(plans) == 1 else f"{len(plans)} videos")
            raise RuntimeError(
                f"[{NODE}] {what} need {total:.2f} GB, over the {memory_cap_gb:g} GB memory cap "
                f"(settings). Load fewer frames or videos, a smaller size, fp16, or raise the cap.")

        grid = GRIDS.get(frame_grid, "free")
        outs = {k: [] for k in ("frames", "audio", "count", "fps", "width", "height", "seconds", "video")}
        lines = []
        for f, plan in zip(files, plans):
            out, info = decode_clip(f, start, plan["frames"], plan["fps"], plan["size"], plan["fit"],
                                    every_nth, precision, grid, who=NODE)
            sound = clip_soundtrack(f, info["start"], info["seconds"]) if audio == "keep" else None
            count = int(out.shape[0])
            line = (f"{os.path.basename(f)}: {count} frames @ {info['fps']:g} fps, "
                    f"{info['width']}x{info['height']}, {info['seconds']:.2f} s"
                    f"{' + sound' if sound is not None else ''}")
            if info["short"]:
                line += f" (file ended early: asked {info['asked']})"
            print(f"[{NODE}] {line}")
            lines.append(line)
            for k, v in (("frames", out), ("audio", sound), ("count", count), ("fps", float(info["fps"])),
                         ("width", int(info["width"])), ("height", int(info["height"])),
                         ("seconds", float(info["seconds"])),
                         ("video", _InputImpl.VideoFromFile(f) if _InputImpl else None)):
                outs[k].append(v)
        return {"ui": {"luna_load_video": lines},
                "result": tuple(outs[k] for k in ("frames", "audio", "count", "fps", "width", "height",
                                                  "seconds", "video"))}

    @classmethod
    def IS_CHANGED(cls, source="upload", video="", path="", folder="", video_count=0, **kwargs):
        try:
            files = _sources(source, video, path, folder, video_count, fetch=False)
        except Exception:
            return float("nan")
        sig = []
        for f in files:
            if is_url(f):
                sig.append(f)           # the same link is the same download
                continue
            st = os.stat(f)
            sig.append(f"{f}:{st.st_mtime_ns}:{st.st_size}")
        return "|".join(sig)

    @classmethod
    def VALIDATE_INPUTS(cls, source="upload", video="", path="", folder="", video_count=0, **kwargs):
        if source not in SOURCES:
            return f"Unknown source: {source}"
        if source == "upload":
            if not video:
                return "No video selected."
            if not folder_paths.exists_annotated_filepath(video):
                return f"Video not found: {video}"
        elif source == "path / URL" and not clean_path(path):
            return "Source is 'path / URL' but no path or link is given."
        elif source == "folder" and not clean_path(folder):
            return "Source is 'folder' but no folder is given."
        return True


try:
    from aiohttp import web
    from server import PromptServer
except ImportError:   # imported outside ComfyUI (tests): no routes
    PromptServer = None

if PromptServer is not None:
    @PromptServer.instance.routes.get("/lunasave/load-video-plan")
    async def _luna_load_video_plan(request):
        """What a run would load with these settings — the same plan the run uses."""
        q = request.query
        path = _input_file(q.get("file", ""))
        if not path:
            return web.json_response({"error": "file not found"}, status=404)
        try:
            src = await asyncio.get_running_loop().run_in_executor(None, probe_media, path)
        except Exception as e:
            return web.json_response({"error": f"cannot read: {type(e).__name__}"}, status=415)
        if not src.get("video"):
            return web.json_response({"error": "no video stream"})

        def num(key, kind, default):
            try:
                return kind(q.get(key, default))
            except (TypeError, ValueError):
                return default
        try:
            plan = _plan(src, num("start", float, 0.0), num("frames", int, 0), num("fps", float, 0.0),
                         num("width", int, 0), num("height", int, 0), q.get("fit", "crop"),
                         q.get("frame_grid", "free"), num("every_nth", int, 1), q.get("precision", "fp32"))
        except ValueError as e:
            return web.json_response({"error": str(e), "source": src})
        return web.json_response(_summary(plan, num("memory_cap_gb", float, 6.0)))


NODE_CLASS_MAPPINGS = {"LunaLoadVideo": LunaLoadVideo}
NODE_DISPLAY_NAME_MAPPINGS = {"LunaLoadVideo": "Luna Load Video"}
