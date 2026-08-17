# ComfyUI-SaveSimple

Two nodes. `SaveImageSimple` / "Save Image (Simple)" in [nodes.py](nodes.py), built because the existing save nodes (SaveImagePlus, was-suite Image Save) were too cluttered for what is actually needed here. `SaveVideoSimple` / "Save Video Simple" in [video_nodes.py](video_nodes.py) with its frontend in [js/save_video_simple_preview.js](js/save_video_simple_preview.js), added 2026-08-06.

## Save Video Simple — a port, not original work
Lifted from `DaSiWa_EnhancedVideoCombine` in ComfyUI-DaSiWa-Nodes. Both packs are Apache-2.0, so the licence carries over; the file headers state the changes, as section 4(b) requires. **Keep those headers.** Our changes: renamed to `SaveVideoSimple` under `Luna/Save`, added `prompt_text` + `save_prompt` writing a `.txt` sidecar, dropped their logging helper, and moved the preview route off theirs.

- **The sidecar path is derived from the finished video path** (`splitext(video_path)[0] + ".txt"`), never from a second filename counter. That is deliberate: two independent counters drift apart the moment a run fails, and then the `.txt` belongs to the previous `.mp4`.
- **The preview route is `/lunasave/video-preview`.** The original was `/dasiwa/enhanced-video-preview`, and since both packs are installed side by side, keeping their path would have registered the same aiohttp route twice and served our node from their handler.

## Gotchas
- **When lifting a node out of someone else's pack, check `WEB_DIRECTORY` before anything else.** Learned the hard way here: the Python was copied, tested and deployed, and the node arrived with no video player, no Download button, and raw `save_first_frame`/`log_level` widgets — because half its UI lives in the pack's JS, which also hides those widgets. Copying the `.py` gives you a node that works and looks half-built. The pack's `assets/*.png` screenshots show what the node is supposed to look like; compare against them.

## Why the design is what it is
- **Deliberately minimal.** Resist the urge to add features from other save nodes wholesale — the whole point is a lean alternative. Only add a widget when it is asked for.
- **`save_metadata` is a plain yes/no boolean**, not a dropdown of metadata levels — matches how it is actually used (PNG only; jpg/webp are always clean regardless of the toggle, since those formats can't carry the same text chunks).
- **Prompt sidecar (`_write_prompt_sidecar`) writes a `.txt` beside the image** with positive/negative prompt text — separate from the embedded-metadata feature, for when readable prompt text is wanted without opening the PNG's metadata.

## Gotchas
- `output_path` behavior is contextual: empty = output dir, relative = subfolder under output, absolute = exactly that dir. Don't collapse this into a single "always relative" behavior.
- `preview` only renders for files that land under the actual output dir (not arbitrary absolute paths) — that's a ComfyUI UI constraint, not a bug to "fix."
- E: install is a manual copy — re-copy `nodes.py`/`__init__.py`/`video_nodes.py`/`js/` after edits. JS changes also need a hard browser refresh (Ctrl+F5), not just a restart.

## Luna Asset Loader — added 2026-08-09

Third node in the pack, because Save Image Simple, Save Video Simple
and the loader belong in ONE pack rather than three. See `LUNA_ASSET_LOADER.md` for what
it does and `HANDOFF.md` for what is next and what not to repeat.

Shared frontend modules, written to be copied into the other Luna packs:
`js/luna_theme.mjs` (palette + role tinting), `js/luna_help.mjs` (the ⓘ panel and
output-socket hover tooltips ComfyUI does not draw), `js/luna_collapse.mjs` (the
chevron that folds a node's settings away). All three are registered from
`js/luna_pack_theme.js` with a node-name list — that list is the only per-pack part.

**Hiding a widget: `widget.hidden = true` is the flag that works.** `type =
"hidden"` leaves a canvas widget drawing its row, and DOM widgets need
`element.style.display` as well. `computeSize` already skips hidden widgets, so
the flag alone shrinks the node. Verified in 1.48.x by zeroing `widget.last_y`,
forcing `canvas.draw(true, true)` and seeing whether it comes back.

## H3 work does not belong in this pack — 2026-08-17

`Luna MiniMax H3 Canvas` left for **ComfyUI-LunaMiniMaxH3**
(github.com/lunaaispace-eng/ComfyUI-LunaMiniMaxH3), which is now the single home for
MiniMax H3 nodes. The class name did not change, so saved workflows resolve as soon as
that pack is installed — but two installed copies of one class collide, so the two packs
deploy together. The E: install was swapped in one pass.

`LUNA_MEDIA_LOADER.md` stays here for now and is the exception to watch: the node it
designs is H3's numbered video/audio references, so **build it in the H3 pack** and move
the plan across at that point. It lives here only because it is the Asset Loader's
sibling and reuses its patterns.

The shared `js/luna_*.mjs` kit is copied into the H3 pack as well. There is no cross-pack
import in ComfyUI's frontend, so a fix in one has to be copied to the other by hand.

## Licence — decides what may be borrowed

This pack is **Apache-2.0**, the house licence for these packs (also DeGrid,
StylePromptLibrary, LunaBrowser; LLM_Prompt is MIT, compatible).

- **ComfyUI-Pixaroma is MIT** and **ComfyUI-DaSiWa-Nodes is Apache-2.0** — safe to
  derive from with a header stating the changes, as `video_nodes.py` already does.
  The Asset Loader's `asset_state` schema is **derived from Pixaroma's
  `RESIZE_DEFAULTS`** (`nodes/_resize_helpers.py`) — the key names, their defaults
  and the JSON-blob approach, right down to a `resample` key this pack never
  exposed. That was originally written off here as borrowing a "vocabulary", which
  undersold it; the attribution now lives in the header of `asset_loader.py`, in
  `README.md` and in `LUNA_ASSET_LOADER.md`.
  **Pixaroma has pull requests disabled**, so there is no way to offer anything
  back or ask a question. Err on the side of over-attributing: the cost is a
  paragraph, the cost of getting it wrong is someone else's goodwill.
- **comfyui-deno-custom-nodes and ComfyUI-KJNodes are GPL-3.0.** Copying their
  code would make this whole pack GPL-3.0 and cut it off from LLM_Prompt and the
  others, which could never take code back. Read them for reference; do not lift.
- Patterns are not copyrightable, expression is. The dynamic-slot idea and the
  help-icon approach were reimplemented from the LiteGraph API, not pasted.
