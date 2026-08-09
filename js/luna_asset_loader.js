// Luna Asset Loader — ordered reference cards, and only the outputs you asked for.
//
// Two jobs in one file:
//   1. show N numbered outputs out of the nine Python always declares
//   2. a card UI that owns the image_paths field: upload, reorder, remove
//
// On (1): ComfyUI has no dynamic outputs. Autogrow is input-only
// (comfy_api/latest/_io.py — `class Autogrow(ComfyTypeI)`), and RETURN_TYPES is a
// fixed class attribute the backend type-checks links against. So Python declares
// all nine and this hides the rest. Slot indices never move, so a link to image_3
// survives the count changing; hidden slots keep their links rather than dropping
// them, and a wired-but-hidden slot is coloured so it cannot go unnoticed.
//
// The count-widget-drives-the-slots idea is the same one KJNodes uses for its
// *Multi nodes, written here from the LiteGraph API rather than copied — KJNodes
// is GPL-3.0 and this pack is Apache-2.0. Their version needs a button pressed;
// this one applies on every change, so there is no button at all. The upload flow
// uses ComfyUI's stock /upload/image endpoint, the same one Load Image posts to.

import { app } from "../../scripts/app.js";
import { LUNA } from "./luna_theme.mjs";

const NODE = "LunaAssetLoader";
const MAX = 9;
const PATHS_WIDGET = "image_paths";
const COUNT_WIDGET = "image_count";
const PREVIEW_H = 170;   // height of the selected-image preview, in pixels

/* ------------------------------------------------------------------ styles */

// Palette comes from luna_theme.mjs — the single place the Luna colours are
// defined for this pack (itself a copy of ComfyUI-LunaRunner/web/style.css, the
// house scheme). Declared under luna- prefixed CSS variables so they cannot
// collide with ComfyUI's own. Nothing here hardcodes a colour.
//
//   accent  #e0a458  warm amber          text  #e7e5df   muted   #8b8e99
//   panel   #1c1e25  border #2e313c      radius 8px
//   section tints: input #7bb47b · processing #7da4c8 · output #d98a6a
//
// One accent throughout: the amber carries the badges, the buttons, the active
// options and the selection. The section tints stay defined in luna_theme.mjs but
// are not used here — a second colour on the same node just read as noise.
const CSS = `
.luna-al { --luna-accent:${LUNA.accent}; --luna-accent-soft:${LUNA.accentSoft}; --luna-panel:${LUNA.panel};
           --luna-border:${LUNA.border}; --luna-text:${LUNA.text}; --luna-muted:${LUNA.muted};
           --luna-input:${LUNA.input}; --luna-danger:${LUNA.danger}; --luna-bg:${LUNA.bg};
           --luna-radius:${LUNA.radius}px;
           display:flex; flex-direction:column; gap:6px; padding:6px; box-sizing:border-box;
           font-family:"Segoe UI", system-ui, sans-serif; font-size:11px; color:var(--luna-text); }
.luna-al-bar { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
.luna-al-btn { flex:0 0 auto; padding:5px 10px; border-radius:6px; cursor:pointer;
               background:var(--luna-panel); border:1px solid var(--luna-border);
               color:var(--luna-text); transition:background .1s, border-color .1s, color .1s; }
.luna-al-btn:hover { background:var(--luna-accent); border-color:var(--luna-accent); color:var(--luna-bg); }
.luna-al-btn.danger:hover { background:var(--luna-danger); border-color:var(--luna-danger); color:#fff; }
.luna-al-count { margin-left:auto; color:var(--luna-muted); }
/* Transient one-liner for the one thing the node refuses to do silently: a slot
   that will not go away because it is wired. Everything else just happens. */
.luna-al-note { color:var(--luna-accent); }
.luna-al-cards { display:grid; grid-template-columns:repeat(auto-fill, minmax(112px, 1fr));
                 gap:8px; overflow-y:auto; flex:1 1 auto; align-content:start; padding:2px; }
.luna-al-card { position:relative; border-radius:8px; overflow:hidden; cursor:grab;
                background:var(--luna-panel); border:1px solid var(--luna-border); transition:border-color .1s; }
.luna-al-card:hover { border-color:var(--luna-accent); }
.luna-al-card.drag { opacity:.35; }
.luna-al-card.over { border-color:var(--luna-accent); box-shadow:0 0 0 1px var(--luna-accent) inset; }
/* The image is the card. Everything else floats on top of it, so the picture
   gets the space instead of a column of text beside a postage stamp. */
.luna-al-thumb { display:block; width:100%; aspect-ratio:1/1; object-fit:contain;
                 background:var(--luna-bg); }
.luna-al-pic { position:absolute; top:4px; left:4px; padding:1px 6px; border-radius:5px;
               background:var(--luna-accent); color:var(--luna-bg); font-weight:700; font-size:10px; }
.luna-al-x { position:absolute; top:4px; right:4px; width:18px; height:18px; line-height:17px;
             text-align:center; border-radius:5px; cursor:pointer; font-size:11px;
             background:rgba(20,21,26,.85); color:var(--luna-muted); opacity:0; transition:opacity .1s; }
.luna-al-card:hover .luna-al-x { opacity:1; }
.luna-al-x:hover { background:var(--luna-danger); color:#fff; }
.luna-al-cap { position:absolute; left:0; right:0; bottom:0; padding:3px 5px; font-size:10px;
               background:linear-gradient(to top, rgba(12,12,15,.95), rgba(12,12,15,0)); }
.luna-al-dim { color:var(--luna-text); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.luna-al-name { opacity:.45; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.luna-al-preview { position:relative; border:1px solid var(--luna-border); border-radius:8px;
                   background:var(--luna-bg); overflow:hidden; flex:0 0 auto; }
.luna-al-preview img { display:block; width:100%; height:100%; object-fit:contain; }
.luna-al-pvlbl { position:absolute; left:6px; bottom:5px; padding:1px 6px; border-radius:5px;
                 background:rgba(20,21,26,.82); font-size:10px; color:var(--luna-text); }
.luna-al-empty { opacity:.55; padding:10px 4px; }
.luna-al-warn { color:var(--luna-accent); padding:2px 4px; }
.luna-al-card.sel { border-color:var(--luna-accent); box-shadow:0 0 0 1px var(--luna-accent) inset; }

/* Resize panel. The state schema behind it — the key names, their defaults and
   the JSON-blob approach — is modelled on ComfyUI-Pixaroma (MIT, Copyright (c)
   2026 pixaroma), nodes/_resize_helpers.py; see the header of asset_loader.py.
   Theirs edits one image so the panel is always on; ours holds up to nine, so it
   edits whichever card is selected.
   NOTE: no backticks anywhere in this block. It lives inside the CSS template
   literal, so one would close the string and turn the rest of the file into
   code. That happened once and broke the whole extension; node --check still
   passed, because the wreckage is still valid syntax. Only loading it catches
   this, so check the browser, not the linter. */
.luna-al-panel { border-top:1px solid var(--luna-border); padding-top:6px; display:flex;
                 flex-direction:column; gap:5px; }
.luna-al-row { display:flex; gap:4px; align-items:center; flex-wrap:wrap; }
.luna-al-lbl { color:var(--luna-muted); min-width:44px; }
.luna-al-seg { flex:1 1 auto; display:flex; gap:3px; }
.luna-al-opt { flex:1 1 auto; text-align:center; padding:3px 5px; border-radius:5px; cursor:pointer;
               background:var(--luna-panel); border:1px solid var(--luna-border); color:var(--luna-text); font-size:10px;
               white-space:nowrap; }
.luna-al-opt:hover { border-color:var(--luna-accent); }
.luna-al-opt.on { background:var(--luna-accent); border-color:var(--luna-accent); color:var(--luna-bg); }
.luna-al-num { width:64px; padding:3px 5px; border-radius:5px; background:var(--luna-bg);
               border:1px solid var(--luna-border); color:var(--luna-text); font-size:10px; }
.luna-al-io { opacity:.75; font-size:10px; }
.luna-al-io b { color:var(--luna-accent); font-weight:600; }
`;

function injectCSS() {
    if (document.getElementById("luna-al-css")) return;
    const s = document.createElement("style");
    s.id = "luna-al-css";
    s.textContent = CSS;
    document.head.appendChild(s);
}

/* ------------------------------------------------------------------- utils */

const widget = (node, name) => node.widgets?.find((w) => w.name === name);

function readPaths(node) {
    const w = widget(node, PATHS_WIDGET);
    return String(w?.value ?? "")
        .replace(/\r/g, "\n").split("\n")
        .map((s) => s.trim().replace(/^"|"$/g, ""))
        .filter(Boolean);
}

// Set while writePaths fires the widget callback, so the hand-edit hook on
// image_paths can tell a user typing from the cards writing — otherwise every
// card action would sync and re-render twice.
let internalWrite = false;

function writePaths(node, list) {
    const w = widget(node, PATHS_WIDGET);
    if (!w) return;
    w.value = list.join("\n");
    internalWrite = true;
    try { w.callback?.(w.value); } finally { internalWrite = false; }
    node.graph?.setDirtyCanvas(true, true);
}

// --- derived accent -------------------------------------------------------
// The widget's accent follows node.color, so ComfyUI's right-click > Colors (or
// our role theme) recolours the buttons, chips and badges too. Node colours are
// dark title-bar tones, so they are lifted to a usable lightness first.
const DEFAULT_ACCENT = LUNA.accent;   // one source: luna_theme.mjs

// targetL 0.55 rather than 0.60, and a saturation WINDOW rather than a floor.
// ComfyUI's palette is deliberately muted; forcing saturation up to 0.38 turned
// its plum (#422342, hue 300) into hot pink. Keeping the source saturation
// preserves each colour's character — the floor only rescues near-greys, and the
// ceiling stops cyan (saturation 1.0) from arriving as neon.
function brighten(hex, targetL = 0.55, minS = 0.18, maxS = 0.72) {
    const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(hex || ""));
    if (!m) return null;
    let h = m[1];
    if (h.length === 3) h = h.split("").map((c) => c + c).join("");
    const r = parseInt(h.slice(0, 2), 16) / 255,
          g = parseInt(h.slice(2, 4), 16) / 255,
          b = parseInt(h.slice(4, 6), 16) / 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
    let H = 0;
    if (d) {
        if (mx === r) H = ((g - b) / d) % 6;
        else if (mx === g) H = (b - r) / d + 2;
        else H = (r - g) / d + 4;
    }
    H *= 60; if (H < 0) H += 360;
    const L0 = (mx + mn) / 2;
    let S = d === 0 ? 0 : d / (1 - Math.abs(2 * L0 - 1));
    // A near-grey node colour has no hue worth keeping — leave the default amber
    // rather than turning the whole panel grey.
    if (S < 0.06) return null;
    S = Math.min(maxS, Math.max(S, minS));
    const C = (1 - Math.abs(2 * targetL - 1)) * S, X = C * (1 - Math.abs(((H / 60) % 2) - 1)),
          mm = targetL - C / 2;
    const seg = [[C,X,0],[X,C,0],[0,C,X],[0,X,C],[X,0,C],[C,0,X]][Math.floor(H / 60) % 6];
    const to = (v) => Math.round((v + mm) * 255).toString(16).padStart(2, "0");
    return `#${to(seg[0])}${to(seg[1])}${to(seg[2])}`;
}

// Accent derivation is OFF by default: Peti wants the amber buttons and green
// <Picture N> badges regardless of the title colour, with the title left at
// ComfyUI's default red like his other nodes. Set node._lunaDeriveAccent = true
// (or flip DERIVE_ACCENT) to make the widget follow node.color again.
const DERIVE_ACCENT = false;

function syncAccent(node, rootEl) {
    const derive = node._lunaDeriveAccent ?? DERIVE_ACCENT;
    const accent = (derive && brighten(node.color)) || DEFAULT_ACCENT;
    if (rootEl._lunaAccent === accent) return;
    rootEl._lunaAccent = accent;
    rootEl.style.setProperty("--luna-accent", accent);
    rootEl.style.setProperty("--luna-accent-soft", accent + "22");
}

const viewURL = (name) =>
    `/view?filename=${encodeURIComponent(name)}&type=input&subfolder=&rand=${Math.random()}`;

/* ------------------------------------------------------- per-image resize state */

const STATE_WIDGET = "asset_state";
const DEFAULT_ITEM = {
    mode: "off", max_mp: 2.0, longest_side: 1024, scale_factor: 1.0,
    ratio: "", ratio_action: "crop", crop_anchor: "center",
    snap: 0, allow_upscale: false,
};

function readState(node) {
    const w = widget(node, STATE_WIDGET);
    try {
        const p = JSON.parse(String(w?.value || "") || "{}");
        return { all: p.all || null, items: Array.isArray(p.items) ? p.items : [] };
    } catch { return { all: null, items: [] }; }
}

function itemAt(node, i) {
    const st = readState(node);
    return { ...DEFAULT_ITEM, ...(st.all || {}), ...(st.items[i] || {}) };
}

function writeItem(node, i, patch, toAll = false) {
    const w = widget(node, STATE_WIDGET);
    if (!w) return;
    const st = readState(node);
    if (toAll) {
        st.all = { ...(st.all || {}), ...patch };
        st.items = [];           // an explicit "apply to all" clears per-card overrides
    } else {
        while (st.items.length <= i) st.items.push({});
        st.items[i] = { ...st.items[i], ...patch };
    }
    const out = {};
    if (st.all) out.all = st.all;
    if (st.items.length) out.items = st.items;
    // Empty state means "untouched", which is what REF2VA wants — keep the field
    // literally empty rather than writing a no-op object.
    w.value = Object.keys(out).length ? JSON.stringify(out) : "";
    w.callback?.(w.value);
}

// What the Python side will produce, mirrored here so the panel can show
// INPUT -> OUTPUT before the graph runs. Kept in step with _apply_state.
function predictSize(w, h, st) {
    if (!w || !h) return [0, 0];
    let W = w, H = h;
    if (st.ratio && st.ratio.includes(":")) {
        const [rw, rh] = st.ratio.split(":").map(Number);
        const t = rw / rh;
        if (t && Math.abs(W / H - t) > 0.001) {
            if (st.ratio_action === "pad") {
                if (W / H > t) H = Math.round(W / t); else W = Math.round(H * t);
            } else {
                if (W / H > t) W = Math.round(H * t); else H = Math.round(W / t);
            }
        }
    }
    let s = 1;
    if (st.mode === "max_mp") s = Math.sqrt((Number(st.max_mp) * 1e6) / (W * H));
    else if (st.mode === "longest_side") s = Number(st.longest_side) / Math.max(W, H);
    else if (st.mode === "scale_factor") s = Number(st.scale_factor);
    if (!st.allow_upscale) s = Math.min(1, s);
    const snap = Number(st.snap) || 0;
    const fix = (v) => (snap > 1 ? Math.max(snap, Math.round(v / snap) * snap) : Math.max(1, Math.round(v)));
    return [fix(W * s), fix(H * s)];
}

// Aspect wording kept deliberately close to the Python side's _describe_ar, so the
// card and the asset_brief never disagree about what a picture is.
const COMMON_AR = [[1,1],[2,3],[3,2],[3,4],[4,3],[4,5],[5,4],[9,16],[16,9],[1,2],[2,1],[21,9]];

// Two forms on purpose. The card is ~120px wide, so anything longer than about
// "1672×941 ≈16:9" truncates — and a truncated resolution defeats the point of
// showing it. The long form goes in the tooltip, where there is room.
function describeAR(w, h) {
    if (!w || !h) return { short: "", long: "" };
    const r = w / h;
    let best = COMMON_AR[0], bd = Infinity;
    for (const [a, b] of COMMON_AR) {
        const d = Math.abs(a / b - r);
        if (d < bd) { bd = d; best = [a, b]; }
    }
    const gcd = (a, b) => (b ? gcd(b, a % b) : a);
    const g = gcd(w, h) || 1;
    const ew = w / g, eh = h / g;
    const nearest = `${best[0]}:${best[1]}`;
    if (ew === best[0] && eh === best[1]) return { short: nearest, long: nearest };
    if (Math.max(ew, eh) <= 32)
        return { short: `${ew}:${eh}`, long: `exactly ${ew}:${eh}, nearest ${nearest}` };
    return { short: `≈${nearest}`, long: `${r.toFixed(2)}:1, nearest ${nearest}` };
}

async function uploadFiles(files) {
    const saved = [];
    for (const file of files) {
        const form = new FormData();
        form.append("image", file);
        form.append("type", "input");
        form.append("overwrite", "false");
        const resp = await fetch("/upload/image", { method: "POST", body: form });
        if (!resp.ok) {
            alert(`Upload failed for ${file.name}: ${resp.status} ${resp.statusText}`);
            continue;
        }
        const data = await resp.json();
        saved.push(data.subfolder ? `${data.subfolder}/${data.name}` : data.name);
    }
    return saved;
}

/* --------------------------------------------------------------- outputs */

// The four fixed outputs (images, width, height, asset_brief) occupy slots 0-3 and
// are never touched. Only the trailing image_N slots grow and shrink.
//
// `slot.hidden` does NOT work: setting it leaves the flag on the object but the
// frontend (1.48.x) still draws every output. Verified in the browser, which is
// why this adds and removes real slots instead.
const FIXED = 4;

// Returns what happened: { target, shown, blocked }. `blocked` is the 1-based
// image_N that stopped a shrink because it is wired, 0 if nothing stopped it.
// Callers report it: a refusal that says nothing looks exactly like a bug, which
// is the mistake this node already made once.
function applyCount(node) {
    if (!node.outputs) return null;
    const w = widget(node, COUNT_WIDGET);
    if (!w) return null;
    const target = Math.max(1, Math.min(MAX, Number(w.value) || 1));
    let current = node.outputs.length - FIXED;
    let blocked = 0;

    while (current > target) {
        const idx = FIXED + current - 1;
        // Refuse to silently destroy wiring: a connected slot stays until the user
        // disconnects it. Shrinking past it stops there rather than cutting links.
        if (node.outputs[idx]?.links?.length) { blocked = current; break; }
        node.removeOutput(idx);
        current--;
    }
    while (current < target) {
        node.addOutput(`image_${current + 1}`, "IMAGE");
        current++;
    }
    node.setDirtyCanvas(true, true);
    return { target, shown: current, blocked };
}

// The one way the count is ever set — stepper, arrows, card list, hand-typed
// path, all land here. Clamped to 1..MAX; a wired slot that refuses to go says so.
function setCount(node, value) {
    const cw = widget(node, COUNT_WIDGET);
    if (!cw) return null;
    const next = Math.max(1, Math.min(MAX, Number(value) || 1));
    if (Number(cw.value) !== next) {
        cw.value = next;
        cw.callback?.(next);      // the wrapped callback re-applies the sockets
    }
    const res = applyCount(node);
    if (res?.blocked) node._lunaNotice?.(`image_${res.blocked} is wired — outputs stop there.`);
    node.setDirtyCanvas(true, true);
    return res;
}

// image_count follows the number of loaded images in BOTH directions. Upload used
// to grow it and nothing ever shrank it, so deleting pictures left the node
// showing sockets for images that no longer existed. Wired slots still survive —
// applyCount stops at them and says so.
const syncCount = (node, count) => setCount(node, count);

// Clicking the number types one. LiteGraph's own prompt, so it looks like every
// other numeric entry on the canvas.
function promptCount(node, cur, e) {
    const apply = (v) => {
        const n = parseInt(v, 10);
        if (Number.isFinite(n)) setCount(node, n);
    };
    const canvas = app.canvas || node.graph?.list_of_graphcanvas?.[0];
    if (canvas?.prompt) canvas.prompt("Outputs", cur, apply, e);
    else apply(window.prompt(`Numbered outputs (1-${MAX})`, String(cur)));
}

/* ------------------------------------------------------- the Image slots stepper */

// The count control sits in the node BODY, top-left, alongside the four fixed
// output rows. Two constraints put it exactly there, and both were measured:
//
//   1. It must not move. Widgets are drawn below the slot rows, so growing 2
//      outputs to 9 pushed the old image_count widget 78px down the node and the
//      arrow slid out from under the cursor mid-click. The four fixed outputs sit
//      at y 14/34/54/74 and image_1 starts at y 94 — everything above y≈84 is
//      stationary at every count. The card widget starts at y≈126 at the node's
//      smallest, so nothing collides.
//   2. It must not be on the TITLE BAR. That was the previous attempt: stationary,
//      but the title bar is where LiteGraph opens the rename editor on
//      double-click, so a quick double-press on + renamed the node. Do not move
//      it back up there.
//
// The node's three inputs are widget-sockets pinned to their own widget rows far
// below (y 276+), so the top-left region really is free.
const CTL = {
    left: 12, top: 8, boxH: 28, stepW: 30, numW: 40, gap: 5,
    label: "Image slots", labelGap: 10, minWidthForLabel: 300,
};

function countCtlRects(node, ctx) {
    // Pure arithmetic on node.size — never measured from what is rendered, which
    // is the rule that keeps a layout from feeding back into itself.
    let x = CTL.left;
    let label = null;
    if (node.size[0] >= CTL.minWidthForLabel) {
        // Measuring a STRING is fine; measuring the LAYOUT is what is forbidden.
        const w = ctx ? ctx.measureText(CTL.label).width : CTL.label.length * 6.2;
        label = [x, CTL.top, w, CTL.boxH];
        x += w + CTL.labelGap;
    }
    const y = CTL.top;
    const r = (rx, rw) => [rx, y, rw, CTL.boxH];
    return {
        label,
        minus: r(x, CTL.stepW),
        num:   r(x + CTL.stepW + CTL.gap, CTL.numW),
        plus:  r(x + CTL.stepW + CTL.gap + CTL.numW + CTL.gap, CTL.stepW),
    };
}

const inRect = (pos, r) =>
    pos[0] >= r[0] && pos[0] <= r[0] + r[2] && pos[1] >= r[1] && pos[1] <= r[1] + r[3];

// Which part is under the cursor, or "" — one function for draw, hover and click
// so they can never disagree about where the boxes are.
function ctlHit(node, pos) {
    const rects = node._lunaCtlRects || countCtlRects(node, null);
    if (inRect(pos, rects.minus)) return "minus";
    if (inRect(pos, rects.num)) return "num";
    if (inRect(pos, rects.plus)) return "plus";
    return "";
}

function drawCtl(node, ctx) {
    const FONT = "'Segoe UI', system-ui, sans-serif";
    ctx.save();
    ctx.font = `12px ${FONT}`;                 // set BEFORE measuring the label
    const rects = countCtlRects(node, ctx);
    node._lunaCtlRects = rects;                // hit tests reuse exactly what was drawn
    const value = Math.max(1, Math.min(MAX, Number(widget(node, COUNT_WIDGET)?.value) || 1));
    const hot = node._lunaCtlHover || "";

    if (rects.label) {
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillStyle = LUNA.muted;
        ctx.fillText(CTL.label, rects.label[0], rects.label[1] + rects.label[3] / 2 + 0.5);
    }

    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const box = (r, glyph, key) => {
        const live = hot === key;
        // A disabled end-stop reads as broken unless it looks disabled.
        const dead = (key === "minus" && value <= 1) || (key === "plus" && value >= MAX);
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(r[0], r[1], r[2], r[3], 5);
        else ctx.rect(r[0], r[1], r[2], r[3]);
        ctx.fillStyle = live && !dead ? LUNA.accent : LUNA.panel;
        ctx.fill();
        ctx.strokeStyle = dead ? LUNA.border : live ? LUNA.accent : LUNA.accentSoft;
        ctx.lineWidth = live ? 1.6 : 1.2;
        ctx.stroke();
        // Amber glyphs on the steppers so the control reads as a control at a
        // glance — Peti's ask was not having to hunt for it.
        ctx.fillStyle = dead ? LUNA.muted : live ? LUNA.bg : (key === "num" ? LUNA.text : LUNA.accent);
        ctx.font = `bold ${key === "num" ? 14 : 17}px ${FONT}`;
        ctx.fillText(glyph, r[0] + r[2] / 2, r[1] + r[3] / 2 + (key === "num" ? 0.5 : 0));
    };
    box(rects.minus, "−", "minus");
    box(rects.num, String(value), "num");
    box(rects.plus, "+", "plus");
    ctx.restore();
}

/* ------------------------------------------------------------------- cards */

function buildUI(node) {
    injectCSS();
    const root = document.createElement("div");
    root.className = "luna-al";

    const bar = document.createElement("div");
    bar.className = "luna-al-bar";
    const cards = document.createElement("div");
    cards.className = "luna-al-cards";
    // A larger look at whichever card is selected. The grid shows what you have;
    // this shows what you are about to act on — the resize panel underneath edits
    // exactly this picture.
    const preview = document.createElement("div");
    preview.className = "luna-al-preview";
    const previewImg = document.createElement("img");
    const previewLbl = document.createElement("div");
    previewLbl.className = "luna-al-pvlbl";
    preview.append(previewImg, previewLbl);

    const panel = document.createElement("div");
    panel.className = "luna-al-panel";
    root.append(bar, cards, preview, panel);

    let selected = 0;                 // which card the resize panel edits
    const natural = new Map();        // filename -> [w, h], filled as thumbs decode

    const picker = document.createElement("input");
    picker.type = "file";
    picker.accept = "image/*";
    picker.multiple = true;
    picker.style.display = "none";
    root.appendChild(picker);

    const mkBtn = (label, cls, fn) => {
        const b = document.createElement("div");
        b.className = `luna-al-btn${cls ? " " + cls : ""}`;
        b.textContent = label;
        b.onclick = fn;
        bar.appendChild(b);
        return b;
    };

    mkBtn("Upload", "", () => picker.click());
    mkBtn("Clear", "danger", () => { writePaths(node, []); syncCount(node, 0); render(); });

    // image_paths and asset_state are hidden once the cards own them — two
    // multiline boxes were taking most of the node. They stay reachable, because
    // image_paths remains the source of truth and typing into it must still work
    // if the frontend ever misbehaves.
    // image_count joins them: the title-bar stepper owns it now, and leaving a
    // second copy in the body would be the control that slides around. Fields
    // brings all three back, so there is still a way in if the stepper misbehaves.
    let fieldsShown = false;
    const setFieldsVisible = (show) => {
        for (const name of [PATHS_WIDGET, COUNT_WIDGET, "asset_state"]) {
            const w = widget(node, name);
            if (!w) continue;
            // `w.hidden` is the flag that actually works. Measured in 1.48.x by
            // zeroing last_y and redrawing: with type="hidden" alone the widget is
            // still drawn, with hidden=true it is skipped. The text widgets only
            // looked hidden before because their DOM elements were hidden below —
            // image_count has no element, so it kept drawing its row.
            w.hidden = !show;
            if (show) {
                w.type = w._lunaType ?? w.type;
                delete w.computeSize;
            } else {
                w._lunaType = w._lunaType ?? w.type;
                w.type = "hidden";
                w.computeSize = () => [0, -4];
            }
            // Multiline STRING widgets are DOM textareas in this frontend, so
            // neither flag moves them — the element has to go too.
            if (w.element) {
                w.element.hidden = !show;
                w.element.style.display = show ? "" : "none";
            }
        }
        node.setDirtyCanvas(true, true);
    };
    const fieldsBtn = mkBtn("Fields", "", () => {
        fieldsShown = !fieldsShown;
        setFieldsVisible(fieldsShown);
        fieldsBtn.textContent = fieldsShown ? "Hide fields" : "Fields";
    });
    fieldsBtn.title = "Show the raw image_paths / image_count / asset_state widgets";
    requestAnimationFrame(() => setFieldsVisible(false));

    // Says what the last click did, then clears itself. Node-local on purpose:
    // a toast for something this small would fire across the whole canvas.
    const note = document.createElement("div");
    note.className = "luna-al-note";
    bar.appendChild(note);
    let noteTimer = 0;
    const notice = (msg) => {
        note.textContent = msg || "";
        clearTimeout(noteTimer);
        if (msg) noteTimer = setTimeout(() => { note.textContent = ""; }, 3000);
    };
    node._lunaNotice = notice;

    const counter = document.createElement("div");
    counter.className = "luna-al-count";
    bar.appendChild(counter);

    picker.onchange = async () => {
        const files = Array.from(picker.files || []);
        picker.value = "";
        if (!files.length) return;
        const names = await uploadFiles(files);
        if (!names.length) return;
        const next = readPaths(node).concat(names).slice(0, MAX);
        writePaths(node, next);
        // The card list drives the socket count, both ways. The arrows still
        // override it by hand; the override holds until the list changes again.
        syncCount(node, next.length);
        render();
    };

    let dragFrom = -1;

    function render() {
        const paths = readPaths(node);
        cards.replaceChildren();
        counter.textContent = `${paths.length} / ${MAX}`;

        // No early return on the empty list. It used to return here, which skipped
        // renderPreview/renderPanel — both handle "nothing loaded" correctly, they
        // just never ran, so the last selected image stayed on screen after Clear.
        if (!paths.length) {
            const e = document.createElement("div");
            e.className = "luna-al-empty";
            e.textContent = "No images. Press Upload, or type file names in image_paths below.";
            cards.appendChild(e);
        }
        if (paths.length > MAX) {
            const warn = document.createElement("div");
            warn.className = "luna-al-warn";
            warn.textContent = `MiniMax H3 takes at most ${MAX} references.`;
            cards.appendChild(warn);
        }

        paths.forEach((name, i) => {
            const card = document.createElement("div");
            card.className = "luna-al-card" + (i === selected ? " sel" : "");
            card.draggable = true;
            // Selecting is what makes a nine-image node editable: the resize panel
            // below edits whichever card is selected, so REF2VA references can stay
            // untouched while slots 1 and 2 get conformed.
            card.onclick = () => { selected = i; render(); };

            const img = document.createElement("img");
            img.className = "luna-al-thumb";
            img.src = viewURL(name);

            const pic = document.createElement("div");
            pic.className = "luna-al-pic";
            pic.textContent = i + 1;
            pic.title = `<Picture ${i + 1}>`;

            const cap = document.createElement("div");
            cap.className = "luna-al-cap";
            const dim = document.createElement("div");
            dim.className = "luna-al-dim";
            dim.textContent = "…";
            const nm = document.createElement("div");
            nm.className = "luna-al-name";
            nm.textContent = name;
            nm.title = name;
            cap.append(dim, nm);

            // Original size and aspect, read off the decoded image — the whole
            // point is to see what you actually loaded before choosing the
            // generation resolution.
            img.onload = () => {
                const w = img.naturalWidth, h = img.naturalHeight;
                const ar = describeAR(w, h);
                dim.textContent = `${w}×${h} ${ar.short}`;
                card.title = `<Picture ${i + 1}>  —  ${w} × ${h} (${ar.long})\n${name}`;
                // The panel's INPUT → OUTPUT preview needs the decoded size, which
                // only exists once the thumbnail has loaded.
                natural.set(name, [w, h]);
                if (i === selected) renderPanel();
            };
            img.onerror = () => { dim.textContent = "missing from input folder"; };

            const x = document.createElement("div");
            x.className = "luna-al-x";
            x.textContent = "✕";
            x.title = "Remove";
            x.onclick = (ev) => {
                ev.stopPropagation();
                const next = readPaths(node);
                next.splice(i, 1);
                writePaths(node, next);
                syncCount(node, next.length);
                render();
            };

            card.addEventListener("dragstart", () => { dragFrom = i; card.classList.add("drag"); });
            card.addEventListener("dragend", () => { dragFrom = -1; card.classList.remove("drag"); render(); });
            card.addEventListener("dragover", (ev) => { ev.preventDefault(); card.classList.add("over"); });
            card.addEventListener("dragleave", () => card.classList.remove("over"));
            card.addEventListener("drop", (ev) => {
                ev.preventDefault();
                card.classList.remove("over");
                if (dragFrom < 0 || dragFrom === i) return;
                const next = readPaths(node);
                const [moved] = next.splice(dragFrom, 1);
                next.splice(i, 0, moved);
                writePaths(node, next);   // reorder IS the renumbering
                render();
            });

            card.append(img, pic, x, cap);
            cards.appendChild(card);
        });

        syncAccent(node, root);
        renderPreview();
        renderPanel();

        // The widget's getHeight depends on how many cards there are, so a redraw
        // has to follow any change to the list or the node keeps its old height.
        node.setDirtyCanvas(true, true);
    }

    function renderPreview() {
        const paths = readPaths(node);
        if (!paths.length) {
            // Drop the picture as well as hiding the box: leaving the src set kept
            // the removed image decoded, and the dataset guard below would then
            // skip re-setting it if the same file were uploaded again.
            preview.style.display = "none";
            previewImg.removeAttribute("src");
            previewImg.dataset.name = "";
            previewLbl.textContent = "";
            selected = 0;
            return;
        }
        if (selected >= paths.length) selected = 0;
        preview.style.display = "";
        preview.style.height = PREVIEW_H + "px";
        const name = paths[selected];
        // Reuse the card's already-decoded copy: same URL, so the browser serves
        // it from cache instead of fetching the picture a second time.
        if (previewImg.dataset.name !== name) {
            previewImg.dataset.name = name;
            previewImg.src = viewURL(name);
        }
        const nat = natural.get(name);
        previewLbl.textContent = nat
            ? `<Picture ${selected + 1}>  ${nat[0]}×${nat[1]} ${describeAR(nat[0], nat[1]).short}`
            : `<Picture ${selected + 1}>`;
    }

    /* ------------------------------------------------------------- resize panel */

    function renderPanel() {
        panel.replaceChildren();
        const paths = readPaths(node);
        if (!paths.length) return;
        if (selected >= paths.length) selected = 0;

        const st = itemAt(node, selected);
        const name = paths[selected];
        const nat = natural.get(name);

        const row = (label) => {
            const r = document.createElement("div");
            r.className = "luna-al-row";
            if (label !== null) {
                const l = document.createElement("div");
                l.className = "luna-al-lbl";
                l.textContent = label;
                r.appendChild(l);
            }
            panel.appendChild(r);
            return r;
        };
        const seg = (parent, opts, current, onPick) => {
            const s = document.createElement("div");
            s.className = "luna-al-seg";
            for (const [val, text] of opts) {
                const o = document.createElement("div");
                o.className = "luna-al-opt" + (val === current ? " on" : "");
                o.textContent = text;
                o.onclick = () => onPick(val);
                s.appendChild(o);
            }
            parent.appendChild(s);
            return s;
        };
        const set = (patch) => { writeItem(node, selected, patch); render(); };

        // which picture the panel is editing
        const head = row(null);
        const who = document.createElement("div");
        who.className = "luna-al-io";
        const out = nat ? predictSize(nat[0], nat[1], st) : null;
        who.innerHTML = nat
            ? `<b>&lt;Picture ${selected + 1}&gt;</b> &nbsp; ${nat[0]}×${nat[1]} → <b>${out[0]}×${out[1]}</b>`
            : `<b>&lt;Picture ${selected + 1}&gt;</b>`;
        head.appendChild(who);

        const r1 = row("Size");
        seg(r1, [["off", "Off"], ["max_mp", "Max MP"], ["longest_side", "Longest"],
                 ["scale_factor", "Scale ×"]], st.mode, (v) => set({ mode: v }));

        if (st.mode !== "off") {
            const r2 = row("");
            const inp = document.createElement("input");
            inp.className = "luna-al-num";
            inp.type = "number";
            inp.step = st.mode === "max_mp" ? "0.1" : (st.mode === "scale_factor" ? "0.05" : "32");
            inp.value = st.mode === "max_mp" ? st.max_mp
                      : st.mode === "longest_side" ? st.longest_side : st.scale_factor;
            inp.onchange = () => {
                const k = st.mode === "max_mp" ? "max_mp"
                        : st.mode === "longest_side" ? "longest_side" : "scale_factor";
                set({ [k]: Number(inp.value) });
            };
            r2.appendChild(inp);
            const up = document.createElement("div");
            up.className = "luna-al-opt" + (st.allow_upscale ? " on" : "");
            up.textContent = "Upscale";
            up.title = "H3 never upscales a reference itself — this is the only place it can happen";
            up.onclick = () => set({ allow_upscale: !st.allow_upscale });
            r2.appendChild(up);
        }

        const r3 = row("Ratio");
        seg(r3, [["", "Source"], ["1:1", "1:1"], ["2:3", "2:3"], ["3:2", "3:2"],
                 ["9:16", "9:16"], ["16:9", "16:9"]], st.ratio, (v) => set({ ratio: v }));

        if (st.ratio) {
            const r4 = row("");
            seg(r4, [["crop", "Crop to fill"], ["pad", "Pad"]], st.ratio_action,
                (v) => set({ ratio_action: v }));
        }

        const r5 = row("Snap");
        seg(r5, [[0, "Off"], [8, "8"], [16, "16"], [32, "32"], [64, "64"]],
            Number(st.snap) || 0, (v) => set({ snap: v }));

        const r6 = row(null);
        const all = document.createElement("div");
        all.className = "luna-al-btn";
        all.textContent = "Apply to all";
        all.title = "Use these settings for every image and drop per-image overrides";
        all.onclick = () => {
            const { mode, max_mp, longest_side, scale_factor, ratio, ratio_action, snap, allow_upscale } = st;
            writeItem(node, 0, { mode, max_mp, longest_side, scale_factor, ratio, ratio_action, snap, allow_upscale }, true);
            render();
        };
        const reset = document.createElement("div");
        reset.className = "luna-al-btn danger";
        reset.textContent = "Reset";
        reset.onclick = () => { const w = widget(node, STATE_WIDGET); if (w) { w.value = ""; w.callback?.(""); } render(); };
        r6.append(all, reset);
    }

    return { root, render, selectCard: (i) => { selected = i; renderPanel(); }, natural };
}

/* ---------------------------------------------------------------- register */

app.registerExtension({
    name: "LunaSaveSimple.AssetLoader",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== NODE) return;

        const onCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onCreated?.apply(this, arguments);

            const ui = buildUI(this);
            // Size the card area to its contents, the same way this pack's video
            // preview widget does. Without it the two multiline text fields take
            // the node's height and the cards get a single visible row.
            // Grid: work out how many rows the cards will wrap into at the node's
            // current width, so the node grows by row rather than by image.
            const CELL = 120, BAR = 34, PAD = 16, MINH = 150, MAXH = 720;
            const cardsHeight = () => {
                const list = readPaths(this);
                const cols = Math.max(1, Math.floor((this.size[0] - 24) / CELL));
                const rows = Math.max(1, Math.ceil(list.length / cols));
                // The resize panel only exists once there is something to resize,
                // and grows a row when a mode or a ratio is chosen.
                let panel = 0;
                if (list.length) {
                    const st = itemAt(this, 0);
                    panel = 118 + (st.mode !== "off" ? 26 : 0) + (st.ratio ? 26 : 0);
                }
                // The preview is a fixed block, so it stays arithmetic like the
                // rest — nothing here is measured from the rendered layout.
                const pv = list.length ? PREVIEW_H + 6 : 0;
                return Math.min(MAXH, Math.max(MINH, BAR + PAD + rows * CELL + pv + panel));
            };
            const w = this.addDOMWidget("luna_asset_cards", "div", ui.root, {
                serialize: false,
                hideOnZoom: false,
                getHeight: cardsHeight,
            });
            w.computeSize = (width) => [width, cardsHeight()];
            this._lunaRender = () => { ui.render(); this.setDirtyCanvas(true, true); };
            this._lunaRoot = ui.root;

            // There is no "Update outputs" button any more, deliberately. Every
            // route into the node now applies itself — the arrows, upload, remove,
            // Clear, and typing into image_paths (hooked below). A button whose
            // work is always already done cannot be told apart from a broken one,
            // and it read as broken. Do not add it back to "be safe"; add the
            // missing automatic path instead.
            const cw = widget(this, COUNT_WIDGET);
            if (cw) {
                const orig = cw.callback;
                const self = this;
                cw.callback = function (value, canvas) {
                    const out = orig ? orig.apply(this, arguments) : undefined;
                    // Apply on EVERY change, interactive or not. This used to fire
                    // only on workflow reload, which left the count and the sockets
                    // disagreeing until you found the button. Changing the number
                    // IS the action.
                    const res = applyCount(self);
                    if (res?.blocked)
                        self._lunaNotice?.(`image_${res.blocked} is wired — outputs stop there.`);
                    return out;
                };
            }

            // Typing into image_paths was the last route the cards did not own —
            // it was the button's one real job. Now the field syncs the count and
            // rebuilds the cards itself. `internalWrite` keeps the cards' own
            // writes from coming back through here and rendering twice.
            const pw = widget(this, PATHS_WIDGET);
            if (pw) {
                const origPaths = pw.callback;
                const self = this;
                pw.callback = function (value) {
                    const out = origPaths ? origPaths.apply(this, arguments) : undefined;
                    if (!internalWrite) {
                        syncCount(self, readPaths(self).length);
                        self._lunaRender?.();
                    }
                    return out;
                };
            }

            if (this.size[1] < 320) this.size[1] = 320;
            requestAnimationFrame(() => { applyCount(this); ui.render(); });
            return r;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure?.apply(this, arguments);
            requestAnimationFrame(() => { applyCount(this); this._lunaRender?.(); });
            return r;
        };

        // Right-click > Colors fires no event, so pick the change up on the next
        // draw. syncAccent early-outs unless the colour actually differs.
        const onDraw = nodeType.prototype.onDrawForeground;
        nodeType.prototype.onDrawForeground = function (ctx) {
            const r = onDraw?.apply(this, arguments);
            if (this._lunaRoot) syncAccent(this, this._lunaRoot);
            if (!this.flags?.collapsed && ctx) drawCtl(this, ctx);
            return r;
        };

        // The stepper's click. Returning true consumes the event so LiteGraph does
        // not start dragging the node out from under a button press.
        const onDown = nodeType.prototype.onMouseDown;
        nodeType.prototype.onMouseDown = function (e, pos) {
            if (!this.flags?.collapsed) {
                const part = ctlHit(this, pos);
                if (part) {
                    const cur = Math.max(1, Math.min(MAX, Number(widget(this, COUNT_WIDGET)?.value) || 1));
                    if (part === "minus") setCount(this, cur - 1);
                    else if (part === "plus") setCount(this, cur + 1);
                    else promptCount(this, cur, e);   // click the number to type one
                    return true;
                }
            }
            return onDown?.apply(this, arguments);
        };

        // Swallow double-clicks that land on the stepper. This is the bug that
        // moved the control off the title bar: two quick presses on + there opened
        // LiteGraph's rename editor. Down here the title cannot be hit at all, and
        // this stops any other double-click behaviour the frontend may attach to
        // the node body from firing between two increments.
        const onDbl = nodeType.prototype.onDblClick;
        nodeType.prototype.onDblClick = function (e, pos) {
            if (!this.flags?.collapsed && ctlHit(this, pos)) return true;
            return onDbl?.apply(this, arguments);
        };

        const onMove = nodeType.prototype.onMouseMove;
        nodeType.prototype.onMouseMove = function (e, pos) {
            const part = this.flags?.collapsed ? "" : ctlHit(this, pos);
            if (part !== (this._lunaCtlHover || "")) {
                this._lunaCtlHover = part;
                this.setDirtyCanvas(true, false);
            }
            return onMove?.apply(this, arguments);
        };
    },
});
