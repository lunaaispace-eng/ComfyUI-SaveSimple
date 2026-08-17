# ComfyUI-SaveSimple

Four deliberately small nodes for ComfyUI: save an image, save a video, load a set
of reference images once instead of once per consumer, and cast a frame batch to
fp16. Each exists because the alternatives carried more settings than the job needs.

| Node | Category | Class |
| --- | --- | --- |
| `Luna Save Image` | `Luna/Save` | `SaveImageSimple` |
| `Luna Save Video` | `Luna/Save` | `SaveVideoSimple` |
| `Luna Asset Loader` | `Luna/Load` | `LunaAssetLoader` |
| `Luna Image Precision` | `Luna/Image` | `LunaImagePrecision` |

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
| `filename_prefix`, `save_output`, `save_metadata` | output |
| `save_first_frame`, `save_last_frame`, `save_prompt` | extras, in the player panel |

| Output | Type | Description |
| --- | --- | --- |
| `frames` | `IMAGE` | the frames as encoded |
| `filename` | `STRING` | the written video path |

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
images        IMAGE   all pictures as ONE batch, conformed to image 1's size
width, height INT     image 1's size AFTER its resize
asset_brief   STRING  "<Picture 1> = 1920x1056 (20:11, landscape); ..."
image_1 … 9   IMAGE   each at its ORIGINAL size, in card order
```

An `IMAGE` batch cannot hold mixed dimensions, so only the batch is conformed —
the numbered outputs stay untouched, because conforming them would destroy the
aspect information the model wants.

## The card UI

| Control | What it does |
| --- | --- |
| **Image slots `− N +`** | top left of the node — how many numbered outputs show; click `N` to type one |
| **Upload** | multi-select; posts to ComfyUI's `/upload/image` |
| **Clear** | empties the list |
| **Fields** | shows the raw `image_paths` / `image_count` / `asset_state` widgets |
| **drag a card** | reorder — this renumbers `<Picture N>` |
| **click a card** | selects it; the preview and resize panel follow |

Card order **is** the numbering: slot N is `<Picture N>` everywhere downstream.
`image_paths` (one filename per line) stays the source of truth, so the node still
works if you type into the field directly.

Showing fewer outputs than you have images is intentional: the extra pictures stay
loaded and a drag promotes one into an active slot, leaving the rest parked.

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

## Dependencies

- `Pillow`
- `numpy`

`torch`, `folder_paths` and the runtime image tensors come from ComfyUI itself.

## License

Apache License 2.0. See [LICENSE](LICENSE).
