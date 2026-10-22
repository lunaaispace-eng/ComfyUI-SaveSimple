# ComfyUI-SaveSimple

Nine deliberately small nodes for ComfyUI: save an image, save a video, load a
set of reference images once instead of once per consumer, load a video as
frames, plan scenes of different lengths over one song, feed MiniMax H3 all
four of its reference families down one wire, cast a frame batch to fp16, and
strip the 2px VAE pixel grid off a decoded image. Each exists because the
alternatives carried more settings than the job needs.

| Node | Category | Class |
| --- | --- | --- |
| `Luna Save Image` | `Luna/Save` | `SaveImageSimple` |
| `Luna Save Video` | `Luna/Save` | `SaveVideoSimple` |
| `Luna Asset Loader` | `Luna/Load` | `LunaAssetLoader` |
| `Luna Shot List` | `Luna/Plan` | `LunaShotList` |
| `Luna Load Video` | `Luna/Load` | `LunaLoadVideo` |
| `Luna H3 Reference Loader` | `Luna/Load` | `LunaH3ReferenceLoader` |
| `Luna H3 Refs Out` | `Luna/Load` | `LunaH3RefsOut` |
| `Luna Image Precision` | `Luna/Image` | `LunaImagePrecision` |
| `VAE DeGrid (Nyquist Notch)` | `Luna/Image` | `VAEDeGrid` |

> The two **Luna H3** nodes were added on 2026-09-04 and do not have a written
> section below yet. Each carries its own **ⓘ** panel with every input and output
> documented, which is the authoritative description until this file catches up.

Every node carries an **ⓘ** on its title bar with its own inputs and outputs
documented, and the two save nodes carry a **chevron** that folds their settings
away, leaving the sockets and the preview.

> **`Luna MiniMax H3 Canvas` has moved.** It now lives in
> [ComfyUI-LunaMiniMaxH3](https://github.com/lunaaispace-eng/ComfyUI-LunaMiniMaxH3)
> along with the rest of the MiniMax H3 nodes. The class name is unchanged, so saved
> workflows keep resolving once that pack is installed — install it in the same pass
> as updating this one, since two installed copies of one class collide.

## Installation

1. Copy this folder into your ComfyUI custom nodes directory:

```text
ComfyUI/custom_nodes/ComfyUI-SaveSimple
```

2. Install dependencies if needed:

```bash
pip install -r requirements.txt
```

3. Restart ComfyUI.
4. Hard-refresh the browser page with `Ctrl+F5`. The nodes ship frontend
   JavaScript, so a restart alone is not enough.

---

# Luna Save Image

Choose a filename prefix, image format, output folder, quality, DPI, preview
behaviour, and whether to keep ComfyUI metadata. It can also write readable
positive and negative prompt text beside each image, so you keep clean prompt
records for PNG, JPG and WEBP output.

## Features

- Save images as `png`, `jpg`, or `webp`.
- Save to the ComfyUI output folder, a subfolder, or an absolute path.
- Optional ComfyUI preview for files saved under the output folder.
- Optional PNG workflow/prompt metadata for drag-and-drop reloads in ComfyUI.
- Optional readable positive/negative prompt sidecar text files.
- Optional PNG metadata fields for `positive_prompt` and `negative_prompt`.
- JPG/WEBP quality control, WEBP lossless mode, PNG/JPG DPI control.
- Timestamped filenames.
- Batch image saving with auto-numbered filenames.

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `images` | required | Image or image batch to save. |
| `filename_prefix` | `ComfyUI` | Base filename. Files are auto-numbered, for example `ComfyUI_00001.png`. Accepts date tokens — see below. |
| `format` | `png` | Output format: `png`, `jpg`, or `webp`. |
| `save_metadata` | `yes` | For PNG only, embeds ComfyUI prompt/workflow metadata. Turn off for a clean file. |
| `output_path` | empty | Empty saves to the ComfyUI output folder. Relative paths save to an output subfolder. Absolute paths save directly there. Accepts date tokens. |
| `quality` | `95` | JPG/WEBP quality. |
| `webp_lossless` | `off` | Enables WEBP lossless mode. |
| `dpi` | `96` | PNG/JPG DPI value. |
| `add_timestamp` | `off` | Adds `_YYYYMMDD-HHMMSS` to the filename. |
| `save_prompt_text` | `off` | Saves readable positive and negative prompt text beside each image. |
| `preview` | `on` | Shows saved images in the node when the file is inside the ComfyUI output folder. |

## Outputs

| Output | Type | Description |
| --- | --- | --- |
| `file_path` | `STRING` | Absolute saved image path. For batches, paths are newline-separated. |

## Prompt text saving

With `save_prompt_text` enabled, the node extracts positive and negative
conditioning text from the ComfyUI prompt graph and writes a sidecar beside each
image:

```text
ComfyUI_00001.png
ComfyUI_00001.txt
```

```text
Positive:
your positive prompt

Negative:
your negative prompt
```

For PNG, if `save_metadata` is also enabled, the same text is embedded as
`positive_prompt` and `negative_prompt` PNG text chunks. The full workflow
metadata is still written to the normal `prompt` and extra PNG info fields.

## Filename behaviour

```text
ComfyUI_00001.png
ComfyUI_00002.png
```

With timestamps enabled:

```text
ComfyUI_20260627-154422_00001.png
```

The counter is based on existing files in the target folder matching the prefix.

## Date tokens

`filename_prefix` and `output_path` both expand `%date:...%`, the same tokens
Luna Save Video accepts, so a pattern means the same thing in either node.

| Pattern | Becomes |
| --- | --- |
| `image_%date:hhmmss%` | `image_154422` |
| `shot_%date:yyyy-MM-dd%` | `shot_2026-08-10` |
| `%date%` | `20260810_154422` |
| `renders/%date:yyyy-MM-dd%` in `output_path` | `renders/2026-08-10` |

Tokens are `yyyy` `yy` `MM` `dd` `HH`/`hh` `mm` `ss`; a bare `%date%` means
`yyyyMMdd_HHmmss`. A literal `%` that isn't part of a token is left alone, so
`100% cotton` survives.

Folders remain `output_path`'s job — the prefix is reduced to a basename after
expansion, so a slash inside a date pattern cannot quietly create a directory.

## Notes

- PNG metadata is only available for PNG output. JPG and WEBP are always saved
  without ComfyUI workflow metadata; the readable `.txt` sidecar works for all
  three formats.
- Saving to an absolute path outside the ComfyUI output folder works, but ComfyUI
  shows no in-node preview, because it only serves known output folders.
- Prompt extraction targets common graphs where samplers receive conditioning
  from `CLIPTextEncode`. Workflows with multiple samplers, regional prompting,
  conditioning merges or custom conditioning nodes may produce combined or
  partial prompt text.

---

# Luna Save Video

An `IMAGE` batch to a video file, with the same prompt-sidecar idea applied to
video: a `.txt` beside the finished file. Includes an in-node player with a
Download button, and optional first/last frame export.

Derived from `DaSiWa_EnhancedVideoCombine` in
[ComfyUI-DaSiWa-Nodes](https://github.com/DaSiWa/ComfyUI-DaSiWa-Nodes), used under
Apache-2.0. The changes are listed in the header of `video_nodes.py` as section
4(b) of the licence requires.

## Inputs and outputs

| Input | Description |
| --- | --- |
| `images` | required — the frames to encode |
| `audio` | optional audio track |
| `prompt_text` | text for the sidecar |
| `frame_rate`, `codec`, `container`, `bit_depth`, `quality` | encoding |
| `pingpong`, `crop_to_audio`, `pass_frames` | frame handling |
| `audio_codec`, `audio_bitrate` | audio encoding |
| `filename_prefix`, `output_path`, `save_output`, `save_metadata` | output |
| `save_first_frame`, `save_last_frame`, `save_prompt` | extras, in the player panel |

| Output | Type | Description |
| --- | --- | --- |
| `frames` | `IMAGE` | the frames as encoded |
| `filename` | `STRING` | the written video path |
| `video` | `VIDEO` | the saved file as a native ComfyUI video, audio included; empty for animated image formats (GIF, WebP) |

`output_path` works as in Luna Save Image: empty saves to the ComfyUI output
folder, a relative name saves to a subfolder of it, an absolute path saves
exactly there. Date tokens work (`renders/%date:yyyy-MM-dd%`). With
`save_output` off, empty and relative paths land in the temp folder instead. The
in-node player can only play files inside the output folder, so a video saved
elsewhere has no preview; the file and the `filename` / `video` outputs are
unaffected. Every input has a hover tooltip, also listed in the ⓘ panel.

The sidecar path is derived from the finished video path
(`splitext(video_path)[0] + ".txt"`), never from a separate counter — two
independent counters drift apart as soon as a run fails, and the `.txt` would
then belong to the previous video.

---

# Luna Asset Loader

One ordered set of reference images, loaded once and fed to every consumer.
Built for MiniMax H3, which wants each reference at its own aspect ratio while
prompt writers want a single batch — so the loader emits both and the picture is
only loaded once.

See [LUNA_ASSET_LOADER.md](LUNA_ASSET_LOADER.md) for the full description.

The per-image resize state is modelled on
[ComfyUI-Pixaroma](https://github.com/pixaroma/ComfyUI-Pixaroma) by pixaroma
(MIT) — the schema's key names, defaults and JSON-blob approach come from that
pack. Details in the header of `asset_loader.py`.

## Outputs

```text
images        IMAGE          all pictures as ONE batch, conformed to image 1's size
width, height INT            image 1's size AFTER its resize
asset_brief   STRING         "<Picture 1> = 1920x1056 (20:11, landscape); ... Song: ..."
audio         AUDIO          the song window from sound card A1, exactly as long as set
refs          LUNA_H3_REFS   the pictures as MiniMax H3 references, for Luna H3 Refs Out
timeline      LUNA_TIMELINE  what sits on the shot and where, in frames (today: the song)
image_1 … 9   IMAGE          each at its ORIGINAL size, in card order
```

Workflows saved before `audio`, `refs` and `timeline` existed are updated when they
open: their `image_N` wires stay on the same pictures.

An `IMAGE` batch cannot hold mixed dimensions, so only the batch is conformed —
the numbered outputs stay untouched, because conforming them would destroy the
aspect information the model wants.

## The card UI

| Control | What it does |
| --- | --- |
| **Image slots `− N +`** | top left of the node — how many numbered outputs show; click `N` to type one |
| **Upload** | multi-select pictures and sound files; posts to ComfyUI's `/upload/image` |
| **Clear** | empties the list, pictures and sounds |
| **Fields** | shows the raw `image_paths` / `image_count` / `asset_state` / `media_state` widgets |
| **drag a card** | reorder — this renumbers `<Picture N>` |
| **click a card** | selects it; the preview and resize panel follow |

Card order **is** the numbering: slot N is `<Picture N>` everywhere downstream.
`image_paths` (one filename per line) stays the source of truth, so the node still
works if you type into the field directly.

Showing fewer outputs than you have images is intentional: the extra pictures stay
loaded and a drag promotes one into an active slot, leaving the rest parked.

## Sound cards — the song

Upload a sound file (wav, mp3, flac, ogg, m4a …) and it becomes a pink sound card,
`A1`. Select it and the preview turns into the song editor:

| Control | What it does |
| --- | --- |
| **the whole song** | drag the yellow window to move it; drag its edges to change the length; click elsewhere on the song to centre the window there |
| **zoom strip** | the window ± 1 s with a 0.5 s grid; drag it to place the cut finely |
| **Start / Duration / End** | the same window as numbers (`1:23.45` or seconds); ◀ ▶ move it by 0.1 s |
| **Song ends** | what fills the window when it runs past the end of the file: silence, or the song again from its start — the editor and the run both say when this happens |
| **Snap** | snap the duration to MiniMax H3 shot lengths (17k+5 frames at 24 fps) |
| **Position** | **Free**: the window is where you put it. **By shot number**: the song is cut into shots — see below |
| **▶** | plays the window |

Wire **`seconds`** (the shot length) and the duration is locked to it — the song
then always matches the shot, and only the start moves. `audio` delivers exactly
that window, sample for sample.

### A music video: one song, many shots

Set **Position** to **By shot number** and the window follows the shot number:
shot *n* starts where shot *n − 1* started plus the shot length minus the
**overlap** (5, 22 or 39 frames — MiniMax H3 clips are 17k+5). Neighbouring shots
share that much song, the same frames a continuation carries over in the picture,
so sound and picture line up at every cut.

- **Shot ◀ n ▶** picks the shot; wire the **`shot`** input (an Int) to drive it
  from outside. The editor says *of N* — how many shots start inside the song.
- **Song start** is where shot 1 begins. Dragging the window moves every shot
  together. A thin strip on top of the song shows every shot's window.
- A shot number past the end of the song stops the run with the shot count.

Every shot the same length is the limit of this mode. For **scenes of different
lengths**, use **Luna Shot List** (below) and wire its **`song_start`** into the
Asset Loader's `song_start` input and its **`seconds`** into `seconds`: the window
then sits exactly where that scene's line in the script puts it, and the editor
locks Start and says where it comes from. A wired `song_start` wins over the
card's Start and over By shot number.

With **Luna MiniMax H3 Canvas** wired into `seconds` (its `seconds` output), the
editor knows the shot length before a run: it reads the Canvas's duration and
rounds it to H3's grid the same way the Canvas does.

## Video cards — clips

Upload a clip (mp4, mov, mkv, webm …) and it becomes an orange video card, `V1`
… `V3` — MiniMax H3's `<Video 1>` … in that order. Select it for the clip editor:
a preview, the whole clip as a film strip with a window over it, and the load
settings.

| Control | What it does |
| --- | --- |
| **film strip** | drag the window to choose the part; drag its edges to change the length; click elsewhere to centre it there |
| **Start / Length** | the window as numbers; ◀ ▶ move one source frame, − + step the length (along the H3 grid when Frames is H3) |
| **Frame rate** | H3 (24), the source's own rate, 24, 25 or 30 — frames are dropped or held, never blended, so motion stays in real time |
| **Frames** | H3 grid (17k+5, nearest) or Free |
| **Size / Fit** | Match canvas (wire `width` and `height`; crop to fill, pad or stretch), 768 short edge, or Source |
| **Every Nth** | keep every 2nd, 3rd or 4th frame |
| **Soundtrack** | keep the clip's own sound (cut to the clip) or drop it |
| **Precision** | fp16 halves the memory |

Before anything decodes, the editor shows what the clip will cost — "39 frames at
1344×768 = 0.24 GB as fp16" — and a clip over 6 GB is refused with that number
instead of filling the machine's memory mid-run. A clip that ends before its
window is cut down to the H3 grid, never padded.

Clips reach MiniMax H3 through **`refs`** → Luna H3 Refs Out (`ref_video_0..2`,
`ref_video_audio_0..2`). A kept soundtrack is the `<Audio>` right before its
`<Video>`, and `asset_brief` names which is which.

## The shot timeline — references or on the shot

Under the cards sits the **shot**: the video being generated, as long as the
`seconds` input says (or set here with − +, in 17-frame steps). It has one lane
per kind of asset, and every card has a **role**:

| Card | Roles |
| --- | --- |
| picture | **Reference** (H3 sees it, named `<Picture n>`), or **Keyframe on the shot** at a frame |
| clip | **Reference** (`<Video n>`), or **On the shot** from a frame — it must end inside the shot |
| sound | **Lock to shot** (sound 1, the song: the picture follows it), **Guide at frame**, or **Reference** (`<Audio n>`) |

Set the role in the card's editor (with *At frame*, *First*, *Last*), then drag
the item along its lane. The **References** row shows the tag H3 will really use:
H3 numbers only the references, in order, so with picture card 1 as a keyframe,
card 2 is `<Picture 1>`. `asset_brief` spells out both the references and what
sits where on the shot.

`refs` carries only the references. `timeline` carries everything on the shot,
with its frames, picture or sound attached, for a node that applies it. A
placement that does not fit stops the run and says where it would fit.

## Continuation — the previous shot opens this one

Press **↺ Continue** and a ↺ card opens the shot with the end of the previous
shot, so the motion carries on across the cut:

| Setting | What it does |
| --- | --- |
| **Take** | the last frames (a clip guide from frame 0) or only the last frame (a keyframe at 0) |
| **Frames** | when the song is cut **By shot number**, the song's overlap — sound and picture then overlap by the same amount at every cut; otherwise 5, 22 or 39 |
| **From** | the **newest video in an output folder** (point the save node there; empty = the output folder itself), **a file** in the input folder, or the **`previous_frames`** input |

The frames end exactly on the previous shot's last image. Shot 1 has nothing
before it, so its continuation is skipped and the brief says so.

## ⚙ Settings

The **⚙** button opens a panel against the node's right edge (it pans and zooms
with the node; ✕, Done or Esc close it):

| Setting | What it does |
| --- | --- |
| **Target** | **MiniMax H3** (24 fps, clips 17k+5), **LTX** (25 fps, clips 8k+1, clip guides only at frame 0 or 8k+1), or **General** (the source's own rate, any length). "Target" frame rate and frame grid on every clip, the shot's ± step and the song snap follow it |
| **New clips** | the frame rate, size and precision a newly added clip starts with |
| **Memory cap** | a clip that would need more is refused before decoding (default 6 GB) |
| **Sound** | the ◀ ▶ nudge step (0.1 s, 1 frame, 0.5 s) and what new songs do past their end |
| **Node** | the picture preview's height |

The settings live in `media_state` with everything else, so they travel with the workflow.

## Per-image resize

`mode` defaults to `off` — nothing is touched unless asked, which is what H3's
reference path wants. Options are max megapixels, longest side or scale factor,
with an optional target ratio (crop or pad) and snapping to /8 … /64 (**32
matches H3's `CANVAS_MULTIPLE`**). Order of operations is aspect → size → snap.

Settings are stored as JSON in `asset_state` and can be edited by hand:

```json
{"items": [{"ratio":"16:9","snap":32}, {"ratio":"16:9","snap":32}]}
```

`{"all": {...}}` applies one state to every image; `items` wins over `all`.
Malformed JSON falls back to defaults rather than failing the run.

## No black frames

A missing file **raises** with its filename rather than substituting a blank
image. Silently dropping `<Picture 2>` would renumber every reference after it
and mislabel the whole prompt.

---

# Luna Shot List

Scenes of different lengths over one song, from a script — one scene per run.

```
# one scene per line:  start | length | prompt
overlap: 22
0:12.00 | 5.17 | the singer walks into the light
        | 124f | close-up on the guitar
0:30.5  | 3s   | wide shot, the crowd
```

- **start** — song time (m:ss.xx or seconds). Empty = straight after the previous
  scene, sharing `overlap` frames with it, so a continuation lines up at the cut.
- **length** — seconds (`5.17`, `3s`) or frames (`124f`); lands on the grid's
  nearest count (H3 17k+5 at 24 fps, LTX 8k+1 at 25 fps, or free).
- **prompt** — the rest of the line, out on `prompt`.
- `overlap: N` and `start: m:ss` on a line of their own apply to the whole script;
  `#` starts a note. A JSON list (`[{"start": 12, "seconds": 5.17, "prompt": "…"},
  {"frames": 124}]`) is read too, for tools.

The **table** under the script shows every scene's start, end, length on the grid
and the frames it shares with the one before; edit a cell (the line in the script
is rewritten, comments stay), **+ scene** adds one, ✕ removes one, and clicking a
scene's number makes it the one the next run makes.

**Automation:** set the control under `scene` to **increment** and queue once per
scene; or wire the script from another node (a song analysis, a text loader). A
scene past the end stops the run and says how many there are.

| Output | |
| --- | --- |
| `scene` / `scenes` | this scene's number, and how many there are |
| `frames` | this scene's frame count on the grid — wire to the H3 node's `length` |
| `seconds` | `frames / fps` — wire to Luna Asset Loader `seconds` (or Canvas `duration_seconds`) |
| `song_start` | where in the song this scene starts — wire to Luna Asset Loader `song_start` |
| `prompt` | this scene's text |
| `overlap` | frames shared with the scene before (0 for scene 1 or after a gap) |
| `info` | one line about the scene |

---

# Luna Load Video

Load a video as a batch of frames, with its sound and its numbers. Upload a file
(button or drag onto the node) or pick one from the list, and it plays on the node
straight away. The line under the player says what a run will load — frames, frame
rate, size, length and memory — before you run, worked out by the same code the run
uses.

**On the node** (the chevron folds these away, the player stays):

| Setting | Does |
| --- | --- |
| `start` | Seconds into the file where loading starts. The sound starts there too. |
| `frames` | How many frames, counted at the frame rate below. `0` = to the end. |
| `fps` | Load at this rate by dropping or repeating frames, so motion stays real-time. `0` = the file's own. |
| `width` / `height` | `0` = keep. One set = scale to it, keeping the shape. Both set = fit that box by `fit`. |
| `fit` | `crop` fills the box and cuts the overflow, `pad` fits inside with black bars, `stretch` distorts. |

**In ⚙** (the cog on the title bar opens the settings panel beside the node):

| Setting | Does |
| --- | --- |
| Frame grid | `Free`; `H3` = 24 fps and 5, 22, 39 … frames (17k+5); `LTX` = 1, 9, 17 … (8k+1). The count lands on the nearest the grid allows, never past the end of the file. |
| Every Nth | Keep every Nth frame; the `fps` output divides by N. |
| Sound | `Keep` = the sound for exactly the loaded frames; `Drop` = none. |
| Precision | `fp32` (what every node expects) or `fp16` (half the memory). |
| Memory cap | A load that would need more is refused before decoding, with the numbers. Default 6 GB. |

**Outputs** — the same seven as Load Video Pixaroma, in the same order:
`video_frames`, `audio` (None when there is no sound or it is dropped), `frame_count`,
`fps`, `width`, `height`, `duration`.

Derived from Load Video Pixaroma (ComfyUI-Pixaroma, MIT); the change list is in the
header of `load_video.py`.

---

# Luna Image Precision

Casts an IMAGE batch to `fp16` or `fp32`. One widget, because there is one
decision to make.

It exists for nodes that size their own output buffer from the dtype of the
batch handed to them. `(Deno) RTX Video Super Resolution (2 Pass)` is the case it
was written for: it preallocates `[batch, height, width, 3]` in `images.dtype`,
so a 2688x1536 frame costs 49.5 MB in fp32 and 24.7 MB in fp16 — across a
247-frame interpolated clip, **11.4 GB against 5.7 GB**.

The batch cannot arrive as fp16 on its own. GIMM-VFI's `interpolate()` ends with
`.cpu().float()`, so it hands on fp32 whatever its own `precision` widget was set
to. Placing this node between the two is the only way to change that.

fp16 holds ~11 bits across the 0-1 range, comfortably more than the 8- or 10-bit
video at the far end. Only the storage dtype changes; nodes that compute in fp32
still cast up internally.

**Where the saving actually lands.** ComfyUI caches every node's output for the
run, so the upstream fp32 batch does not disappear when you cast — you gain on
what the *downstream* node allocates, less the cost of the fp16 copy. In the
247-frame example that is roughly 4.3 GB net rather than the full halving.

Put it immediately before the node whose buffer you want to shrink. Casting
earlier only makes the fp16 copy coexist with more cached fp32 batches.

---

# VAE DeGrid (Nyquist Notch)

Removes the 2px pixel grid the Qwen Image VAE (and, less strongly, the Wan 2.1
VAE) leaves across decoded images — affects Krea2, Qwen Image, **Qwen Image 2.1**,
Anima and anything else on those VAEs. The artifact is easy to miss at 100% but
any sharpening or upscaling afterwards amplifies it, so wire this **straight
after VAE Decode**, before any resize / sharpening / upscaling — and before a
diffusion restorer such as SeedVR2, which reads a regular lattice as detail worth
reconstructing. A resize will hide the grid from your eyes without removing it
from what the restorer was handed.

Ported here on 2026-08-28 from the standalone `ComfyUI-DeGrid` repo. The class id
`VAEDeGrid` is unchanged, so old workflows resolve once this pack is installed.

> **That standalone repo was un-retired on 2026-09-20 and is live again**, for
> people who want the one node without the rest of this pack. Both packs declare
> the same node id, so **do not install both** — if you do, this pack detects the
> other and stands down, printing which folder won.

## What changed on 2026-09-20

**In short:** the filter was fine — the thing deciding *when to run it* was broken.

The node used to report how much fine detail an image had and call that "the grid".
Those are not the same thing, so it got it backwards: on a real test set it called
the cleanest image the most gridded one. And because it never really knew whether a
grid was there, it filtered everything, always — quietly scraping a little genuine
texture off images that had no grid at all.

It now measures the grid itself. A VAE grid lands on the same pixel positions across
the whole frame, so averaging those positions keeps the grid while ordinary detail
cancels out. Gridded images measure about 1.6–2.0/255, grid-free ones about 0.1 — a
wide, unambiguous gap. If there is no grid, the image is now passed through
**completely untouched**, which matters most for anything that has already been
through an upscaler or a resize.

**The maths that removes the grid did not change.** On an image that really has a
grid you get exactly the same result as before.

Also: a new `skip_when_clean` widget (on by default), and the status line now names
which pattern it found and no longer claims to have removed a grid that was not there.

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `image` | required | Wire straight from VAE Decode. |
| `enabled` | `on` | Off = image passes through untouched. Flip it for a quick A/B. |
| `mode` | `auto` | **auto (recommended):** measures the grid strength per image and sets the removal limit itself. **manual:** uses the `limit` widget. Switch only if auto visibly under- or over-corrects. |
| `limit` | `0.02` | **Manual mode only** (ignored in auto). Max per-pixel correction on the 0–1 scale. VAE grid is usually 0.005–0.02. Too low → grid survives in contrasty areas; too high → fine 2–3px texture (pores, weave) softens. |
| `skip_when_clean` | `on` | Leave the image completely untouched when no grid is actually there. The node measures the lattice directly, so anything already through an upscaler or a resize passes through **bit-for-bit**. Turn off only to force the filter to run regardless. |
| `grid_gain` | `10` | Brightness amplification of the `removed_grid` preview **only** — never touches the cleaned image. |
| `grid_view` | `4x zoom` | Framing of the `removed_grid` preview. `full frame` aliases the 2px lattice into gray noise at preview size; `4x zoom` / `8x zoom` show a magnified center crop where the pattern is visible. Preview only. |

## Outputs

| Output | Type | Description |
| --- | --- | --- |
| `image` | `IMAGE` | The degridded image, same size as the input. Send it onward to sharpening / upscaling / save. |
| `removed_grid` | `IMAGE` | Visualization of what was subtracted (amplified, centered on gray). Uniform fine speckle = working. Recognizable faces/fabric = limit too high. |

After each run the node's title bar shows a status line, e.g.
`grid 1.97/255 (checker) — removed (limit 0.014 auto) · edges protected: 4.3%` —
that is your confirmation it did something, no pixel-peeping needed. The bracket
names the dominant orientation (`checker`, `V-stripe` or `H-stripe`). On an image
with no lattice you get `grid 0.16/255 — none detected, passed through untouched`
and nothing is changed.

## How it works

A separable Nyquist notch: a 9-tap alternating-sign binomial kernel (1D response
sin⁸(ω/2)), combined as `center − Bx − By + Bxy`, which factors into
`(1 − sin⁸(ωx/2))(1 − sin⁸(ωy/2))` — an exact zero for any 2px-period pattern
(stripes or checkerboard) and exact unity at DC with an 8th-order flat zero, so
gradients pass through without banding. The correction is then amplitude-clamped
before subtraction, so strong real edges and legitimate fine texture pass through
unsoftened — only the low-amplitude artifact band is removed. In `auto` the clamp
limit is estimated per image from a robust percentile of the extracted grid
component. Math core is [degrid_core.py](degrid_core.py) — pure torch, no ComfyUI
imports.

Separately from the clamp, the node decides *whether there is a grid at all* by
measuring the phase-locked lattice: the grid's phase is tied to the VAE's output
stride, so averaging the four `(y%2, x%2)` sublattices keeps it while genuine
detail cancels. Measured on Qwen Image 2.1 output that separates by about 10× —
native VAE decodes 1.6–2.0/255, the same images after an upscaler 0.10–0.20/255,
a pure-noise control 0.05/255. Below 0.5/255 the filter is skipped entirely
rather than run weakly, because the notch is cheap but not free: on a clean,
detailed image it still shaves roughly 1/255 of real high-frequency detail.

Qwen Image 2.1 ships a different VAE — architecture id `qwen_image_2.1_vae`, a
64-channel latent and four spatial upsample stages against 16 channels and three
for the Qwen-Image / Wan 2.1 VAE, so 16× spatial compression rather than 8×. It
still leaves the same 2px artifact, because the period follows the stride of the
*final* upsample stage rather than the depth of the VAE. There is no 16px "latent
grid" to chase: a phase-fold sweep over periods 5–12 shows only the even-period
harmonics of the 2px component, and an exact-bin comb test reads flat at
p=4/8/16/32.

Based on the GLSL notch-filter approach shared by
[u/Haiku-575 on r/StableDiffusion](https://www.reddit.com/r/StableDiffusion/comments/1umwhq7/2px_pixel_grid_on_krea2_from_vae_and_how_to/),
reimplemented in pure PyTorch with a narrower 9-tap kernel, amplitude limiting,
and per-image auto-calibration.

---

## Dependencies

- `Pillow`
- `numpy`

`torch`, `folder_paths` and the runtime image tensors come from ComfyUI itself.

## License

Apache License 2.0. See [LICENSE](LICENSE).
