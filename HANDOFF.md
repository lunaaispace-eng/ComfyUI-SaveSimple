# Handoff — Luna Asset Loader and the shared frontend, 2026-08-09

Read `LUNA_ASSET_LOADER.md` first (what the node is and why), then this (what was
decided and what is next). `CLAUDE.md` has the licence rules — they constrain what
may be borrowed, so read them before copying anything from another pack.

Everything here is deployed by plain file copy to
`E:\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-SaveSimple`. JS changes need
a hard browser refresh (Ctrl+F5), not just a restart.

## Files added in this round

| file | what |
|---|---|
| `asset_loader.py` | the node — outputs, resize engine, brief, warnings |
| `js/luna_asset_loader.js` | cards, preview, resize panel, dynamic outputs, the Image slots stepper |
| `js/luna_help.mjs` | the ⓘ panel **and** output-socket hover tooltips |
| `js/luna_collapse.mjs` | the chevron that folds a node's settings away |
| `js/luna_theme.mjs` | Luna palette + role tinting (**tinting currently off**) |
| `js/luna_pack_theme.js` | per-pack registration — the node-name lists live here |

`luna_help.mjs`, `luna_collapse.mjs` and `luna_theme.mjs` are written to be copied
into the other Luna packs unchanged; only the node-name lists in
`luna_pack_theme.js` are per-pack.

## Appearance — settled, do not "improve" it

**ComfyUI's default red title bar**, matching the other nodes in this install, and
**amber `#e0a458` for everything inside** — buttons, active chips, `<Picture N>`
badges, selection.

Two things were tried and rejected: the role tint `#33513a` on the title, and
green `<Picture N>` badges. Both are parked one line each — `DERIVE_ACCENT =
false` in the loader JS, and the commented-out `registerLunaTheme(...)` call.
Section tints stay defined in `luna_theme.mjs` and the **Settings → Luna → Node
colours** entries still work. Do not re-enable either without asking.

## `image_count` — every route applies itself, and there is no button

Changing the count grows and shrinks the sockets immediately. It originally
applied only on workflow reload (`if (!canvas)` in the widget callback), leaving
an **Update outputs** button as the only thing that worked.

That button is now **deleted, deliberately**. Once the count applied live the
button had nothing left to do, and a control whose work is always already done
cannot be told apart from a broken one — it was reported as broken twice. Adding
feedback to it was the wrong fix. The right one was to delete it and make the last
manual route automatic: `image_paths`'s widget callback is hooked, so typing a
file name by hand syncs the count and rebuilds the cards. `internalWrite` guards
that hook against the cards' own writes, which would otherwise render twice.

**Do not add the button back.** If a route ever fails to apply, hook that route.

Everything the count touches now goes through one function, `setCount`:

- The card list drives it **both ways** — upload grows it, ✕ and Clear shrink it.
  Uploading used to grow it while nothing ever shrank it, so deleting pictures
  left sockets for images that no longer existed.
- A **wired** slot is never removed. `applyCount` stops there and returns
  `{target, shown, blocked}`; the `_lunaNotice` line in the card bar reports it.
  That is the one thing the node still refuses to do, and it says so — a silent
  refusal is indistinguishable from a bug.
- The empty list is handled by `renderPreview`/`renderPanel`. `render()` used to
  early-return before reaching them, so the last selected image stayed on screen
  after Clear.

## The Image slots stepper — position is the whole point

Widgets are drawn below the slot rows, so going from 2 outputs to 9 pushed the
`image_count` widget **78 px down the node** (y 246 → 324) and the arrow slid out
from under the cursor on every click.

It is now an **Image slots** `− N +` stepper drawn in the node body, top left,
beside the four fixed outputs: **0 px of travel from 1 to 9 outputs**, against
160 px for the old widget. Mechanics borrowed from the ⓘ in `luna_help.mjs` — draw
in `onDrawForeground`, hit-test node-relative `pos`, return `true` from
`onMouseDown` so the node does not start dragging. Boxes are 28 px tall; clicking
`N` opens LiteGraph's own prompt to type a value.

**It was on the title bar first, and that was wrong — do not put it back.** The
title bar is stationary, but it is also where LiteGraph opens the rename editor on
double-click, so two quick presses on `+` renamed the node. `onDblClick` now
returns `true` inside the stepper as belt and braces.

Why the body's top-left corner is safe at every count, all measured on a live
node: fixed outputs at y 14/34/54/74, `image_1` starts at 94 so growth is all
below y≈84, the card widget never starts above y≈126, and the node's three inputs
are widget-sockets pinned to their own rows at y 276+, not the top-left column.

- `_lunaCtlRects` is cached at draw time and reused by the hit test, so drawing
  and clicking cannot disagree. That cache is **not** the forbidden kind of
  measurement — it depends on `node.size`, never on what was rendered.
- Below 300 px of node width the label is dropped and the stepper drawn alone, so
  a narrowed node cannot overlap the `asset_brief` label column.
- The body `image_count` widget is hidden and joins **Fields** as the escape
  hatch.

## Collapsing the settings

`js/luna_collapse.mjs` puts a chevron beside the ⓘ that folds a node's settings
away. On **the two save nodes only** — the Asset Loader is cards rather than
settings. Save Video Simple 665 px → 329, Save Image (Simple) 314 → 74.

The rule is **canvas widgets fold, DOM widgets stay** — not a per-node special
case. That is what keeps the video's player, first/last-frame checkboxes, Autoplay
and Download (all inside the one `video_preview` DOM widget), and gives Save Image
its preview for free, because that is ComfyUI's own image area and not a widget.

- **Only `w.hidden` is touched, and the previous value is remembered per widget.**
  Save Video Simple hides `log_level`, `save_first_frame` and `save_last_frame`
  itself using `draw`/`computeSize` overrides and redraws them in its own panel.
  Unfolding must not resurrect them, so nothing else about those widgets is
  altered and their flag goes back to exactly what it was.
- **Restoring a saved workflow fights the node.** Save Video Simple resizes itself
  on configure (`fitPreviewHeight` → `setSize(computeSize)`), and that runs while
  the widgets are still visible — the node came back folded but 657 px tall and
  empty. Fixed by re-asserting `info.size` two frames after configure. The height
  in the workflow is the truth.
- Collapsing shrinks by **the widget height that disappeared**, not to the
  computed minimum, so Save Image keeps whatever extra room it was holding for a
  preview image (previews contribute nothing to `computeSize`).

State lives in `node.properties.lunaSettingsCollapsed`, so LiteGraph serialises it
with the workflow.

## Fewer outputs than images is a feature — do not "fix" it

Nine images loaded with `image_count` at 3 shows three sockets and **keeps all
nine cards**. The spare six stay parked and a drag promotes one into an active
slot. Documented in `LUNA_ASSET_LOADER.md`. Never clamp `image_paths` to
`image_count`.

## Parked — extracting the 2 RTX nodes from the Deno pack

Not started, and **not to be started without being asked for.** Researched
2026-08-09 so the survey does not have to be re-derived.

**The motivation.** All of `comfyui-deno-custom-nodes` (23 nodes, 54 MB) is
installed for two of them, and the pack's `WEB_DIRECTORY` loads ~1.56 MB of JS on
**every** canvas — `deno_floating_tools.js`, `deno_visual_fold.js`,
`deno_node_help.js` and the rest — whether or not its nodes are used. A fork would
drop ~1.49 MB of that.

The two nodes are `DenoRTXVFXEasyUpscale` — "(Deno) RTX Video Super Resolution" —
and `DenoRTXVFXVideoFinisher` — "(Deno) RTX Video Super Resolution (2 Pass)".

**DaSiWa is not a substitute.** It has an RTX node, but 2-stage only, so it does
not cover the pair. Settled; do not re-propose it.

**The cut is clean** — verified statically. Nothing outside this list is
referenced: no dynamic imports, no aiohttp routes, no asset fetches, and
`requirements.txt` is empty.

| file | size |
|---|---|
| `deno_rtx_vfx_easy_upscale.py` | 471 lines — node 1 |
| `deno_rtx_vfx_video_finisher.py` | 246 lines — node 2, imports node 1 |
| `deno_rtx_vfx_runtime.py` | 166 lines — finds `nvvfx`; stdlib only |
| `deno_resolution_common.py` | 123 lines — ratio/resize math; stdlib only |
| `web/js/deno_rtx_vfx_easy_upscale.js` | 32 KB — imports only ComfyUI's `app.js` |
| `web/js/deno_rtx_vfx_video_finisher.js` | 35 KB — same |
| `prestartup_script.py` | 61 lines — **exists purely for the RTX runtime** |
| `tools/` | the RTX VFX installer `.bat` + guide |

**Three things decide whether it works:**

1. **Licence — GPL-3.0.** It must be a **standalone GPL-3.0 fork** in
   `D:\Claude\comfy-forks\`, keeping their LICENSE and stating the changes in the
   headers. It may **never** be folded into this pack or any Luna Apache-2.0 pack;
   see the licence section in `CLAUDE.md`.
2. **The `nvvfx` runtime is the real risk, not the code.** These wrap NVIDIA's
   Maxine VFX SDK, resolved through `tools/DENO_RTX_VFX_runtime_path.txt` — a
   marker pointing at a runtime matching the running Python version. **That marker
   is absent from the current install**, so `nvvfx` is resolving some other way.
   Establish exactly how *before* cutting over; this is what fails silently.
3. **Keep the class names and the JS extension names identical**, so existing
   workflows load untouched — which means the fork and the original can never be
   installed at the same time (duplicate class mappings, and the "Extension named
   … already registered" clash seen in the console from DaSiWa).

Estimate: about an hour, most of it verifying the runtime resolves and that both
nodes actually process a clip.

## Next, in the order agreed

1. **Build Luna Media Loader** — the numbered VIDEO/AUDIO references for H3, the
   Asset Loader's sibling. Designed 2026-08-13, agreed for the next session; the
   full spec, the survey of what already exists and the reasoning for keeping it
   out of the Asset Loader are in `LUNA_MEDIA_LOADER.md`. One decision is still
   open there — the `video_previews` output — settle it before building.
2. **Drag grip to resize the preview area only** — requested twice. This does
   **not** mean resizing the whole node. Make the dragged height an **input**
   stored on the node, never something measured from the layout (see below).
3. **⚙ cog** for node-scoped settings: preview height, columns, defaults for newly
   added images. **Not** the resize panel — that is per-image and belongs with the
   selected card. Colour does **not** go in the cog; that was settled.
4. **`Resample`** — the state key exists, is never exposed.
5. Roll `luna_help.mjs` (and `OUTPUT_TOOLTIPS`) and `luna_collapse.mjs` into
   LunaBrowser, LLM_Prompt, DeGrid, StylePromptLibrary. Pure gain: every node gets
   an ⓘ, working output hovers and a collapse chevron for one import plus a
   node-name list.
6. **Wire the loader into the real workflow** — replaces three
   `PixaromaLoadImageMini` nodes *and* `ImageBatchMulti` (node `2746` in
   `MinimaxH3T2VAR2VA.json`).

## Mistakes made here — do not repeat them

**The node broke once from measuring instead of predicting.** `cardsHeight()`
summed the rendered `panel.offsetHeight`, but the panel sits in a flex column and
can shrink — the height came from the layout and the layout came from the height,
so the card area collapsed to a strip. Height must be arithmetic, or an explicit
number the user set. Never derived from what is currently rendered.

**Four "supported" things silently do nothing in frontend 1.48.x** — each cost a
round trip, so trust the browser, not the API surface:

- `slot.hidden = true` on outputs: the flag sets, every output still draws. Real
  `addOutput`/`removeOutput` is the only way.
- `widget.type = "hidden"` on a multiline STRING: the DOM textarea keeps
  rendering. The element needs hiding too.
- `widget.type = "hidden"` on a **canvas** widget: still drawn, row and all.
  **`widget.hidden = true` is the flag that works**, and `computeSize` already
  skips hidden widgets, so the flag alone shrinks the node. The two text fields
  only looked hidden because their DOM elements were hidden separately, which
  masked this for weeks. Test by zeroing `widget.last_y`, forcing
  `canvas.draw(true, true)` and seeing whether it comes back.
- `OUTPUT_TOOLTIPS`: shipped in `object_info`, never attached to output slots —
  true for core nodes as well. `luna_help.mjs` draws them.

**A backtick in a comment inside a template literal breaks the whole file, and
the linter will not tell you.** `luna_asset_loader.js` keeps its CSS in a
template literal with explanatory `/* */` comments inside it. A comment written
as ``  `nodes/_resize_helpers.py`  `` closed the CSS string; everything after it
parsed as code, `nodes` was undefined, the module threw on import, the extension
never registered, and the node rendered as three raw widgets with no card UI.

`node --check` **passed** — the wreckage is still valid syntax. Nothing short of
loading the page catches it. When touching that CSS block, check that the only
backticks between `const CSS = ` and its closing delimiter are the two delimiters
themselves, and reload the browser before believing it works.

**Synthetic `PointerEvent`s do not drive widget clicks.** This frontend hit-tests
via `getWidgetAtCursor`, which reads the live cursor, so a simulated click proves
nothing — it "failed" while the callback worked fine. Call the handler
(`node.onMouseDown(e, pos)`) instead.

**An automation browser pane can report `document.hidden`, and then
`requestAnimationFrame` never fires** — a node whose init runs in a rAF looks
broken when it is not. Drive the callbacks synchronously when inspecting that way.

**A settings `onChange` fires before the store commits.** Reading the value inside
it gives the previous one and every change lands a step late. Defer a frame.

**Do not put another pack's custom type on a Luna socket.** A
`DENO_MINIMAX_H3_REFERENCE_IMAGES` input was added to Luna Agent Chat and rejected
— plain `IMAGE` is the common denominator across Luna Agent Chat, `LLMPromptNode`
and the native H3 nodes. The rule is in `ComfyUI-LunaBrowser/CLAUDE.md`.

## How to work on this

Reason about a change before building it, and do not stack three changes into one
turn. Verify in the browser rather than asserting from the code — several of the
bugs above were invisible until something was clicked.
