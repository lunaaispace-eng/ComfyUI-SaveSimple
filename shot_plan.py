"""Luna Shot List's rules: a script of scenes -> where each scene sits in the song and
how many frames it has. Pure Python, no ComfyUI imports, so it is tested on its own
(tests/test_shot_plan.py).

The script is plain text, one scene per line, so a person can type it and a song
analysis can write it:

    # comments and blank lines are skipped
    overlap: 22            # optional settings lines: overlap (frames), start (song time of scene 1)
    0:12.00 | 5.17 | the singer walks into the light
            | 124f | close-up on the guitar
    0:30.5  | 3s   | wide shot, the crowd

Each line is `start | length | prompt`.
  * start: m:ss.xx, h:mm:ss or plain seconds. Empty = straight after the previous
    scene, sharing `overlap` frames with it (scene 1: the `start:` setting, else 0).
  * length: seconds (5.17, 5.17s, 0:05.17) or frames (124f, 124 frames). Snapped to the
    grid's nearest count.
  * prompt: everything after the second |, may be empty.

A JSON list is accepted too, for tools: [{"start": 12, "seconds": 5.17, "prompt": "..."},
{"frames": 124}] or {"overlap": 22, "scenes": [...]}.
"""

from __future__ import annotations

import json
import re

GRIDS = {"h3": (24, 17, 5), "ltx": (25, 8, 1), "free": (24, 1, 0)}   # fps, step, phase


def grid_fps(grid: str) -> int:
    return GRIDS.get(grid, GRIDS["h3"])[0]


def snap(frames: int, grid: str) -> int:
    """Nearest frame count on the grid (n % step == phase), never below the smallest."""
    _, step, phase = GRIDS.get(grid, GRIDS["h3"])
    n = max(1, int(round(frames)))
    if step == 1:
        return n
    lo = n - ((n - phase) % step)
    if lo < max(phase, 1):
        lo = phase if phase >= 1 else step
    hi = lo + step
    return hi if (n - lo) > (hi - n) else lo


def parse_time(text: str) -> float:
    """'1:02.5' -> 62.5, '0:01:02' -> 62, '12' -> 12.0. Raises ValueError."""
    t = text.strip().lower().rstrip("s").strip()
    if not t:
        raise ValueError("empty time")
    parts = t.split(":")
    if len(parts) > 3 or any(p.strip() == "" for p in parts):
        raise ValueError(f"cannot read the time '{text.strip()}'")
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    if total < 0:
        raise ValueError(f"negative time '{text.strip()}'")
    return total


_FRAMES = re.compile(r"^\s*(\d+)\s*(f|fr|frame|frames)\s*$", re.I)


def parse_length(text: str, fps: int) -> tuple:
    """-> (frames asked, as written). '124f' is frames; anything else is a time."""
    m = _FRAMES.match(text)
    if m:
        return int(m.group(1)), "frames"
    return int(round(parse_time(text) * fps)), "seconds"


def _rows_from_text(script: str) -> tuple:
    """-> (settings dict, [ {line, start, length, prompt} as text ])."""
    settings, rows = {}, []
    for i, raw in enumerate(script.splitlines()):
        line = raw.split("#", 1)[0] if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        if "|" not in line:
            m = re.match(r"^\s*(overlap|start)\s*[:=]\s*(.+?)\s*$", line, re.I)
            if m:
                settings[m.group(1).lower()] = m.group(2)
                continue
            raise ValueError(f"line {i + 1}: expected 'start | length | prompt', got '{raw.strip()}'")
        start, rest = line.split("|", 1)
        length, prompt = (rest.split("|", 1) + [""])[:2]
        # The prompt keeps a '#' (a colour, a hashtag): only the start/length part had
        # its comment cut, so take the prompt from the raw line.
        prompt = raw.split("|", 2)[2] if raw.count("|") >= 2 else prompt
        rows.append({"line": i, "start": start.strip(), "length": length.strip(), "prompt": prompt.strip()})
    return settings, rows


def _rows_from_json(data) -> tuple:
    settings = {}
    if isinstance(data, dict):
        for k in ("overlap", "start"):
            if k in data:
                settings[k] = str(data[k])
        data = data.get("scenes", [])
    if not isinstance(data, list):
        raise ValueError("JSON must be a list of scenes or {\"scenes\": [...]}")
    rows = []
    for i, s in enumerate(data):
        if not isinstance(s, dict):
            raise ValueError(f"scene {i + 1}: expected an object")
        if "frames" in s:
            length = f"{int(s['frames'])}f"
        elif "seconds" in s or "length" in s:
            length = str(s.get("seconds", s.get("length")))
        else:
            raise ValueError(f"scene {i + 1}: needs frames or seconds")
        start = s.get("start")
        rows.append({"line": None, "start": "" if start is None else str(start), "length": length,
                     "prompt": str(s.get("prompt", ""))})
    return settings, rows


def plan_scenes(script: str, grid: str = "h3", overlap_frames: int = 22) -> dict:
    """The script -> {"scenes": [...], "fps": f, "overlap": n}. Raises ValueError with
    the line or scene that is wrong. A `overlap:` line in the script wins over the
    argument; so does `start:` for scene 1."""
    fps = grid_fps(grid)
    text = (script or "").strip()
    if not text:
        raise ValueError("the script is empty")
    if text[0] in "[{":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"the JSON does not parse: {e.msg} at line {e.lineno}") from None
        settings, rows = _rows_from_json(data)
    else:
        settings, rows = _rows_from_text(text)
    if not rows:
        raise ValueError("the script has no scenes")
    overlap = int(overlap_frames)
    if "overlap" in settings:
        try:
            overlap = int(float(settings["overlap"]))
        except ValueError:
            raise ValueError(f"cannot read overlap '{settings['overlap']}'") from None
    if overlap < 0:
        raise ValueError("overlap cannot be negative")
    first = parse_time(settings["start"]) if "start" in settings else 0.0

    scenes, prev = [], None
    for k, r in enumerate(rows):
        where = f"line {r['line'] + 1}" if r["line"] is not None else f"scene {k + 1}"
        try:
            asked, unit = parse_length(r["length"], fps)
        except ValueError as e:
            raise ValueError(f"{where}: length — {e}") from None
        if asked <= 0:
            raise ValueError(f"{where}: length must be more than 0")
        frames = snap(asked, grid)
        seconds = frames / fps
        if r["start"]:
            try:
                start = parse_time(r["start"])
            except ValueError as e:
                raise ValueError(f"{where}: start — {e}") from None
            auto = False
        elif prev is None:
            start, auto = first, True
        else:
            start, auto = prev["start"] + prev["seconds"] - overlap / fps, True
            if start <= prev["start"]:
                raise ValueError(f"{where}: an overlap of {overlap} frames is as long as scene "
                                 f"{prev['scene']}; the song would not move on")
        shared = 0 if prev is None else max(0, int(round((prev["start"] + prev["seconds"] - start) * fps)))
        s = {"scene": k + 1, "line": r["line"], "start": start, "seconds": seconds,
             "frames": frames, "asked": asked, "unit": unit, "prompt": r["prompt"],
             "auto_start": auto, "overlap": shared}
        scenes.append(s)
        prev = s
    return {"scenes": scenes, "fps": fps, "overlap": overlap,
            "end": max(s["start"] + s["seconds"] for s in scenes)}


def clock(t: float) -> str:
    t = max(0.0, float(t))
    m = int(t // 60)
    return f"{m}:{t - m * 60:05.2f}"


def scene_line(start: str, length: str, prompt: str) -> str:
    """One script line, as the table editor writes it back."""
    return f"{start.strip():<8} | {length.strip():<6} | {prompt.strip()}".rstrip()
