"""Luna Shot List — scenes of different lengths over one song, from a script.

One run = one scene. The `scene` number picks the row; set its control to
"increment" and queue the whole list. The script is plain text (or JSON) so a song
analysis can write it and a person can fix it in the table on the node; the rules
live in shot_plan.py.

Wiring: `seconds` -> Luna Asset Loader `seconds` (or Luna MiniMax H3 Canvas
`duration_seconds`), `song_start` -> Luna Asset Loader `song_start`, `frames` ->
the H3 node's `length`, `prompt` -> the prompt writer.
"""

from __future__ import annotations

from .shot_plan import clock, plan_scenes

NODE = "Luna Shot List"
GRIDS = {"H3 (24 fps, 17k+5)": "h3", "LTX (25 fps, 8k+1)": "ltx", "free (24 fps)": "free"}
EXAMPLE = """# One scene per line:  start | length | prompt
# start: m:ss.xx or seconds; empty = right after the previous scene (sharing the overlap)
# length: seconds (5.17) or frames (124f)
0:00.00 | 5.17 | first scene
        | 124f | second scene
"""


class LunaShotList:
    DESCRIPTION = (
        "Scenes of different lengths over one song, from a script — one scene per run.\n\n"
        "Write one scene per line: `start | length | prompt`. Start is the song time "
        "(m:ss.xx or seconds); leave it empty and the scene follows the previous one, "
        "sharing `overlap` frames with it. Length is seconds (5.17) or frames (124f) and "
        "lands on the grid's nearest count. A JSON list of scenes works too. The table "
        "under the script shows every scene's song window and lets you edit, add and "
        "remove rows; click a row to make it the scene this run makes.\n\n"
        "Automation: set `scene`'s control to increment and queue as many runs as there "
        "are scenes; or wire the script from another node. A scene number past the end "
        "stops the run and says how many scenes there are.\n\n"
        "Wire seconds -> Luna Asset Loader seconds, song_start -> its song_start, frames "
        "-> the H3 node's length, prompt -> the prompt writer."
    )
    CATEGORY = "Luna/Plan"
    FUNCTION = "pick"

    RETURN_TYPES = ("INT", "INT", "INT", "FLOAT", "FLOAT", "STRING", "INT", "STRING")
    RETURN_NAMES = ("scene", "scenes", "frames", "seconds", "song_start", "prompt", "overlap", "info")
    OUTPUT_TOOLTIPS = (
        "The scene this run makes, counting from 1.",
        "How many scenes the script has.",
        "This scene's frame count, on the grid. Wire it to the H3 node's length.",
        "This scene's length in seconds, frames / fps. Wire it to Luna Asset Loader's seconds "
        "(or Luna MiniMax H3 Canvas's duration_seconds).",
        "Where in the song this scene starts, in seconds. Wire it to Luna Asset Loader's song_start.",
        "This scene's prompt text from the script (may be empty).",
        "How many frames this scene shares with the one before it (0 for scene 1 and for a "
        "scene with its own start that leaves a gap).",
        "One line about this scene, for a note or a log.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "script": ("STRING", {
                "multiline": True, "default": EXAMPLE,
                "tooltip": "The scenes, one per line: start | length | prompt. Lines starting "
                           "with # are notes. 'overlap: 22' or 'start: 0:12' on a line of its own "
                           "set those for the whole script. A JSON list of scenes is read too. "
                           "Wire a STRING here to drive it from another node."}),
            "scene": ("INT", {
                "default": 1, "min": 1, "max": 9999, "step": 1, "control_after_generate": True,
                "tooltip": "Which scene this run makes, from 1. Set the control under it to "
                           "increment and queue once per scene to make them all."}),
            "grid": (list(GRIDS), {
                "default": "H3 (24 fps, 17k+5)",
                "tooltip": "Frame counts the model accepts, and its frame rate. Every length "
                           "lands on the nearest count."}),
            "overlap": ("INT", {
                "default": 22, "min": 0, "max": 361, "step": 1,
                "tooltip": "Frames a scene without its own start shares with the one before "
                           "(H3: 5, 22 or 39 fit its grid). The song steps back this much at "
                           "each cut, so a continuation lines up. 0 = back to back. An "
                           "'overlap:' line in the script wins."}),
        }}

    def pick(self, script, scene=1, grid="H3 (24 fps, 17k+5)", overlap=22):
        try:
            plan = plan_scenes(script, GRIDS.get(grid, "h3"), overlap)
        except ValueError as e:
            raise RuntimeError(f"[{NODE}] The script: {e}.") from None
        scenes = plan["scenes"]
        n = int(scene)
        if not 1 <= n <= len(scenes):
            raise RuntimeError(f"[{NODE}] Scene {n} asked, but the script has {len(scenes)} "
                               f"scene(s). Set scene to 1-{len(scenes)}.")
        s = scenes[n - 1]
        info = (f"Scene {n} of {len(scenes)}: {clock(s['start'])}-{clock(s['start'] + s['seconds'])}, "
                f"{s['frames']} frames ({s['seconds']:.2f} s at {plan['fps']} fps)")
        if s["overlap"]:
            info += f", sharing {s['overlap']} frames with scene {n - 1}"
        if s["frames"] != s["asked"]:
            info += f"; asked {s['asked']} frames, the grid gives {s['frames']}"
        print(f"[{NODE}] {info}")
        return {"ui": {"luna_shot": [n]},
                "result": (n, len(scenes), s["frames"], float(s["seconds"]), float(s["start"]),
                           s["prompt"], s["overlap"], info)}


try:
    from aiohttp import web
    from server import PromptServer
except ImportError:   # imported outside ComfyUI (tests): no routes
    PromptServer = None

if PromptServer is not None:
    @PromptServer.instance.routes.post("/lunasave/shot-list")
    async def _luna_shot_list(request):
        """The script as the table shows it — the same plan the run uses."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "bad request"}, status=400)
        script = body.get("script", "")
        if not isinstance(script, str) or len(script) > 1_000_000:
            return web.json_response({"error": "the script is not text"}, status=400)
        try:
            overlap = int(body.get("overlap", 22))
            plan = plan_scenes(script, GRIDS.get(body.get("grid"), "h3"), overlap)
        except (ValueError, TypeError) as e:
            return web.json_response({"error": str(e)})
        return web.json_response(plan)


NODE_CLASS_MAPPINGS = {"LunaShotList": LunaShotList}
NODE_DISPLAY_NAME_MAPPINGS = {"LunaShotList": "Luna Shot List"}
