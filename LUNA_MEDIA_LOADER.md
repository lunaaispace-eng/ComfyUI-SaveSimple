# Luna Media Loader — plan, 2026-08-13

**Status: designed, not built.** Agreed 2026-08-13, to be built next session. Read
`LUNA_ASSET_LOADER.md` first — this node is its sibling and copies its patterns
deliberately. `CLAUDE.md` has the licence rules; they constrain what may be
borrowed here, and one of the nearest prior-art packs is GPL-3.0.

`Luna/Load` → **Luna Media Loader**. The numbered *video and audio* references
for MiniMax H3, alongside the Asset Loader's numbered images.

## Why it exists

Core's `MiniMax H3 Reference to Video` (`comfy_api_nodes/nodes_minimax.py:733`)
takes **three** Autogrow families, not one:

| family | slots | type | limit |
|---|---|---|---|
| `reference_images` | `image_1`…`image_9` | IMAGE | 9 |
| `reference_videos` | `video_1`…`video_3` | **VIDEO** | 2–15 s each, 15 s total |
| `reference_audios` | `audio_1`…`audio_3` | **AUDIO** | same, and unusable without an image or video |

Its own description: references are addressed in the prompt as *"Image 1",
"Video 1", "Audio 1"* — **in connection order**. That is the Asset Loader's
contract exactly, one type over: the wiring order *is* the numbering, and the
prompt writer has to be told which is which or it cannot refer to them.

Nothing installed fills this. The closest,
`VRGDG_MiniMaxH3ReferenceMediaFromPaths`, is paths-only with no brief.

## What this node is NOT — and the survey behind that

**It is not a "load a video, get frames" node.** That was considered and set
aside on 2026-08-13; four nodes on this install already do it. Recorded so the
survey is not re-derived:

| node | controls | outputs |
|---|---|---|
| core **Load Video** + **Get Video Components** | file combo + upload | VIDEO → images, audio, fps, bit_depth |
| core **Trim Video** | start_time, duration | VIDEO |
| **VHS** LoadVideo / LoadVideoPath (+ FFmpeg variants) | force_rate, custom w/h, frame_load_cap, skip_first_frames, select_every_nth | IMAGE, frame_count, audio, video_info |
| **Load Video Pixaroma** | max_frames, force_fps, skip_first_frames, custom w/h, node preview | video_frames, audio, frame_count, fps, width, height, duration |
| **crt-nodes** `Load_Last_Video` | — | the most recent video |

**Licences:** VHS is **GPL-3.0 — read for reference, never lift.** Pixaroma is
MIT and its output set is already what a blank-page design would land on; derive
from it with a header if a frames loader is ever wanted.

If it does come back, these are the only four gaps worth building for:

1. **N evenly spaced frames across the clip.** Everything ships
   `select_every_nth`, which is length-dependent — a 3 s and a 30 s clip give
   wildly different counts. Handing a clip to a prompt writer wants exactly N
   frames spread across it whatever its length.
2. `first_frame` / `last_frame` outputs — the mirror of Save Video Simple's
   `save_first_frame` / `save_last_frame`, for shot chaining.
3. Arbitrary paths: empty = input dir, relative = subfolder, absolute = exact —
   the same contract as Save Image Simple's `output_path`, so this pack's own
   `output/video/` files load back without being copied into `input/`.
4. A `video_info` brief for the prompt writer.

**A standalone Load Audio was also declined.** Core `LoadAudio` already lists
video files as well as audio, and Trim / Concat / Merge / Adjust Volume / Split
Channels all ship. The only gaps were a `duration` FLOAT and arbitrary paths —
not a node's worth. Audio earns slots *here*, where the numbering matters.

## Why a sibling node and not more sockets on the Asset Loader

Conceptually it belongs there. Mechanically it does not, and the reason is
concrete rather than aesthetic.

`asset_loader.py:255` returns a fixed 13-wide tuple (4 fixed + 9 images) and the
frontend trims trailing image slots. Append video and audio families after the
images and that mapping breaks: with `image_count` at 3, displayed slot 7 is
`video_1` but the tuple's index 7 is `image_4` — silently handing an IMAGE to a
VIDEO socket. Fixing it means Python packing densely by all three counts,
mirroring the JS rule exactly. About twenty lines, but it is the same bug class
`LUNA_ASSET_LOADER.md` records as having already bitten once, introduced into a
node that currently works.

Per-image *resize* and per-clip *trim* are also genuinely different panels.

The brief still ends up as one string: this node takes `asset_brief` as an
optional STRING input and appends to it, so
`Luna Asset Loader → Luna Media Loader → prompt writer` reads as one list.

## The spec

### Widgets

Canvas widgets, hidden behind the card UI, with **Fields** as the escape hatch —
same arrangement as the Asset Loader, and for the same reason: if the frontend
ever breaks, typing into the field still works.

| widget | type | role |
|---|---|---|
| `video_paths` | STRING multiline | one filename per line, the source of truth |
| `audio_paths` | STRING multiline | same |
| `media_state` | STRING multiline | JSON, mirrors `asset_state` — `{"videos":[{"start":0,"duration":0}],"audios":[…]}` |
| `asset_brief` | STRING input, optional | chained in from Luna Asset Loader |

Malformed `media_state` falls back to defaults rather than failing the run, as
`asset_state` does.

### Outputs — seven, fixed

| output | type |
|---|---|
| `asset_brief` | STRING |
| `video_1` … `video_3` | VIDEO |
| `audio_1` … `audio_3` | AUDIO |

**No slots stepper here, deliberately.** H3's ceiling is 3 and 3. Seven static
outputs delete the dense-packing index contract outright instead of
reimplementing it on both sides, and the stepper's original justification — 9
outputs pushing a widget 78 px down the node — does not apply at 3. Six sockets
that are sometimes empty cost nothing.

### The brief

Appends to whatever arrived on the input:

```
<Video 1> = 6.0 s, 1920x1080, 24 fps, mp4 (landscape)
<Audio 1> = 8.2 s, 48 kHz, stereo
```

### Warnings — advisory, never fatal

Printed and appended to the brief, following the FL2VA warning precedent:

- a clip under 2 s or over 15 s **after trim**
- a family's total over 15 s

**The node cannot enforce the budget and must not pretend to.** It cannot see
which of its outputs are wired, so three loaded clips may be one wired clip. It
reports each duration and the sum, and leaves the judgement there.

A missing file still **raises** with the filename — the no-black-frames rule
from `LUNA_ASSET_LOADER.md` applies unchanged.

## Implementation notes

**`VideoFromFile(file, *, start_time=0, duration=0)`**
(`comfy_api/latest/_input_impl/video_types.py:123`) takes the trim window in its
constructor. Trimming is therefore free — no re-encode, no temp file, no ffmpeg
call. Build the output as `VideoFromFile(path, start_time=s, duration=d)` and
that is the whole of it. Audio has no lazy equivalent; slice the waveform.

The same object answers everything the brief needs **without decoding frames**:
`get_duration()`, `get_dimensions()`, `get_frame_rate()`, `get_frame_count()`,
`get_container_format()`, `get_bit_depth()`.

**No new dependency.** `av` is imported at module level by core's
`comfy_extras/nodes_video.py`, so it is always present. `requirements.txt` stays
`Pillow` / `numpy`.

**Never call `get_components()` to sample frames.** A 15 s 1080p clip
materialises ~9 GB of float32 — on a 64 GB box that routinely sits near its
ceiling during H3 runs, that is a hang, not a slowdown. Seek and decode only the
frames wanted, through `av`.

### Frontend

Reuse the Asset Loader's card machinery: upload, drag to renumber, ✕, click to
select, ⓘ help panel, collapse chevron. Two lists, Videos and Audio.

- Video cards get a poster frame from an HTML `<video>` element — no backend
  route needed.
- Audio cards get a duration chip.
- The selected item's panel is **start / duration**, not the resize panel.

Watch the two traps from `HANDOFF.md`: `widget.hidden = true` is the flag that
actually hides a canvas widget, and a stray backtick inside the CSS template
literal silently wrecks the whole module while still passing `node --check`.

## The open decision — settle this first

The brief can say Video 1 is 6 seconds of 1080p. It cannot say Video 1 is a
handheld push-in through a doorway, which is the thing an H3 prompt would
actually want to reference.

An optional **`video_previews` IMAGE** output — N evenly spaced frames per
reference clip, batched — would let Luna Agent Chat / LLM Prompt see the motion
references rather than read their dimensions.

Recommended **in**, defaulting to 3 frames per clip, subject to the
`get_components()` memory note above. Not yet agreed.
