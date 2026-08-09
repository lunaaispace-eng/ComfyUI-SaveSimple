# Luna Asset Loader

`Luna/Load` → **Luna Asset Loader**. One ordered set of reference images, fed to
every consumer that wants them, loaded once.

Built 2026-08-09 to replace a pattern that wired each picture twice: three
`PixaromaLoadImageMini` nodes going *both* into an `ImageBatchMulti` (for the
prompt writer) *and* individually into `MiniMaxH3ReferenceToVideo`.

## What it outputs, and why there are two kinds

```
images        IMAGE   all pictures as ONE batch, conformed to image 1's size
width, height INT     image 1's size AFTER its resize
asset_brief   STRING  "<Picture 1> = 1920x1056 (20:11, landscape); ..."
image_1 … 9   IMAGE   each at its ORIGINAL size, in card order
```

An `IMAGE` batch **cannot hold mixed dimensions**, and H3's REF2VA path
deliberately keeps every reference at its own aspect ratio — conforming them
there destroys information the model wants. So the numbered outputs stay
untouched and only the batch is conformed. Its consumers (Luna Agent Chat, LLM
Prompt) re-encode each frame to JPEG individually anyway, so conforming costs
nothing downstream.

**Output order is fixed-first on purpose.** ComfyUI maps outputs to the returned
tuple **by index**, and the frontend removes trailing slots to shrink the node.
With `image_N` first, dropping `image_3` would silently hand image 3's tensor to
`images`.

## Wiring

```
Luna Asset Loader
  image_1 ─→ MiniMax H3 Reference to Video . ref_image_0     (REF2VA)
  image_2 ─→ ................................ ref_image_1
  image_1 ─→ MiniMax H3 Image to Video . first_frame         (FL2VA)
  image_2 ─→ ...........................  last_frame
  images  ─→ Luna Agent Chat . images   /  LLM Prompt . image
  width/height ─→ the generation nodes
  asset_brief  ─→ prepend to the prompt so the writer knows which is which
```

Card order **is** the numbering: slot N is `<Picture N>` everywhere downstream.
Drag a card to position 1 and it becomes `<Picture 1>` for the backend, not just
on screen.

## The UI

| control | what it does |
|---|---|
| **Image slots `− N +`** | top left of the node — how many numbered outputs show; click `N` to type one |
| **Upload** | multi-select; posts to ComfyUI's `/upload/image` |
| **Clear** | empties the list |
| **Fields** | shows the raw `image_paths` / `image_count` / `asset_state` widgets |
| **cards** | thumbnail, `N` badge, `1672×941 ≈16:9`, filename; ✕ on hover |
| **drag a card** | reorder — this renumbers `<Picture N>` |
| **click a card** | selects it; the preview and resize panel follow |
| **preview** | the selected image, larger, with its size and aspect |
| **⚙ ⓘ** | the ⓘ in the title bar opens the help panel |

`image_paths` (one filename per line) stays the source of truth — the cards
write it. If the frontend ever breaks, type into the field and the node still
works.

### The count sits beside the fixed outputs for a reason

Widgets are drawn below the slot rows, so growing 2 outputs to 9 pushed the
`image_count` widget **78 px down the node** — measured — and the arrow slid out
from under the cursor mid-click.

The four fixed outputs sit at y 14/34/54/74 and `image_1` starts at 94, so the
top-left corner of the body is stationary at every count, and the card widget
never starts above y≈126. The stepper lives there.

**Not the title bar**, which is also stationary and was tried: that is where
LiteGraph opens the rename editor on double-click, so two quick presses on `+`
renamed the node. The body widget is hidden (**Fields** brings it back); the
stepper is the control.

### Fewer outputs than images is a feature

`image_count` sets how many sockets show; it does **not** trim the card list. Load
nine, show three, and the other six stay loaded — drag one up into positions 1-3
to swap it into an active slot and the rest stay parked. A bench of alternates,
one drag from being live. Do not "fix" this by clamping `image_paths` to
`image_count`.

## Per-image resize

`mode` defaults to **`off`**: nothing is touched unless asked. That default is
the point — REF2VA wants originals.

| row | options |
|---|---|
| **Size** | Off · Max MP · Longest · Scale × (+ value, + `Upscale` toggle) |
| **Ratio** | Source · 1:1 · 2:3 · 3:2 · 9:16 · 16:9 |
| *(with a ratio)* | Crop to fill · Pad |
| **Snap** | Off · 8 · 16 · 32 · 64 — **32 matches H3's `CANVAS_MULTIPLE`** |
| | **Apply to all** (clears per-image overrides) · **Reset** |

Order of operations: **aspect → size → snap**. Cropping after scaling would undo
the size you asked for.

`Upscale` is off by default and matters specifically because **H3 never upscales
a reference** (`scale = min(1.0, …)`) — the loader is the only place it can
happen, so it has to be deliberate.

Stored in `asset_state` as JSON, editable by hand:

```json
{"items": [{"ratio":"16:9","snap":32}, {"ratio":"16:9","snap":32}]}
```

`{"all": {...}}` applies one state to every image; `items` wins over `all`.
Malformed JSON falls back to defaults rather than failing the run.

### The FL2VA warning

If pictures 1 and 2 differ in aspect by more than 2%, the node prints a warning
and appends it to `asset_brief`. This is not cosmetic:

- `first_frame` → `crop="disabled"` → **stretched**, aspect ignored
- `last_frame` → `crop="center"` → **cropped**

Neither errors. For REF2VA it is fine — each reference keeps its own aspect.

The threshold is **relative (2%)**, not absolute: snapping to /32 moves the
aspect by up to ~1% on its own, so a tighter test warns on every snapped pair.

## What it will never do

**No black frames.** Skipped entries are skipped; a missing file **raises** with
the filename. `ImageBatchMulti` substitutes `torch.zeros(...)` for a bypassed
input — that is where the black screens came from. A missing file must fail
loudly, because silently dropping `<Picture 2>` would renumber every reference
after it and mislabel the whole prompt.

## Documentation lives in Python

`DESCRIPTION`, input `tooltip`s and `OUTPUT_TOOLTIPS` are the only copies. They
surface as the hover text **and** as the Inputs/Outputs tables in the ⓘ panel, so
nothing can drift. Adding a tooltip is adding documentation in both places.

Note: ComfyUI ships `OUTPUT_TOOLTIPS` in `object_info` but its 1.48.x frontend
never renders them on output sockets — verified against the core `VAEDecode`
node, which has one and shows nothing either. `js/luna_help.mjs` draws them.
