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
"""

from __future__ import annotations

import asyncio
import os

import folder_paths

from .asset_loader import _input_file
from .media_io import clip_soundtrack, decode_clip, plan_load, probe_media

NODE = "Luna Load Video"
GRIDS = {"free": "free", "H3 (24 fps, 17k+5)": "h3", "LTX (8k+1)": "ltx"}


def _videos():
    input_dir = folder_paths.get_input_directory()
    os.makedirs(input_dir, exist_ok=True)
    try:
        files = folder_paths.filter_files_content_types(os.listdir(input_dir), ["video"])
    except Exception:
        files = []
    return sorted(files)


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
        "On the node: where to start (seconds), how many frames (0 = to the end), the frame "
        "rate (0 = the file's own), and a size — one side set scales keeping the shape, "
        "both sides fit that box by crop, pad or stretch. The chevron folds these away.\n\n"
        "In ⚙: a frame grid (H3: 24 fps and 17k+5 frames; LTX: 8k+1), every Nth frame, keep "
        "or drop the sound, fp32/fp16, and a memory cap that refuses an oversized load "
        "before decoding.\n\n"
        "The sound is cut to exactly the loaded frames' time. Outputs match Load Video "
        "Pixaroma's, in the same order."
    )
    CATEGORY = "Luna/Load"
    FUNCTION = "load"

    RETURN_TYPES = ("IMAGE", "AUDIO", "INT", "FLOAT", "INT", "INT", "FLOAT")
    RETURN_NAMES = ("video_frames", "audio", "frame_count", "fps", "width", "height", "duration")
    OUTPUT_TOOLTIPS = (
        "The video as a batch of frames, after start, length, frame rate, grid and size.",
        "The video's sound for exactly the loaded frames. None when the file has no sound "
        "or Sound is set to Drop in ⚙.",
        "How many frames were loaded.",
        "Frames per second of the loaded frames (the frame rate set here, divided by Every Nth).",
        "Frame width in pixels, after any resize.",
        "Frame height in pixels, after any resize.",
        "Length of the loaded part in seconds.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            # No "video_upload": the frontend would add a second player of its own.
            # The upload button and drag-and-drop come from js/luna_load_video.js.
            "video": (_videos(), {
                "tooltip": "The video, from ComfyUI's input folder. Upload one, drag a file onto "
                           "the node, or pick from the list."}),
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

    def load(self, video, start=0.0, frames=0, fps=0.0, width=0, height=0, fit="crop",
             frame_grid="free", every_nth=1, audio="keep", precision="fp32", memory_cap_gb=6.0):
        if not video:
            raise RuntimeError(f"[{NODE}] No video selected — upload one or pick one from the list.")
        path = folder_paths.get_annotated_filepath(video)
        if not path or not os.path.isfile(path):
            raise RuntimeError(f"[{NODE}] File not found: {video}")
        src = probe_media(path)
        if not src.get("video"):
            raise RuntimeError(f"[{NODE}] {os.path.basename(path)} has no video stream.")
        try:
            plan = _plan(src, start, frames, fps, width, height, fit, frame_grid, every_nth, precision)
        except ValueError as e:
            raise RuntimeError(f"[{NODE}] {os.path.basename(path)}: {e}.") from None
        s = _summary(plan, float(memory_cap_gb))
        if s["over"]:
            raise RuntimeError(
                f"[{NODE}] {plan['delivered']} frames at {plan['width']}x{plan['height']} {precision} "
                f"need {s['gb']:.2f} GB, over the {memory_cap_gb:g} GB memory cap (settings). Load fewer frames, "
                f"a smaller size, fp16, or raise the cap.")

        grid = GRIDS.get(frame_grid, "free")
        out, info = decode_clip(path, start, plan["frames"], plan["fps"], plan["size"], plan["fit"],
                                every_nth, precision, grid, who=NODE)
        sound = clip_soundtrack(path, info["start"], info["seconds"]) if audio == "keep" else None
        count = int(out.shape[0])
        line = (f"{os.path.basename(path)}: {count} frames @ {info['fps']:g} fps, "
                f"{info['width']}x{info['height']}, {info['seconds']:.2f} s"
                f"{' + sound' if sound is not None else ''}")
        if info["short"]:
            line += f" (file ended early: asked {info['asked']})"
        print(f"[{NODE}] {line}")
        return {"ui": {"luna_load_video": [line]},
                "result": (out, sound, count, float(info["fps"]), int(info["width"]),
                           int(info["height"]), float(info["seconds"]))}

    @classmethod
    def IS_CHANGED(cls, video, **kwargs):
        try:
            st = os.stat(folder_paths.get_annotated_filepath(video))
            return f"{st.st_mtime_ns}:{st.st_size}"
        except Exception:
            return float("nan")

    @classmethod
    def VALIDATE_INPUTS(cls, video, **kwargs):
        if not video:
            return "No video selected."
        if not folder_paths.exists_annotated_filepath(video):
            return f"Video not found: {video}"
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
