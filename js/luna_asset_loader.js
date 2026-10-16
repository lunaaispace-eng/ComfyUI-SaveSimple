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

/* Sound cards and the song editor (v3). Pink marks sound everywhere, the same
   colour ComfyUI gives AUDIO sockets, so a sound card cannot be mistaken for a
   picture. Still no backticks in here. */
.luna-al-card.snd { cursor:pointer; }
.luna-al-snd { display:block; width:100%; aspect-ratio:1/1; background:var(--luna-bg); }
.luna-al-pic.snd { background:#e07bb4; }
.luna-al-aed { display:flex; flex-direction:column; gap:6px; border:1px solid var(--luna-border);
               border-radius:8px; background:var(--luna-bg); padding:7px; }
.luna-al-ahead { display:flex; align-items:center; gap:8px; color:var(--luna-muted); font-size:10.5px; }
.luna-al-ahead b { color:#e07bb4; font-size:11px; }
.luna-al-ahead .sp { flex:1 1 auto; }
.luna-al-play { width:26px; height:20px; border-radius:5px; border:1px solid var(--luna-border);
                background:var(--luna-panel); color:var(--luna-text); text-align:center; line-height:18px; cursor:pointer; }
.luna-al-play:hover { border-color:var(--luna-accent); color:var(--luna-accent); }
.luna-al-wave { position:relative; height:64px; border-radius:6px; background:#101116; overflow:hidden; cursor:crosshair; }
.luna-al-wave canvas, .luna-al-zoom canvas { position:absolute; inset:0; width:100%; height:100%; }
.luna-al-win { position:absolute; top:0; bottom:0; background:#e0a45826; border-left:2px solid var(--luna-accent);
               border-right:2px solid var(--luna-accent); cursor:grab; box-sizing:border-box; }
.luna-al-win .h { position:absolute; top:0; bottom:0; width:10px; cursor:ew-resize; }
.luna-al-win .h.l { left:-6px; } .luna-al-win .h.r { right:-6px; }
.luna-al-win.locked .h { cursor:not-allowed; }
.luna-al-win .tag { position:absolute; top:2px; left:4px; font-size:10px; color:var(--luna-accent);
                    white-space:nowrap; text-shadow:0 1px 2px #000; pointer-events:none; }
.luna-al-ph { position:absolute; top:0; bottom:0; width:2px; background:#fff; display:none; pointer-events:none; }
.luna-al-ruler { position:relative; height:12px; font-size:9.5px; color:var(--luna-muted); }
.luna-al-ruler span { position:absolute; transform:translateX(-50%); white-space:nowrap; }
.luna-al-zoom { position:relative; height:40px; border-radius:6px; background:#101116; overflow:hidden; cursor:ew-resize; }
.luna-al-zlbl { display:flex; justify-content:space-between; font-size:10px; color:var(--luna-muted); }
.luna-al-nums { display:grid; grid-template-columns:auto auto auto 1fr; gap:5px 7px; align-items:center; font-size:10.5px; }
.luna-al-nums .l { color:var(--luna-muted); }
.luna-al-nf { display:flex; align-items:center; gap:3px; }
.luna-al-nf input { width:74px; padding:3px 5px; border-radius:5px; background:#0d0e12; border:1px solid var(--luna-border);
                    color:var(--luna-text); font:11px ui-monospace, Consolas, monospace; text-align:center; }
.luna-al-nf input:focus { outline:none; border-color:var(--luna-accent); }
.luna-al-nf input.lockd { color:var(--luna-accent); border-color:#e0a45855; background:#e0a45810; }
.luna-al-nud { width:20px; height:20px; border-radius:4px; border:1px solid var(--luna-border); background:var(--luna-panel);
               color:var(--luna-muted); text-align:center; line-height:18px; cursor:pointer; user-select:none; }
.luna-al-nud:hover { color:var(--luna-accent); border-color:var(--luna-accent); }
.luna-al-lock { font-size:10px; color:var(--luna-accent); white-space:nowrap; }
.luna-al-astat { font-size:10px; color:var(--luna-muted); border-top:1px solid var(--luna-border); padding-top:5px; line-height:1.45; }
.luna-al-astat b { color:var(--luna-text); font-weight:600; }
.luna-al-astat .w { color:#f0a49a; }

/* Video cards and the clip editor (v3). Orange marks clips, pink sound. */
.luna-al-pic.vid { background:#d98a6a; }
.luna-al-vthumb { display:block; width:100%; aspect-ratio:1/1; object-fit:cover; background:var(--luna-bg); }
.luna-al-ved { display:flex; flex-direction:column; gap:6px; border:1px solid var(--luna-border);
               border-radius:8px; background:var(--luna-bg); padding:7px; }
.luna-al-ved .luna-al-ahead b { color:#d98a6a; }
.luna-al-video { display:block; width:100%; height:150px; background:#000; border-radius:6px; object-fit:contain; }
.luna-al-strip { position:relative; height:46px; border-radius:6px; background-color:#101116;
                 background-size:100% 100%; background-repeat:no-repeat; overflow:hidden; cursor:crosshair; }
.luna-al-sect { font-size:10.5px; color:var(--luna-accent); font-weight:600; margin-top:2px; }

/* The shot timeline (v3): the video being generated, one lane per kind. */
.luna-al-tl { border:1px solid var(--luna-border); border-radius:8px; background:var(--luna-bg); padding:7px;
              display:flex; flex-direction:column; gap:4px; }
.luna-al-tlh { display:flex; align-items:center; gap:7px; font-size:10.5px; color:var(--luna-muted); }
.luna-al-tlh b { color:var(--luna-text); }
.luna-al-tlh .sp { flex:1 1 auto; }
.luna-al-lane { display:grid; grid-template-columns:76px 1fr; align-items:center; gap:6px; }
.luna-al-lane .ln { font-size:10px; color:var(--luna-muted); text-align:right; }
.luna-al-track { position:relative; height:24px; border-radius:5px; background:#101116; border:1px solid #1f2129; }
.luna-al-truler { position:relative; height:13px; font-size:9.5px; color:var(--luna-muted); }
.luna-al-truler span { position:absolute; transform:translateX(-50%); white-space:nowrap; }
.luna-al-blk { position:absolute; top:2px; bottom:2px; border-radius:4px; cursor:grab; font-size:9.5px; font-weight:600;
               color:var(--luna-bg); display:flex; align-items:center; padding:0 5px; white-space:nowrap; overflow:hidden;
               box-sizing:border-box; min-width:6px; }
.luna-al-blk.vid { background:#d98a6a; } .luna-al-blk.snd { background:#e07bb4; }
.luna-al-blk.key { width:20px; margin-left:-10px; justify-content:center; padding:0; background:var(--luna-accent); }
.luna-al-blk.sel { box-shadow:0 0 0 2px #fff; }
.luna-al-refs { display:flex; gap:4px; flex-wrap:wrap; align-items:center; min-height:22px; }
.luna-al-chip { font-size:9.5px; font-weight:700; padding:2px 6px; border-radius:5px; cursor:pointer; color:var(--luna-bg); }
.luna-al-chip.p { background:var(--luna-accent); } .luna-al-chip.v { background:#d98a6a; } .luna-al-chip.a { background:#e07bb4; }
.luna-al-tlnote { font-size:10px; color:var(--luna-muted); line-height:1.4; }
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

// One cache-busting token per file per page load: a fresh one on EVERY call made
// each re-render download every thumbnail again (seen 2026-10-16 once the editors
// re-render on each change). Uploads never overwrite (overwrite=false gives a new
// name), so a stable URL cannot show a stale picture.
const _viewTok = new Map();
const viewURL = (name) => {
    if (!_viewTok.has(name)) _viewTok.set(name, Math.random().toString(36).slice(2));
    return `/view?filename=${encodeURIComponent(name)}&type=input&subfolder=&rand=${_viewTok.get(name)}`;
};
// Stable URL for sound files: the waveform decode and the player share the
// browser's cache instead of downloading a song twice.
const soundURL = (name) => `/view?filename=${encodeURIComponent(name)}&type=input&subfolder=`;

/* ------------------------------------------------------------- sound cards */

const MEDIA_WIDGET = "media_state";
const WIRED_INPUTS = ["seconds", "shot", "width", "height"];   // sockets whose value the editors show
const MAX_VIDEOS = 3;
const VIDEO_EXT = /\.(mp4|mov|mkv|webm|avi|m4v|mpg|mpeg|wmv|flv)$/i;
const isVideoFile = (f) => (f.type || "").startsWith("video/") || VIDEO_EXT.test(f.name || "");
const MEMORY_CAP_GB = 6;          // asset_loader.py MEMORY_CAP; the run refuses above it
const NEW_VIDEO = { start: 0, frames: 124, fps: "target", count: "target", size: "canvas", fit: "crop",
                    nth: 1, sound: "keep", precision: "fp16" };

// Clip facts (size, fps, length, sound) come from the server: the browser's
// <video> element does not expose a frame rate.
const _mediaInfo = new Map();
const _hasSound = new Map();   // file -> does it have a sound track (filled as info arrives)
function mediaInfo(file) {
    if (!_mediaInfo.has(file)) {
        const p = fetch(`/lunasave/media-info?file=${encodeURIComponent(file)}`)
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status))));
        p.then((mi) => _hasSound.set(file, !!mi.audio)).catch(() => _mediaInfo.delete(file));
        _mediaInfo.set(file, p);
    }
    return _mediaInfo.get(file);
}
const stripURL = (file, n) => `/lunasave/filmstrip?file=${encodeURIComponent(file)}&n=${n}`;

// Roles: a reference is shown to H3 and named in the prompt; "on the shot" is
// anchored at a frame. Defaults: pictures and clips are references, sound 1 is
// the song locked to the shot, later sounds are references.
const picRole = (m, i) => (m.pictures[i]?.role === "key" ? "key" : "ref");
const clipRole = (c) => (c.role === "guide" ? "guide" : "ref");
// Mirror of asset_timeline.normalize_sound_role: only sound 1 (the song) can be
// locked — a later sound asked to lock is a guide.
const soundRole = (c, j) => (c.role === "lock" ? (j === 0 ? "lock" : "guide")
    : ["guide", "ref"].includes(c.role) ? c.role : j === 0 ? "lock" : "ref");

// Mirror of asset_timeline.h3_tags: H3 numbers ONLY the references, in order, so
// a keyframe on card 1 makes card 2 <Picture 1>. Sound order: each reference
// clip's kept soundtrack, then the standalone reference sounds.
function h3Tags(node) {
    const m = readMedia(node), n = readPaths(node).length;
    const out = { pictures: {}, videos: {}, videoAudio: {}, sounds: {} };
    let p = 0, v = 0, a = 0;
    for (let i = 0; i < n; i++) if (picRole(m, i) === "ref") out.pictures[i] = `<Picture ${++p}>`;
    m.video.forEach((c, k) => {
        if (clipRole(c) !== "ref") return;
        // A kept soundtrack counts only when the file has sound (known once its info is in).
        if (c.sound !== "drop" && _hasSound.get(c.file) !== false) out.videoAudio[k] = `<Audio ${++a}>`;
        out.videos[k] = `<Video ${++v}>`;
    });
    m.audio.forEach((c, j) => { if (soundRole(c, j) === "ref") out.sounds[j] = `<Audio ${++a}>`; });
    return out;
}

// How many frames the continuation takes: the song's overlap when the song is
// cut by shot number (sound and picture then overlap by the same amount), else
// its own count. Shot 1 has nothing before it.
function contFrames(m, wiredShotNo = null) {
    const c = m.continuation || {}, song = m.audio[0];
    const byShot = song?.position === "shot";
    const shotNo = wiredShotNo > 0 ? wiredShotNo : (Number(song?.shot) || 1);   // a wired shot wins, as in Python
    if (byShot && shotNo === 1) return { frames: 0, shot1: true, fromSong: true };
    if (c.take === "last") return { frames: 1, shot1: false, fromSong: false };
    return { frames: byShot ? Number(song.overlap ?? 22) : Number(c.frames) || 22, shot1: false, fromSong: byShot };
}

// H3 clip lengths are 17k+5 frames; step to the previous / next one.
function stepH3Frames(n, dir) {
    let f = Math.max(5, Math.round(n));
    if (dir > 0) { f += 1; while (f % 17 !== 5) f += 1; }
    else { f -= 1; while (f > 5 && f % 17 !== 5) f -= 1; f = Math.max(5, f); }
    return f;
}
// Capped at 362 like media_io.snap_frames_nearest: the top of the trained range.
const nearestH3Frames = (n) => Math.min(362, Math.round(snapH3Seconds(n / H3_FPS) * H3_FPS));

// The numbers on the nodes feeding `seconds` and `shot`, as one string. Checked on
// every draw, so editing the Float/Int upstream moves the window straight away.
function wiredSignature(node) {
    const g = node.graph;
    return WIRED_INPUTS.map((name) => {
        const inp = node.inputs?.find((x) => x.name === name);
        if (!inp || inp.link == null) return "-";
        const l = g?.getLink?.(inp.link) ?? g?.links?.get?.(inp.link) ?? g?.links?.[inp.link];
        const src = l && g.getNodeById(l.origin_id);
        const w = src?.widgets?.find((x) => x.name === src.outputs?.[l.origin_slot]?.name) || src?.widgets?.find((x) => x.name === "value");
        return String(w?.value ?? "?");
    }).join("|");
}
const MAX_SOUNDS = 3;
const H3_FPS = 24;
const AUDIO_EXT = /\.(wav|mp3|flac|ogg|opus|m4a|aac|wma|aiff?)$/i;
const isAudioFile = (f) => (f.type || "").startsWith("audio/") || AUDIO_EXT.test(f.name || "");

function readMedia(node) {
    try {
        const m = JSON.parse(String(widget(node, MEDIA_WIDGET)?.value || "") || "{}");
        return {
            audio: Array.isArray(m.audio) ? m.audio.filter((c) => c && c.file) : [],
            video: Array.isArray(m.video) ? m.video.filter((c) => c && c.file) : [],
            pictures: Array.isArray(m.pictures) ? m.pictures.map((p) => p || {}) : [],
            shot: m.shot && Number(m.shot.frames) > 0 ? { frames: Number(m.shot.frames) } : null,
            continuation: m.continuation && typeof m.continuation === "object" ? m.continuation : null,
        };
    } catch { return { audio: [], video: [], pictures: [], shot: null, continuation: null }; }
}
const NEW_CONT = { on: true, from: "folder", folder: "", file: "", take: "frames", frames: 22 };

function writeMedia(node, m) {
    const w = widget(node, MEDIA_WIDGET);
    if (!w) return;
    const out = {};
    if (m.audio?.length) out.audio = m.audio;
    if (m.video?.length) out.video = m.video;
    // Picture roles only matter once one of them is not a plain reference.
    if (m.pictures?.some((p) => p?.role === "key")) out.pictures = m.pictures;
    if (m.shot?.frames) out.shot = m.shot;
    if (m.continuation) out.continuation = m.continuation;   // kept while off, so settings survive a toggle
    w.value = Object.keys(out).length ? JSON.stringify(out) : "";
    w.callback?.(w.value);
    node.graph?.setDirtyCanvas(true, true);
}

// MiniMax H3 shot lengths: 5, 22, 39 … frames (17k+5) at 24 fps, nearest first.
function snapH3Seconds(sec) {
    const n = Math.max(5, Math.round(sec * H3_FPS));
    const up = n + ((5 - (n % 17)) % 17 + 17) % 17, down = up - 17;
    return (down >= 5 && n - down < up - n ? down : up) / H3_FPS;
}

const clock = (t) => {
    t = Math.max(0, t || 0);
    const m = Math.floor(t / 60), s = t - m * 60;
    return `${m}:${s.toFixed(2).padStart(5, "0")}`;
};
const parseClock = (txt) => {
    const s = String(txt).trim().replace(",", ".");
    const m = s.match(/^(\d+):(\d+(?:\.\d+)?)$/);
    const v = m ? Number(m[1]) * 60 + Number(m[2]) : Number(s.replace(/\s*s$/, ""));
    return Number.isFinite(v) ? v : null;
};

// Waveform peaks, 100 per second, decoded once per file in the browser — the
// file is already in the input folder, so nothing is decoded on the server just
// to draw a picture of it (the same split Pixaroma's Load Audio makes).
const PEAKS_PER_S = 100;
const _peaks = new Map();     // file -> Promise<{peaks, duration, sampleRate, channels}>
function loadPeaks(file) {
    if (_peaks.has(file)) return _peaks.get(file);
    const p = (async () => {
        const buf = await (await fetch(soundURL(file))).arrayBuffer();
        const ctx = new OfflineAudioContext(1, 1, 44100);
        const ab = await ctx.decodeAudioData(buf);
        const n = Math.max(1, Math.ceil(ab.duration * PEAKS_PER_S));
        const per = ab.length / n, peaks = new Float32Array(n);
        for (let c = 0; c < ab.numberOfChannels; c++) {
            const d = ab.getChannelData(c);
            for (let i = 0; i < n; i++) {
                let mx = peaks[i];
                const a = Math.floor(i * per), b = Math.min(d.length, Math.floor((i + 1) * per));
                for (let j = a; j < b; j++) { const v = d[j] < 0 ? -d[j] : d[j]; if (v > mx) mx = v; }
                peaks[i] = mx;
            }
        }
        return { peaks, duration: ab.duration, sampleRate: ab.sampleRate, channels: ab.numberOfChannels };
    })();
    p.catch(() => _peaks.delete(file));
    _peaks.set(file, p);
    return p;
}

// Draw [t0, t1] of a song; samples inside [a, b] in the selection colour.
function drawWave(cv, info, t0, t1, a, b, opts = {}) {
    if (!cv?.isConnected || !info) return;
    const r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    if (!r.width || !r.height) return;
    cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
    const g = cv.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const W = r.width, H = r.height, mid = H / 2, span = Math.max(1e-6, t1 - t0);
    if (opts.grid) {
        g.strokeStyle = "#2a2c35";
        for (let s = Math.ceil(t0 * 2) / 2; s < t1; s += 0.5) {
            const x = (s - t0) / span * W;
            g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke();
        }
    }
    const { peaks } = info, step = opts.step || 2;
    for (let x = 0; x < W; x += step) {
        const ta = t0 + x / W * span, tb = t0 + (x + step) / W * span;
        let mx = 0;
        for (let i = Math.max(0, Math.floor(ta * PEAKS_PER_S)); i <= Math.min(peaks.length - 1, Math.floor(tb * PEAKS_PER_S)); i++)
            if (peaks[i] > mx) mx = peaks[i];
        const tm = (ta + tb) / 2, h = Math.max(1, mx * (H / 2 - 2));
        g.fillStyle = tm >= a && tm <= b ? (opts.color || "#e07bb4") : "#5d616e";
        g.fillRect(x, mid - h, Math.max(1, step - 0.6), h * 2);
    }
}

// The last run's song report, per node. Module memory rather than node.properties:
// properties are compared by the change tracker, and writing them on every run
// would mark the workflow modified (the lesson LLM Prompt's face learned).
const _lastSong = new Map();

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

// The seven fixed outputs (images, width, height, asset_brief, audio, refs,
// timeline) occupy slots 0-6 and are never touched. Only the trailing image_N
// slots grow and shrink.
//
// `slot.hidden` does NOT work: setting it leaves the flag on the object but the
// frontend (1.48.x) still draws every output. Verified in the browser, which is
// why this adds and removes real slots instead.
const FIXED = 7;
const NEW_OUTS = [["audio", "AUDIO"], ["refs", "LUNA_H3_REFS"], ["timeline", "LUNA_TIMELINE"]];

// Workflows saved before audio/refs/timeline existed have image_1 at slot 4.
// Frontend 1.55.17 overwrites a saved node's output names BY POSITION from the
// current definition and keeps every link on its slot number, so left alone an
// old image_1 wire lands on `audio` without a word (seen in the S0 spike,
// 2026-10-16). onConfigure is too late for that; this rewrites the raw workflow
// JSON before the graph is configured: the three new slots go in at 4 and every
// link leaving slot 4 or higher of an old Asset Loader moves up by three. Root
// graph and subgraph definitions alike. A migrated save has "audio" at slot 4, so
// it is never moved twice.
function migrateWorkflowJSON(data) {
    const moved = [];
    const fixGraph = (g, where) => {
        if (!Array.isArray(g?.nodes)) return;
        const old = new Set();
        for (const n of g.nodes) {
            if (n?.type !== NODE || !Array.isArray(n.outputs) || n.outputs[4]?.name !== "image_1") continue;
            old.add(n.id);
            n.outputs.splice(4, 0, ...NEW_OUTS.map(([name, type]) => ({ name, localized_name: name, type, links: null })));
        }
        if (!old.size) return;
        // Floating links (a wire dragged to a reroute with nothing after it) carry an
        // origin too; they move with the rest.
        for (const l of [...(g.links || []), ...(g.floatingLinks || [])]) {
            // [id, origin_id, origin_slot, target_id, target_slot, type] in the root
            // graph; {id, origin_id, origin_slot, ...} inside subgraph definitions.
            const arr = Array.isArray(l);
            const oid = arr ? l[1] : l?.origin_id, os = arr ? l[2] : l?.origin_slot;
            if (!old.has(oid) || !(os >= 4)) continue;
            if (arr) l[2] = os + NEW_OUTS.length; else l.origin_slot = os + NEW_OUTS.length;
            moved.push(`${where} link ${arr ? l[0] : l.id}: slot ${os} -> ${os + NEW_OUTS.length}`);
        }
    };
    fixGraph(data, "root");
    for (const sg of data?.definitions?.subgraphs || []) fixGraph(sg, `subgraph ${sg.id}`);
    // clipboard / blueprint data keeps its subgraphs at the top level
    for (const sg of Array.isArray(data?.subgraphs) ? data.subgraphs : []) fixGraph(sg, `subgraph ${sg.id}`);
    return moved;
}

// Paste and subgraph-blueprint insertion go through LGraphCanvas._deserializeItems,
// never loadGraphData, so beforeConfigureGraph never sees them (review,
// 2026-10-16). Tested: an old pasted node lost its image_1/image_3 wires (AUDIO and
// LUNA_TIMELINE slots refuse an IMAGE link) and image_4+ would land on image_1+.
// The same JSON migration runs on that data before it becomes nodes.
function patchDeserialize() {
    const proto = app.canvas && Object.getPrototypeOf(app.canvas);
    if (!proto || typeof proto._deserializeItems !== "function" || proto._lunaAssetMigrates) return;
    const orig = proto._deserializeItems;
    proto._deserializeItems = function (items, options) {
        try {
            const moved = migrateWorkflowJSON(items);
            if (moved.length) console.info("[Luna Asset Loader] updated pasted pre-v3 Asset Loader wires:", moved);
        } catch (e) { console.warn("[Luna Asset Loader] paste migration skipped:", e); }
        return orig.call(this, items, options);
    };
    proto._lunaAssetMigrates = true;
}

// Paste and subgraph-blueprint insertion never call loadGraphData, so the JSON
// migration above never sees them (review, 2026-10-16). Such a node is configured
// from its old serialized form — outputs[4] still "image_1" in `info` — and its
// links are made right after. So: once they exist, move every link leaving slot 4
// or higher up by three, on the live graph. A node from a migrated save has
// "audio" at slot 4 in `info` and is left alone.
function migrateLiveNode(node) {
    const g = node.graph;
    if (!g || !node.outputs) return 0;
    const getLink = (id) => g.getLink?.(id) ?? g.links?.get?.(id) ?? g.links?.[id];
    const moves = [];
    node.outputs.forEach((o, i) => {
        if (i < 4) return;
        for (const id of o.links || []) { const l = getLink(id); if (l && l.origin_id === node.id) moves.push([i, id, l]); }
    });
    if (!moves.length) return 0;
    const need = Math.max(...moves.map(([i]) => i)) + NEW_OUTS.length;
    const cw = widget(node, COUNT_WIDGET);
    if (cw && node.outputs.length <= need) {
        cw.value = Math.min(MAX, Math.max(Number(cw.value) || 1, need - FIXED + 1));
        applyCount(node);
    }
    for (const [i] of moves) node.outputs[i].links = [];
    for (const [i, id, l] of moves) {
        const to = i + NEW_OUTS.length;
        l.origin_slot = to;
        const out = node.outputs[to];
        if (out) (out.links = out.links || []).push(id);
    }
    node.setDirtyCanvas(true, true);
    return moves.length;
}

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
        label = [x, 0, w, CTL.boxH];   // y is set below, with the rest of the row
        x += w + CTL.labelGap;
    }
    // Input sockets (`seconds`, v3) occupy the left column's top rows; the stepper
    // sits below them. Counted from the inputs, never measured.
    const sockets = (node.inputs || []).filter((i) => !i.widget).length;
    const y = CTL.top + (sockets ? sockets * (window.LiteGraph?.NODE_SLOT_HEIGHT || 20) + 4 : 0);
    const r = (rx, rw) => [rx, y, rw, CTL.boxH];
    if (label) label[1] = y;
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
    // The song editor takes the preview's place while a sound card is selected.
    const aed = document.createElement("div");
    aed.className = "luna-al-aed";
    aed.style.display = "none";
    // Drags and typing in here belong to the editor, never to the canvas.
    for (const ev of ["pointerdown", "keydown", "wheel"]) aed.addEventListener(ev, (e) => e.stopPropagation());
    // The clip editor, same idea, while a video card is selected.
    const ved = document.createElement("div");
    ved.className = "luna-al-ved";
    ved.style.display = "none";
    for (const ev of ["pointerdown", "keydown", "wheel"]) ved.addEventListener(ev, (e) => e.stopPropagation());
    // The shot timeline: what is anchored where in the video being generated.
    const tl = document.createElement("div");
    tl.className = "luna-al-tl";
    tl.style.display = "none";
    for (const ev of ["pointerdown", "keydown", "wheel"]) tl.addEventListener(ev, (e) => e.stopPropagation());
    // The continuation editor.
    const ced = document.createElement("div");
    ced.className = "luna-al-ved";
    ced.style.display = "none";
    for (const ev of ["pointerdown", "keydown", "wheel"]) ced.addEventListener(ev, (e) => e.stopPropagation());
    root.append(bar, cards, tl, preview, panel, aed, ved, ced);

    let selected = 0;                 // which card the resize panel edits
    let selAudio = -1;                // which sound card the song editor edits; -1 = none
    let selVideo = -1;                // which video card the clip editor edits; -1 = none
    let selCont = false;              // the continuation editor is open
    // One editor at a time: picking a card of one kind clears the others.
    const pick = (kind, i) => {
        selAudio = kind === "a" ? i : -1;
        selVideo = kind === "v" ? i : -1;
        selCont = kind === "c";
        if (kind === "p") selected = i;
        render();
    };
    const natural = new Map();        // filename -> [w, h], filled as thumbs decode

    const picker = document.createElement("input");
    picker.type = "file";
    picker.accept = "image/*,audio/*,.mp3,.wav,.flac,.ogg,.opus,.m4a,.aac";
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
    mkBtn("Clear", "danger", () => {
        writePaths(node, []); syncCount(node, 0);
        writeMedia(node, { audio: [], video: [], pictures: [], shot: readMedia(node).shot }); selAudio = -1; selVideo = -1;
        render();
    });

    // image_paths and asset_state are hidden once the cards own them — two
    // multiline boxes were taking most of the node. They stay reachable, because
    // image_paths remains the source of truth and typing into it must still work
    // if the frontend ever misbehaves.
    // image_count joins them: the title-bar stepper owns it now, and leaving a
    // second copy in the body would be the control that slides around. Fields
    // brings all three back, so there is still a way in if the stepper misbehaves.
    let fieldsShown = false;
    const setFieldsVisible = (show) => {
        for (const name of [PATHS_WIDGET, COUNT_WIDGET, "asset_state", MEDIA_WIDGET]) {
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
    // The continuation: the end of the previous shot opens this one.
    const contBtn = mkBtn("↺ Continue", "", () => {
        const m = readMedia(node);
        const on = !(m.continuation?.on);
        m.continuation = { ...NEW_CONT, ...(m.continuation || {}), on };
        writeMedia(node, m);
        if (on) { selCont = true; selAudio = -1; selVideo = -1; } else selCont = false;
        render();
    });
    contBtn.title = "Open this shot with the end of the previous one, so the motion carries on across the cut";
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
        // One button for everything: sound files become sound cards, clips video
        // cards, the rest pictures.
        const sounds = files.filter(isAudioFile), clips = files.filter((f) => !isAudioFile(f) && isVideoFile(f));
        const pictures = files.filter((f) => !isAudioFile(f) && !isVideoFile(f));
        if (sounds.length) {
            const m = readMedia(node);
            const room = MAX_SOUNDS - m.audio.length;
            const names = await uploadFiles(sounds.slice(0, Math.max(0, room)));
            for (const file of names) m.audio.push({ file, start: 0, duration: 0, fill: "silence" });
            if (names.length) { writeMedia(node, m); selAudio = m.audio.length - 1; selVideo = -1; }
            if (sounds.length > room) notice(`Room for ${MAX_SOUNDS} sounds; ${sounds.length - Math.max(0, room)} not added.`);
        }
        if (clips.length) {
            const m = readMedia(node);
            const room = MAX_VIDEOS - m.video.length;
            const names = await uploadFiles(clips.slice(0, Math.max(0, room)));
            for (const file of names) m.video.push({ file, ...NEW_VIDEO });
            if (names.length) { writeMedia(node, m); selVideo = m.video.length - 1; selAudio = -1; }
            if (clips.length > room) notice(`Room for ${MAX_VIDEOS} clips; ${clips.length - Math.max(0, room)} not added.`);
        }
        if (pictures.length) {
            const names = await uploadFiles(pictures);
            if (names.length) {
                const next = readPaths(node).concat(names).slice(0, MAX);
                writePaths(node, next);
                // The card list drives the socket count, both ways. The arrows still
                // override it by hand; the override holds until the list changes again.
                syncCount(node, next.length);
                if (!sounds.length && !clips.length) { selAudio = -1; selVideo = -1; }
            }
        }
        render();
    };

    let dragFrom = -1;

    function render() {
        const paths = readPaths(node);
        const media = readMedia(node);
        if (selAudio >= media.audio.length) selAudio = media.audio.length - 1;
        if (selVideo >= media.video.length) selVideo = media.video.length - 1;
        cards.replaceChildren();
        counter.textContent = `${paths.length} / ${MAX}`
            + (media.video.length ? ` · ${media.video.length} clip${media.video.length > 1 ? "s" : ""}` : "")
            + (media.audio.length ? ` · ${media.audio.length} sound` : "");

        // No early return on the empty list. It used to return here, which skipped
        // renderPreview/renderPanel — both handle "nothing loaded" correctly, they
        // just never ran, so the last selected image stayed on screen after Clear.
        if (!paths.length && !media.audio.length && !media.video.length) {
            const e = document.createElement("div");
            e.className = "luna-al-empty";
            e.textContent = "Nothing loaded. Press Upload for pictures or a song, or type file names in image_paths below.";
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
            card.className = "luna-al-card" + (i === selected && selAudio < 0 && selVideo < 0 && !selCont ? " sel" : "");
            card.draggable = true;
            // Selecting is what makes a nine-image node editable: the resize panel
            // below edits whichever card is selected, so REF2VA references can stay
            // untouched while slots 1 and 2 get conformed.
            card.onclick = () => pick("p", i);

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
                // A picture's role travels with it.
                const m = readMedia(node);
                if (m.pictures.length > i) { m.pictures.splice(i, 1); writeMedia(node, m); }
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
                // Keep each picture's role with the picture, not with the slot.
                const m = readMedia(node);
                if (m.pictures.some((p) => p?.role === "key")) {
                    while (m.pictures.length < Math.max(next.length, dragFrom + 1)) m.pictures.push({});
                    const [mr] = m.pictures.splice(dragFrom, 1);
                    m.pictures.splice(i, 0, mr);
                    writeMedia(node, m);
                }
                writePaths(node, next);   // reorder IS the renumbering
                render();
            });

            card.append(img, pic, x, cap);
            cards.appendChild(card);
        });

        // The continuation card comes first: it opens the shot.
        if (media.continuation?.on) {
            const card = document.createElement("div");
            card.className = "luna-al-card" + (selCont ? " sel" : "");
            card.style.cursor = "pointer";
            card.title = "Continuation — the end of the previous shot opens this one";
            card.onclick = () => pick("c", 0);
            const face = document.createElement("div");
            face.className = "luna-al-vthumb";
            face.style.cssText = "display:flex;align-items:center;justify-content:center;font-size:30px;color:#fff9;background:repeating-linear-gradient(45deg,#3a2a40 0 8px,#2c2131 8px 16px)";
            face.textContent = "↺";
            const pic = document.createElement("div");
            pic.className = "luna-al-pic vid";
            pic.textContent = "↺";
            const cap = document.createElement("div");
            cap.className = "luna-al-cap";
            const c = media.continuation;
            const n = contFrames(media, wiredShot().value);
            cap.innerHTML = `<div class="luna-al-dim">${n.shot1 ? "shot 1: none" : c.take === "last" ? "last frame" : `last ${n.frames} frames`}</div><div class="luna-al-name"></div>`;
            cap.querySelector(".luna-al-name").textContent = c.from === "input" ? "previous_frames input" : c.from === "file" ? (c.file || "pick a file") : `newest in output/${c.folder || ""}`;
            card.append(face, pic, cap);
            cards.appendChild(card);
        }

        // Video cards after the pictures: V1-V3, MiniMax H3's <Video k> in this order.
        media.video.forEach((c, i) => {
            const card = document.createElement("div");
            card.className = "luna-al-card" + (i === selVideo ? " sel" : "");
            card.style.cursor = "pointer";
            card.title = `<Video ${i + 1}>\n${c.file}`;
            card.onclick = () => pick("v", i);
            const img = document.createElement("img");
            img.className = "luna-al-vthumb";
            img.src = stripURL(c.file, 1);
            const pic = document.createElement("div");
            pic.className = "luna-al-pic vid";
            pic.textContent = `V${i + 1}`;
            const cap = document.createElement("div");
            cap.className = "luna-al-cap";
            const dim = document.createElement("div");
            dim.className = "luna-al-dim";
            dim.textContent = "reading…";
            const nm = document.createElement("div");
            nm.className = "luna-al-name";
            nm.textContent = c.file;
            cap.append(dim, nm);
            const x = document.createElement("div");
            x.className = "luna-al-x";
            x.textContent = "✕";
            x.title = "Remove";
            x.onclick = (ev) => {
                ev.stopPropagation();
                const m = readMedia(node);
                m.video.splice(i, 1);
                writeMedia(node, m);
                if (selVideo >= m.video.length) selVideo = m.video.length - 1;
                render();
            };
            card.append(img, pic, x, cap);
            cards.appendChild(card);
            mediaInfo(c.file).then((mi) => {
                dim.textContent = `${(mi.duration || 0).toFixed(1)} s · ${+(mi.fps || 0).toFixed(2)} fps${mi.audio ? "" : " · no sound"}`;
                // A silent clip shifts the <Audio n> numbers: redraw the tags now that it is known.
                if (!mi.audio && c.sound !== "drop") renderTimeline();
            }).catch(() => { dim.textContent = "cannot be read"; });
        });

        // Sound cards after the pictures. Not draggable: they are numbered on their
        // own (A1 is the song), and pictures never trade places with them.
        media.audio.forEach((c, i) => {
            const card = document.createElement("div");
            card.className = "luna-al-card snd" + (i === selAudio ? " sel" : "");
            card.title = `Sound ${i + 1}${i === 0 ? " — the song on the audio output" : ""}\n${c.file}`;
            card.onclick = () => pick("a", i);
            const cv = document.createElement("canvas");
            cv.className = "luna-al-snd";
            const pic = document.createElement("div");
            pic.className = "luna-al-pic snd";
            pic.textContent = `A${i + 1}`;
            const cap = document.createElement("div");
            cap.className = "luna-al-cap";
            const dim = document.createElement("div");
            dim.className = "luna-al-dim";
            dim.textContent = "reading…";
            const nm = document.createElement("div");
            nm.className = "luna-al-name";
            nm.textContent = c.file;
            cap.append(dim, nm);
            const x = document.createElement("div");
            x.className = "luna-al-x";
            x.textContent = "✕";
            x.title = "Remove";
            x.onclick = (ev) => {
                ev.stopPropagation();
                const m = readMedia(node);
                m.audio.splice(i, 1);
                writeMedia(node, m);
                if (selAudio >= m.audio.length) selAudio = m.audio.length - 1;
                if (!m.audio.length) selAudio = -1;
                render();
            };
            card.append(cv, pic, x, cap);
            cards.appendChild(card);
            loadPeaks(c.file).then((info) => {
                dim.textContent = `${clock(info.duration).replace(/\.\d+$/, "")} · ${(info.sampleRate / 1000).toFixed(1)} kHz`;
                const dur = c.duration > 0 ? c.duration : info.duration - c.start;
                setTimeout(() => drawWave(cv, info, 0, info.duration, c.start, c.start + dur, { step: 2 }), 0);
            }).catch(() => { dim.textContent = "cannot be read"; });
        });

        syncAccent(node, root);
        renderTimeline();
        renderPreview();
        renderPanel();
        renderAudio();
        renderVideo();
        renderContinuation();

        // The widget's getHeight depends on how many cards there are, so a redraw
        // has to follow any change to the list or the node keeps its old height.
        node.setDirtyCanvas(true, true);
    }

    function renderPreview() {
        const paths = readPaths(node);
        if (selAudio >= 0 || selVideo >= 0 || selCont) { preview.style.display = "none"; return; }
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
            ? `${picLabel(selected)}  ${nat[0]}×${nat[1]} ${describeAR(nat[0], nat[1]).short}`
            : picLabel(selected);
    }

    /* ------------------------------------------------------------- resize panel */

    function renderPanel() {
        panel.replaceChildren();
        panel.style.display = selAudio >= 0 || selVideo >= 0 || selCont ? "none" : "";
        if (selAudio >= 0 || selVideo >= 0 || selCont) return;
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
            ? `<b>${picLabel(selected).replace(/</g, "&lt;").replace(/>/g, "&gt;")}</b> &nbsp; ${nat[0]}×${nat[1]} → <b>${out[0]}×${out[1]}</b>`
            : `<b>${picLabel(selected).replace(/</g, "&lt;").replace(/>/g, "&gt;")}</b>`;
        head.appendChild(who);

        // Reference for H3, or a keyframe anchored on the shot.
        const mm = readMedia(node);
        roleRow(panel, "p", selected, [["ref", "Reference"], ["key", "Keyframe on the shot"]],
                picRole(mm, selected), Number(mm.pictures[selected]?.at) || 0, 1);

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

    // What H3 calls picture card i: its real tag when it is a reference, or that it is a keyframe.
    const picLabel = (i) => h3Tags(node).pictures[i] || `Card ${i + 1} · keyframe`;

    /* ------------------------------------------------------- shot timeline */

    // The shot length in frames: the wired seconds when there are any, else the
    // length kept on the node (124 frames = MiniMax H3's 5.17 s default).
    function shotLen() {
        const ws = wiredSeconds();
        if (ws.wired && ws.value > 0) return { frames: Math.round(ws.value * H3_FPS), from: ws.from };
        return { frames: readMedia(node).shot?.frames || 124, from: "" };
    }

    // Patch one card's role/placement. kind: "p" (picture index), "v", "a".
    function setPlacement(kind, i, patch) {
        const m = readMedia(node);
        if (kind === "p") {
            while (m.pictures.length <= i) m.pictures.push({});
            m.pictures[i] = { ...m.pictures[i], ...patch };
        } else {
            const list = kind === "v" ? m.video : m.audio;
            if (!list[i]) return;
            list[i] = { ...list[i], ...patch };
        }
        writeMedia(node, m);
        render();
    }

    // A clip's length on the shot, in output frames — what the guide will hold.
    const clipLen = (c) => {
        const f = Math.max(1, Number(c.frames) || 124);
        const n = (c.count || "target") === "target" ? nearestH3Frames(f) : f;
        return Math.ceil(n / Math.max(1, Number(c.nth) || 1));
    };

    // The role row every editor shows: which role, and the frame when it has one.
    function roleRow(host, kind, i, roles, cur, at, len) {
        const S = shotLen().frames;
        const row = document.createElement("div");
        row.className = "luna-al-row";
        row.innerHTML = `<div class="luna-al-lbl">Role</div><div class="luna-al-seg"></div>`;
        const segEl = row.querySelector(".luna-al-seg");
        for (const [val, text] of roles) {
            const o = document.createElement("div");
            o.className = "luna-al-opt" + (val === cur ? " on" : "");
            o.textContent = text;
            o.onclick = () => setPlacement(kind, i, { role: val, at: Math.min(at || 0, Math.max(0, S - len)) });
            segEl.appendChild(o);
        }
        host.appendChild(row);
        if (cur === "ref") return;
        const r2 = document.createElement("div");
        r2.className = "luna-al-row";
        r2.innerHTML = `<div class="luna-al-lbl">At frame</div><div class="luna-al-nf"><span class="luna-al-nud" data-a="first" title="The first frame">First</span><input class="at" style="width:52px"><span class="luna-al-nud" data-a="last" title="As late as it fits">Last</span><span class="luna-al-lock"></span></div>`;
        const inp = r2.querySelector(".at");
        inp.value = String(at || 0);
        r2.querySelector(".luna-al-lock").textContent = `of ${S} · ${((at || 0) / H3_FPS).toFixed(2)} s`;
        const set = (v) => setPlacement(kind, i, { at: Math.max(0, Math.min(Math.round(v), Math.max(0, S - len))) });
        inp.onchange = () => { const v = Number(inp.value); if (Number.isFinite(v)) set(v); };
        inp.addEventListener("keydown", (e) => { if (e.key === "Enter") inp.blur(); e.stopPropagation(); });
        r2.querySelector('[data-a="first"]').onclick = () => set(0);
        r2.querySelector('[data-a="last"]').onclick = () => set(S - len);
        host.appendChild(r2);
    }

    function renderTimeline() {
        const m = readMedia(node), paths = readPaths(node);
        if (!paths.length && !m.video.length && !m.audio.length) { tl.style.display = "none"; tl.replaceChildren(); return; }
        tl.style.display = "";
        const { frames: S, from } = shotLen();
        const tags = h3Tags(node);
        tl.innerHTML = `
            <div class="luna-al-tlh"><span>Shot</span><b>${S} frames · ${(S / H3_FPS).toFixed(2)} s</b>
              <span>${from ? `from ${from.replace(/[<>&]/g, "")}` : "set here"}</span><span class="sp"></span>
              ${from ? "" : `<span class="luna-al-nud" data-s="-1" title="17 frames shorter">−</span><span class="luna-al-nud" data-s="1" title="17 frames longer">+</span>`}</div>
            <div class="luna-al-lane"><span></span><div class="luna-al-truler"></div></div>
            <div class="luna-al-lane"><span class="ln">Pictures</span><div class="luna-al-track" data-k="p"></div></div>
            <div class="luna-al-lane"><span class="ln">Clips</span><div class="luna-al-track" data-k="v"></div></div>
            <div class="luna-al-lane"><span class="ln">Sounds</span><div class="luna-al-track" data-k="a"></div></div>
            <div class="luna-al-lane"><span class="ln">References</span><div class="luna-al-refs"></div></div>
            <div class="luna-al-tlnote"></div>`;
        const q = (s) => tl.querySelector(s);
        const ruler = q(".luna-al-truler"), stepR = S > 200 ? 48 : 24;
        for (let f = 0; f <= S; f += stepR) {
            const sp = document.createElement("span");
            sp.style.left = `${f / S * 100}%`;
            sp.textContent = String(f);
            ruler.appendChild(sp);
        }
        tl.querySelectorAll("[data-s]").forEach((b) => {
            b.onclick = () => {
                const mm = readMedia(node);
                mm.shot = { frames: Math.max(5, Math.min(362, S + 17 * Number(b.dataset.s))) };
                writeMedia(node, mm); render();
            };
        });

        // One draggable item on a lane; dragging changes its frame, a click selects its card.
        const place = (track, cls, kind, i, at, len, label, title, isSel) => {
            const el = document.createElement("div");
            el.className = `luna-al-blk ${cls}` + (isSel ? " sel" : "");
            el.textContent = label;
            el.title = title;
            const pos = (a) => {
                if (cls === "key") el.style.left = `${(a + 0.5) / S * 100}%`;
                else { el.style.left = `${a / S * 100}%`; el.style.width = `${Math.max(0.8, Math.min(len, S - a) / S * 100)}%`; }
            };
            pos(at);
            let d = null;
            el.addEventListener("pointerdown", (e) => { d = { x: e.clientX, at, moved: false }; el.setPointerCapture(e.pointerId); e.preventDefault(); });
            el.addEventListener("pointermove", (e) => {
                if (!d) return;
                const df = (e.clientX - d.x) / track.getBoundingClientRect().width * S;
                const a = Math.max(0, Math.min(Math.round(d.at + df), Math.max(0, S - (cls === "key" ? 1 : len))));
                if (a !== d.cur) { d.cur = a; d.moved = true; pos(a); el.title = `${title} — frame ${a}`; }
            });
            const up = () => {
                if (!d) return;
                const moved = d.moved, a = d.cur;
                d = null;
                if (moved) setPlacement(kind, i, { at: a }); else pick(kind, i);
            };
            el.addEventListener("pointerup", up);
            el.addEventListener("pointercancel", up);
            track.appendChild(el);
        };

        const tp = q('[data-k="p"]'), tv = q('[data-k="v"]'), ta = q('[data-k="a"]'), refs = q(".luna-al-refs");
        // The continuation always opens the shot: drawn, not draggable.
        const cf = m.continuation?.on ? contFrames(m, wiredShot().value) : null;
        if (cf && !cf.shot1) {
            const el = document.createElement("div");
            el.className = "luna-al-blk vid" + (selCont ? " sel" : "");
            el.style.cssText = `left:0;width:${Math.max(0.8, cf.frames / S * 100)}%;background:repeating-linear-gradient(45deg,#b07a8a 0 6px,#9a6878 6px 12px);cursor:pointer`;
            el.textContent = `↺ 0–${cf.frames - 1}`;
            el.title = "The continuation: the end of the previous shot";
            el.onclick = () => pick("c", 0);
            tv.appendChild(el);
        }
        const chip = (cls, text, kind, i, title) => {
            const c = document.createElement("span");
            c.className = `luna-al-chip ${cls}`;
            c.textContent = text;
            c.title = title;
            c.onclick = () => pick(kind, i);
            refs.appendChild(c);
        };
        paths.forEach((name, i) => {
            if (picRole(m, i) === "key") {
                const at = Number(m.pictures[i]?.at) || 0;
                place(tp, "key", "p", i, at, 1, String(i + 1), `Picture card ${i + 1} — keyframe at frame ${at}`, selAudio < 0 && selVideo < 0 && selected === i);
            } else chip("p", `${tags.pictures[i]} = ${i + 1}`, "p", i, `${tags.pictures[i]} in the prompt is picture card ${i + 1} (${name})`);
        });
        m.video.forEach((c, k) => {
            if (clipRole(c) === "guide") {
                const len = clipLen(c), at = Number(c.at) || 0;
                place(tv, "vid", "v", k, at, len, `V${k + 1} · ${at}–${at + len - 1}`, `Clip V${k + 1} on the shot`, selVideo === k);
            } else chip("v", `${tags.videos[k]} = V${k + 1}` + (tags.videoAudio[k] ? ` + ${tags.videoAudio[k]}` : ""), "v", k,
                `${tags.videos[k]} in the prompt is clip card V${k + 1}` + (tags.videoAudio[k] ? `; its sound is ${tags.videoAudio[k]}` : ""));
        });
        m.audio.forEach((c, j) => {
            const role = soundRole(c, j);
            if (role === "ref") { chip("a", `${tags.sounds[j]} = A${j + 1}`, "a", j, `${tags.sounds[j]} in the prompt is sound card A${j + 1}`); return; }
            const at = Number(c.at) || 0;
            place(ta, "snd", "a", j, at, S - at, `A${j + 1} · ${role === "lock" ? "locked" : "guide"} from ${at}`,
                `Sound A${j + 1} ${role === "lock" ? "locked — the picture follows it" : "as a guide"}, from frame ${at}`, selAudio === j);
        });
        if (!refs.children.length) refs.innerHTML = `<span class="luna-al-tlnote">none — everything is on the shot</span>`;
        q(".luna-al-tlnote").textContent = "MiniMax H3: pictures anchor at any frame; a clip must be 17k+5 frames and end inside the shot; "
            + "a sound runs from its frame to the end. H3 numbers only the references, in this order.";
    }

    /* -------------------------------------------------------- song editor */

    // What the `seconds` input says, when it is wired. The frontend can read a
    // plain number widget on the node at the other end (a Float primitive, a
    // canvas node's seconds); anything computed is only known after a run, so the
    // last run's value stands in, and the editor says which it is showing.
    function wiredSeconds() { return wiredNumber("seconds", (last) => last?.wired && last.seconds > 0 ? last.seconds : null); }
    function wiredShot() { return wiredNumber("shot", (last) => last?.shot > 0 ? last.shot : null); }
    function wiredNumber(name, fromLast) {
        const inp = node.inputs?.find((x) => x.name === name);
        if (!inp || inp.link == null) return { wired: false, value: null, from: "" };
        let value = null, from = "the wire";
        try {
            const g = node.graph;
            const l = g.getLink?.(inp.link) ?? g.links?.get?.(inp.link) ?? g.links?.[inp.link];
            const src = l && g.getNodeById(l.origin_id);
            const out = src?.outputs?.[l.origin_slot];
            from = src?.title || from;
            const w = src?.widgets?.find((x) => x.name === out?.name) || src?.widgets?.find((x) => x.name === "value");
            if (w && Number.isFinite(Number(w.value)) && Number(w.value) > 0) value = Number(w.value);
        } catch { /* graph mid-change: fall back to the last run */ }
        if (value == null) {
            const v = fromLast(_lastSong.get(node.id));
            if (v != null) { value = v; from += ", last run"; }
        }
        return { wired: true, value, from };
    }

    // Shot mode: shot n's window starts at song_start + (n-1) x (shot length - overlap).
    const shotStep = (len, overlap) => len - overlap / H3_FPS;
    const shotCount = (T, songStart, len, overlap) => {
        const step = shotStep(len, overlap);
        return step > 0 && T > songStart ? Math.ceil((T - songStart) / step) : 0;
    };
    // Rows of the editor beyond the base, for the node's arithmetic height.
    const audioExtraRows = () => {
        const c = readMedia(node).audio[selAudio];
        const role = c ? soundRole(c, selAudio) : "ref";
        return 1 + (c?.position === "shot" ? 2 : 0) + 1 + (role !== "ref" ? 1 : 0);   // + Role, + At frame
    };

    let player = null, playRaf = 0;
    function stopPlay() {
        cancelAnimationFrame(playRaf);
        player?.pause();
        aed.querySelectorAll(".luna-al-ph").forEach((p) => { p.style.display = "none"; });
        const b = aed.querySelector(".luna-al-play");
        if (b) b.textContent = "▶";
    }

    function renderAudio() {
        stopPlay();
        const media = readMedia(node);
        if (selAudio < 0 || !media.audio[selAudio]) {
            aed.style.display = "none";
            aed.replaceChildren();
            return;
        }
        aed.style.display = "";
        const idx = selAudio;
        const card = { fill: "silence", snap: "off", position: "free", song_start: 0, shot: 1, overlap: 22, ...media.audio[idx] };
        const byShot = card.position === "shot";
        let start = Number(card.start) || 0, songStart = Number(card.song_start) || 0;
        let dur = Number(card.duration) || 0, info = null;
        const ws = wiredSeconds(), wsh = wiredShot();
        const shotNo = () => Math.max(1, Math.round(wsh.wired && wsh.value > 0 ? wsh.value : Number(card.shot) || 1));

        aed.innerHTML = `
            <div class="luna-al-ahead"><b>A${idx + 1}</b><span class="nm"></span><span class="sp"></span><span class="meta">reading the song…</span>
              <div class="luna-al-play" title="Play the window">▶</div></div>
            <div class="luna-al-wave"><canvas></canvas><div class="luna-al-win"><div class="h l"></div><div class="h r"></div><div class="tag"></div></div><div class="luna-al-ph"></div></div>
            <div class="luna-al-ruler"></div>
            <div class="luna-al-zlbl"><span>Zoom on the window (± 1 s) · drag to fine-tune the start</span><span class="zr"></span></div>
            <div class="luna-al-zoom"><canvas></canvas><div class="luna-al-ph"></div></div>
            <div class="luna-al-nums">
              <span class="l stl">Start</span><div class="luna-al-nf"><span class="luna-al-nud" data-n="-1" title="0.1 s earlier">◀</span><input class="st"><span class="luna-al-nud" data-n="1" title="0.1 s later">▶</span></div>
              <span class="l">Duration</span><div class="luna-al-nf"><input class="du"><span class="luna-al-lock dl"></span></div>
              <span class="l">Window</span><div class="luna-al-nf"><input class="en" readonly tabindex="-1" style="width:120px"></div><span></span><span></span>
            </div>
            <div class="rolehost" style="display:flex;flex-direction:column;gap:5px"></div>
            <div class="luna-al-row"><div class="luna-al-lbl">Position</div><div class="luna-al-seg pos"></div></div>
            <div class="luna-al-row shotrow"><div class="luna-al-lbl">Shot</div>
              <div class="luna-al-nf"><span class="luna-al-nud" data-s="-1" title="Previous shot">◀</span><input class="sn" style="width:46px"><span class="luna-al-nud" data-s="1" title="Next shot">▶</span><span class="luna-al-lock sl"></span></div></div>
            <div class="luna-al-row ovrow"><div class="luna-al-lbl">Overlap</div><div class="luna-al-seg ov"></div></div>
            <div class="luna-al-row"><div class="luna-al-lbl">Song ends</div><div class="luna-al-seg fill"></div></div>
            <div class="luna-al-row snaprow"><div class="luna-al-lbl">Snap</div><div class="luna-al-seg snap"></div></div>
            <div class="luna-al-astat"></div>`;
        const $ = (s) => aed.querySelector(s);
        $(".nm").textContent = card.file;
        const wave = $(".luna-al-wave"), win = $(".luna-al-win"), zoom = $(".luna-al-zoom");
        const [phW, phZ] = aed.querySelectorAll(".luna-al-ph");
        const iSt = $(".st"), iDu = $(".du"), iEn = $(".en"), iSn = $(".sn");
        roleRow($(".rolehost"), "a", idx,
                idx === 0 ? [["lock", "Lock to shot"], ["guide", "Guide at frame"], ["ref", "Reference"]]
                          : [["guide", "Guide at frame"], ["ref", "Reference"]],   // the shot has one locked sound: the song
                soundRole(card, idx), Number(card.at) || 0, 1);

        const total = () => info?.duration || 0;
        // dur 0 means "to the end of the file"; a wired seconds input wins over both.
        const eff = () => (ws.wired && ws.value > 0) ? ws.value
            : (dur > 0 ? dur : (byShot ? 0 : Math.max(0, total() - start)));
        const step = () => shotStep(eff(), Number(card.overlap) || 0);
        // The window this run uses. In shot mode it is derived from where shot 1 begins.
        const winStart = () => byShot ? songStart + (shotNo() - 1) * step() : start;
        const clampWin = (t) => Math.max(byShot ? (shotNo() - 1) * Math.max(0, step()) : 0,
            Math.min(t, Math.max(0, total() - Math.min(eff(), total()))));
        // Moving the window: free mode moves it; shot mode moves every shot together.
        const setWin = (t) => {
            const c = clampWin(t);
            if (byShot) songStart = Math.max(0, c - (shotNo() - 1) * step()); else start = c;
        };

        const seg = (host, opts, cur, pick) => {
            host.replaceChildren();
            for (const [val, text] of opts) {
                const o = document.createElement("div");
                o.className = "luna-al-opt" + (val === cur ? " on" : "");
                o.textContent = text;
                o.onclick = () => pick(val);
                host.appendChild(o);
            }
        };
        seg($(".pos"), [["free", "Free"], ["shot", "By shot number"]], card.position, (v) => {
            if (v === card.position) return;
            if (v === "shot") {
                // Start from what is on screen: this window becomes shot 1, and a
                // whole-song window becomes one H3 shot (124 frames) rather than nothing.
                if (!ws.wired && !(dur > 0)) dur = 124 / H3_FPS;
                commit({ position: "shot", song_start: +start.toFixed(6), shot: 1, duration: +dur.toFixed(6) });
            } else commit({ position: "free", start: +winStart().toFixed(6) });
        });
        seg($(".ov"), [[5, "5 frames"], [22, "22 frames"], [39, "39 frames"]], Number(card.overlap), (v) => commit({ overlap: v }));
        seg($(".fill"), [["silence", "Silence"], ["loop", "Loop the song"]], card.fill, (v) => commit({ fill: v }));
        seg($(".snap"), [["off", "Off"], ["h3", "H3 shot grid (17k+5 at 24 fps)"]], card.snap, (v) => {
            commit({ snap: v, duration: v === "h3" && dur > 0 ? snapH3Seconds(dur) : dur });
        });
        $(".snaprow").style.display = ws.wired ? "none" : "";
        $(".shotrow").style.display = $(".ovrow").style.display = byShot ? "" : "none";
        $(".stl").textContent = byShot ? "Song start" : "Start";

        function commit(patch = {}) {
            const m = readMedia(node);
            if (!m.audio[idx]) return;
            m.audio[idx] = { ...m.audio[idx], start: +start.toFixed(6), song_start: +songStart.toFixed(6),
                             duration: +dur.toFixed(6), ...patch };
            writeMedia(node, m);
            render();
        }

        function draw() {
            const e = eff(), T = total(), a = winStart(), n = shotNo();
            const N = byShot && T ? shotCount(T, songStart, e, Number(card.overlap) || 0) : 0;
            iSt.value = clock(byShot ? songStart : start);
            iDu.value = `${e.toFixed(2)} s`;
            iEn.value = `${clock(a)} – ${clock(a + e)}`;
            iDu.readOnly = ws.wired;
            iDu.classList.toggle("lockd", ws.wired);
            $(".dl").textContent = ws.wired
                ? (ws.value > 0 ? `🔒 ${Math.round(e * H3_FPS)} frames · ${ws.from}` : `🔒 set by ${ws.from} — known after a run`)
                : `${Math.round(e * H3_FPS)} frames at 24 fps`;
            iSn.value = String(n);
            iSn.readOnly = wsh.wired;
            iSn.classList.toggle("lockd", wsh.wired);
            $(".sl").textContent = wsh.wired
                ? (wsh.value > 0 ? `🔒 from ${wsh.from}` : `🔒 set by ${wsh.from} — known after a run`)
                : (N ? `of ${N}` : "");
            win.classList.toggle("locked", ws.wired);
            if (T) {
                const W = wave.getBoundingClientRect().width;
                win.style.left = `${Math.min(a, T) / T * W}px`;
                win.style.width = `${Math.max(3, Math.min(e, Math.max(0, T - a)) / T * W)}px`;
                $(".tag").textContent = byShot ? `shot ${n} · ${e.toFixed(2)} s` : `${e.toFixed(2)} s`;
                const cv = wave.querySelector("canvas");
                drawWave(cv, info, 0, T, a, a + e);
                if (byShot && step() > 0) drawShotStrip(cv, T, N, n, e);
                const z0 = a - 1, z1 = a + e + 1;
                drawWave(zoom.querySelector("canvas"), info, z0, z1, a, a + e, { grid: true, step: 1 });
                $(".zr").textContent = `${clock(Math.max(0, z0))} – ${clock(z1)}`;
            }
            const last = _lastSong.get(node.id);
            let msg;
            if (byShot && step() <= 0)
                msg = `<span class="w">The overlap is as long as the shot, so the song would never move on. Choose a smaller overlap.</span>`;
            else if (byShot && T && a >= T)
                msg = `<span class="w">Shot ${n} would start at ${clock(a)}, after the song ends (${clock(T)}). This song has ${N} shot(s); the run will stop with that message.</span>`;
            else if (byShot)
                msg = `Shot <b>${n}</b>${N ? ` of ${N}` : ""} uses the song from <b>${clock(a)}</b> to <b>${clock(a + e)}</b>`
                    + (n > 1 && Number(card.overlap) ? `, sharing its first ${(Number(card.overlap) / H3_FPS).toFixed(2)} s with shot ${n - 1}` : "")
                    + `. Each shot starts ${step().toFixed(2)} s after the one before. Change the shot number${wsh.wired ? "" : " (or wire <b>shot</b>)"} and the window follows; dragging moves every shot together.`;
            else msg = ws.wired
                ? `The duration comes from the <b>seconds</b> input, so the song always matches the shot. Move the window or type a start.`
                : `Drag the window to choose the part; drag its edges or type Start and Duration.`;
            const short = T && a < T ? a + e - T : 0;
            if (short > 0.005)
                msg += `<br><span class="w">The song ends ${short.toFixed(2)} s before the window does; that part will be ${card.fill === "loop" ? "the song again from its start" : "silence"}.</span>`;
            if (last && last.name === card.file)
                msg += `<br>Last run: ${last.shot ? `shot ${last.shot}, ` : ""}${clock(last.start)}–${clock(last.start + last.seconds)}, ${last.seconds.toFixed(2)} s${last.filled > 0.0005 ? `, ${last.filled.toFixed(2)} s filled` : ""}.`;
            $(".luna-al-astat").innerHTML = msg;
        }

        // Every shot's window as a thin strip along the top of the song; the current one in pink.
        function drawShotStrip(cv, T, N, n, e) {
            if (!cv?.isConnected) return;
            const g = cv.getContext("2d"), W = cv.getBoundingClientRect().width;
            g.font = "9px Segoe UI, system-ui, sans-serif";
            for (let k = 1; k <= N; k++) {
                const s = songStart + (k - 1) * step();
                const x0 = s / T * W, x1 = Math.min(T, s + e) / T * W, cur = k === n;
                g.fillStyle = cur ? "#e07bb4" : (k % 2 ? "#3a3d48" : "#4f5361");
                g.fillRect(x0, k % 2 ? 1 : 5, Math.max(1, x1 - x0), 3);
                if (cur || k === 1 || k === N) { g.fillStyle = cur ? "#e07bb4" : "#8b8e99"; g.fillText(String(k), x0 + 1, 17); }
            }
        }

        const ruler = () => {
            const T = total(), r = $(".luna-al-ruler");
            r.replaceChildren();
            if (!T) return;
            const stp = T > 240 ? 60 : T > 90 ? 30 : T > 30 ? 10 : 5;
            for (let t = 0; t <= T; t += stp) {
                const s = document.createElement("span");
                s.style.left = `${t / T * 100}%`;
                s.textContent = clock(t).replace(/\.\d+$/, "");
                r.appendChild(s);
            }
        };

        loadPeaks(card.file).then((p) => {
            if (!aed.isConnected || aed.contains(win) === false) return;
            info = p;
            // The stored start is NOT clamped here: Python uses it as stored, so the
            // window is drawn where it really is and the status says if the song runs
            // out. Only a user's move is kept inside the song.
            $(".meta").textContent = `${clock(p.duration)} · ${(p.sampleRate / 1000).toFixed(1)} kHz · ${p.channels === 1 ? "mono" : p.channels === 2 ? "stereo" : p.channels + " ch"}`;
            ruler();
            setTimeout(draw, 0);     // not rAF: a background tab never runs it
        }).catch(() => { $(".meta").textContent = "this file cannot be read by the browser"; });
        draw();

        // Window: the body moves it, the edges resize it (not while seconds is wired;
        // in shot mode only the right edge, which is the shot length).
        let drag = null;
        win.addEventListener("pointerdown", (e) => {
            if (!info) return;
            const edge = e.target.classList.contains("h") ? (e.target.classList.contains("l") ? "l" : "r") : "m";
            if (edge !== "m" && ws.wired) { notice("The duration comes from the seconds input."); return; }
            if (edge === "l" && byShot) { notice("In shot mode the window starts where the shot number puts it."); return; }
            drag = { edge, x: e.clientX, a: winStart(), d: eff() };
            win.setPointerCapture(e.pointerId);
            e.preventDefault();
        });
        win.addEventListener("pointermove", (e) => {
            if (!drag) return;
            const T = total(), dt = (e.clientX - drag.x) / wave.getBoundingClientRect().width * T;
            if (drag.edge === "m") setWin(drag.a + dt);
            else if (drag.edge === "l") {
                start = Math.max(0, Math.min(drag.a + drag.d - 0.1, drag.a + dt));
                dur = drag.a + drag.d - start;
            } else dur = Math.max(0.1, Math.min(T - drag.a, drag.d + dt));
            draw();
        });
        const end = () => {
            if (!drag) return;
            const resized = drag.edge !== "m";
            drag = null;
            if (resized && card.snap === "h3") dur = snapH3Seconds(dur);
            commit();
        };
        win.addEventListener("pointerup", end);
        win.addEventListener("pointercancel", end);
        // A click on the song outside the window centres the window there.
        wave.addEventListener("pointerdown", (e) => {
            if (!info || win.contains(e.target)) return;
            const r = wave.getBoundingClientRect();
            setWin((e.clientX - r.left) / r.width * total() - eff() / 2);
            commit();
        });
        // The zoom strip pans the window finely: the song moves with the hand.
        let zd = null;
        zoom.addEventListener("pointerdown", (e) => { if (!info) return; zd = { x: e.clientX, a: winStart() }; zoom.setPointerCapture(e.pointerId); });
        zoom.addEventListener("pointermove", (e) => {
            if (!zd) return;
            setWin(zd.a - (e.clientX - zd.x) / zoom.getBoundingClientRect().width * (eff() + 2));
            draw();
        });
        const zEnd = () => { if (zd) { zd = null; commit(); } };
        zoom.addEventListener("pointerup", zEnd);
        zoom.addEventListener("pointercancel", zEnd);

        aed.querySelectorAll("[data-n]").forEach((b) => {
            b.onclick = () => { setWin(winStart() + 0.1 * Number(b.dataset.n)); commit(); };
        });
        aed.querySelectorAll("[data-s]").forEach((b) => {
            b.onclick = () => {
                if (wsh.wired) { notice("The shot number comes from the shot input."); return; }
                commit({ shot: Math.max(1, (Number(card.shot) || 1) + Number(b.dataset.s)) });
            };
        });
        iSt.onchange = () => {
            const v = parseClock(iSt.value);
            if (v != null) { if (byShot) songStart = Math.max(0, v); else start = clampWin(v); }
            commit();
        };
        iDu.onchange = () => {
            if (ws.wired) return;
            const v = parseClock(iDu.value);
            if (v != null && v > 0) dur = card.snap === "h3" ? snapH3Seconds(v) : v;
            commit();
        };
        iSn.onchange = () => {
            if (wsh.wired) return;
            const v = Math.round(Number(iSn.value));
            commit(Number.isFinite(v) && v >= 1 ? { shot: v } : {});
        };
        for (const inp of [iSt, iDu, iSn]) inp.addEventListener("keydown", (e) => { if (e.key === "Enter") inp.blur(); });

        $(".luna-al-play").onclick = () => {
            if (!info) return;
            if (player && !player.paused) { stopPlay(); return; }
            player = player || new Audio();
            const src = soundURL(card.file);
            if (!player.src.endsWith(src)) player.src = src;
            const a = winStart(), b = a + Math.min(eff(), total() - a);
            player.currentTime = a;
            player.play().catch(() => notice("The browser would not start playback."));
            $(".luna-al-play").textContent = "■";
            const tick = () => {
                const t = player.currentTime;
                if (t >= b || player.paused) { stopPlay(); return; }
                const T = total(), W = wave.getBoundingClientRect().width, Z = zoom.getBoundingClientRect().width;
                phW.style.display = phZ.style.display = "block";
                phW.style.left = `${t / T * W}px`;
                phZ.style.left = `${(t - (a - 1)) / (eff() + 2) * Z}px`;
                playRaf = requestAnimationFrame(tick);
            };
            playRaf = requestAnimationFrame(tick);
        };
    }

    /* ------------------------------------------------- continuation editor */

    function renderContinuation() {
        const m = readMedia(node);
        if (!selCont || !m.continuation?.on) {
            selCont = selCont && !!m.continuation?.on;
            ced.style.display = "none";
            ced.replaceChildren();
            return;
        }
        ced.style.display = "";
        const c = { ...NEW_CONT, ...m.continuation }, n = contFrames(m, wiredShot().value);
        ced.innerHTML = `
            <div class="luna-al-ahead"><b>↺ Continuation</b><span>the end of the previous shot opens this one</span><span class="sp"></span>
              <div class="luna-al-play off" title="Turn the continuation off">Off</div></div>
            <div class="luna-al-strip cstrip" style="height:40px"></div>
            <div class="luna-al-zlbl"><span class="cwhat">…</span><span class="cfr"></span></div>
            <div class="luna-al-row"><div class="luna-al-lbl">Take</div><div class="luna-al-seg take"></div></div>
            <div class="luna-al-row frow"><div class="luna-al-lbl">Frames</div><div class="luna-al-seg frs"></div></div>
            <div class="luna-al-row"><div class="luna-al-lbl">From</div><div class="luna-al-seg from"></div></div>
            <div class="luna-al-row frow2"><div class="luna-al-lbl src"></div><div class="luna-al-nf"><input class="cin" style="width:220px"></div></div>
            <div class="luna-al-astat"></div>`;
        const $ = (s) => ced.querySelector(s);
        const set = (patch) => { const mm = readMedia(node); mm.continuation = { ...c, ...patch }; writeMedia(node, mm); render(); };
        const seg = (host, opts, cur, f) => {
            host.replaceChildren();
            for (const [val, text] of opts) {
                const o = document.createElement("div");
                o.className = "luna-al-opt" + (String(val) === String(cur) ? " on" : "");
                o.textContent = text;
                o.onclick = () => f(val);
                host.appendChild(o);
            }
        };
        $(".off").onclick = () => set({ on: false });
        seg($(".take"), [["frames", "Last frames (a clip)"], ["last", "Last frame (a picture)"]], c.take, (v) => set({ take: v }));
        if (n.fromSong || c.take === "last") {
            $(".frs").innerHTML = `<span class="luna-al-lock">${c.take === "last" ? "1 frame" : `= the song's overlap, ${Number(m.audio[0]?.overlap ?? 22)} frames`}</span>`;
        } else seg($(".frs"), [[5, "5"], [22, "22"], [39, "39"]], c.frames, (v) => set({ frames: v }));
        seg($(".from"), [["folder", "Newest in an output folder"], ["file", "A file"], ["input", "previous_frames input"]], c.from, (v) => set({ from: v }));
        const inp = $(".cin");
        if (c.from === "input") $(".frow2").style.display = "none";
        $(".src").textContent = c.from === "folder" ? "Folder" : "File";
        inp.placeholder = c.from === "folder" ? "e.g. music_video  (empty = the output folder)" : "a video in the input folder";
        inp.value = c.from === "folder" ? c.folder : c.file;
        inp.onchange = () => set(c.from === "folder" ? { folder: inp.value.trim() } : { file: inp.value.trim() });
        inp.addEventListener("keydown", (e) => { if (e.key === "Enter") inp.blur(); });

        const describe = (name) => {
            const k = n.frames;
            $(".cwhat").textContent = name ? `from ${name}` : "no video found yet";
            $(".cfr").textContent = n.shot1 ? "" : k === 1 ? "frame 0" : `frames 0–${k - 1} of this shot`;
            let msg = n.shot1
                ? "This is <b>shot 1</b>: nothing comes before it, so the continuation is skipped."
                : `Frames <b>0–${k - 1}</b> of this shot are guided by the last ${k === 1 ? "frame" : `${k} frames`} of the previous shot, so the motion carries on across the cut.`;
            if (n.fromSong && !n.shot1) msg += ` The song windows overlap by the same ${(k / H3_FPS).toFixed(2)} s, so sound and picture line up.`;
            if (c.from === "folder") msg += `<br>Takes whatever video was written last into <b>output/${(c.folder || "").replace(/[<>&]/g, "")}</b> — point your save node there.`;
            if (c.from === "input") msg += `<br>Wire the previous shot's frames into <b>previous_frames</b>.`;
            $(".luna-al-astat").innerHTML = msg;
            if (name && c.from !== "input") $(".cstrip").style.backgroundImage = "";
        };
        if (c.from === "folder") {
            fetch(`/lunasave/newest-video?folder=${encodeURIComponent(c.folder || "")}`)
                .then((r) => r.json()).then((j) => describe(j.name ? `${j.name}${j.duration ? ` (${j.duration.toFixed(2)} s)` : ""}` : null))
                .catch(() => describe(null));
        } else if (c.from === "file" && c.file) {
            $(".cstrip").style.backgroundImage = `url("${stripURL(c.file, 12)}")`;
            describe(c.file);
        } else describe(c.from === "input" ? "the previous_frames input" : null);
    }

    /* --------------------------------------------------------- clip editor */

    function renderVideo() {
        const vplayer = ved.querySelector("video");
        if (vplayer) { vplayer.pause(); vplayer.removeAttribute("src"); vplayer.load(); }
        const media = readMedia(node);
        if (selVideo < 0 || !media.video[selVideo]) {
            ved.style.display = "none";
            ved.replaceChildren();
            return;
        }
        ved.style.display = "";
        const idx = selVideo, card = { ...NEW_VIDEO, ...media.video[idx] };
        let start = Number(card.start) || 0, frames = Math.max(1, Number(card.frames) || 124), mi = null;
        const ww = wiredNumber("width", () => null), wh = wiredNumber("height", () => null);

        ved.innerHTML = `
            <div class="luna-al-ahead"><b>&lt;Video ${idx + 1}&gt;</b><span class="nm"></span><span class="sp"></span><span class="meta">reading the clip…</span>
              <div class="luna-al-play" title="Play the clip window">▶</div></div>
            <video class="luna-al-video" muted playsinline preload="metadata"></video>
            <div class="luna-al-zlbl"><span>The whole clip · drag the window to choose the part</span><span class="zr"></span></div>
            <div class="luna-al-strip"><div class="luna-al-win"><div class="h l"></div><div class="h r"></div><div class="tag"></div></div></div>
            <div class="luna-al-ruler"></div>
            <div class="luna-al-nums">
              <span class="l">Start</span><div class="luna-al-nf"><span class="luna-al-nud" data-n="-1" title="One source frame earlier">◀</span><input class="st"><span class="luna-al-nud" data-n="1" title="One source frame later">▶</span></div>
              <span class="l">Length</span><div class="luna-al-nf"><span class="luna-al-nud" data-f="-1" title="Shorter">−</span><input class="fr" style="width:56px"><span class="luna-al-nud" data-f="1" title="Longer">+</span><span class="luna-al-lock fl"></span></div>
            </div>
            <div class="rolehost" style="display:flex;flex-direction:column;gap:5px"></div>
            <div class="luna-al-sect">Load settings</div>
            <div class="luna-al-row"><div class="luna-al-lbl">Frame rate</div><div class="luna-al-seg fps"></div></div>
            <div class="luna-al-row"><div class="luna-al-lbl">Frames</div><div class="luna-al-seg cnt"></div></div>
            <div class="luna-al-row"><div class="luna-al-lbl">Size</div><div class="luna-al-seg size"></div></div>
            <div class="luna-al-row fitrow"><div class="luna-al-lbl">Fit</div><div class="luna-al-seg fit"></div></div>
            <div class="luna-al-row"><div class="luna-al-lbl">Every Nth</div><div class="luna-al-seg nth"></div></div>
            <div class="luna-al-row"><div class="luna-al-lbl">Soundtrack</div><div class="luna-al-seg snd"></div></div>
            <div class="luna-al-row"><div class="luna-al-lbl">Precision</div><div class="luna-al-seg prec"></div></div>
            <div class="luna-al-astat"></div>`;
        const $ = (s) => ved.querySelector(s);
        $(".nm").textContent = card.file;
        const video = $("video"), strip = $(".luna-al-strip"), win = $(".luna-al-win");
        const iSt = $(".st"), iFr = $(".fr");
        roleRow($(".rolehost"), "v", idx, [["ref", "Reference"], ["guide", "On the shot"]],
                clipRole(card), Number(card.at) || 0, clipLen(card));
        video.src = soundURL(card.file);
        strip.style.backgroundImage = `url("${stripURL(card.file, 16)}")`;

        const outFps = () => card.fps === "target" ? H3_FPS : card.fps === "source" ? (mi?.fps || H3_FPS) : Number(card.fps);
        const dur = () => mi?.duration || 0;
        const clipS = () => frames / outFps();
        const outSize = () => {
            if (!mi) return [0, 0];
            if (card.size === "canvas" && ww.value > 0 && wh.value > 0) return [ww.value, wh.value];
            if (card.size === "source") return [mi.width, mi.height];
            // Same rule as media_io._target_size: scale the short edge to 768, never
            // up, then even dimensions.
            const s = Math.min(1, 768 / Math.min(mi.width, mi.height));
            const ev = (v) => Math.max(2, v - (v % 2));
            return [ev(Math.round(mi.width * s)), ev(Math.round(mi.height * s))];
        };
        const clampStart = (t) => Math.max(0, Math.min(t, Math.max(0, dur() - Math.min(clipS(), dur()))));
        const snapCount = (n) => card.count === "target" ? nearestH3Frames(n) : Math.max(1, Math.round(n));

        const seg = (host, opts, cur, pickOpt) => {
            host.replaceChildren();
            for (const [val, text] of opts) {
                const o = document.createElement("div");
                o.className = "luna-al-opt" + (String(val) === String(cur) ? " on" : "");
                o.textContent = text;
                o.onclick = () => pickOpt(val);
                host.appendChild(o);
            }
        };
        const opts = () => {
            seg($(".fps"), [["target", "H3 (24)"], ["source", `Source${mi?.fps ? ` (${+mi.fps.toFixed(2)})` : ""}`], [24, "24"], [25, "25"], [30, "30"]], card.fps, (v) => commit({ fps: v }));
            seg($(".cnt"), [["target", "H3 grid (17k+5)"], ["free", "Free"]], card.count, (v) => {
                card.count = v;
                commit({ count: v, frames: snapCount(frames) });
            });
            seg($(".size"), [["canvas", ww.wired && wh.wired ? "Match canvas" : "Match canvas (not wired)"], ["edge", "768 short edge"], ["source", "Source"]], card.size, (v) => commit({ size: v }));
            seg($(".fit"), [["crop", "Crop to fill"], ["pad", "Pad"], ["stretch", "Stretch"]], card.fit, (v) => commit({ fit: v }));
            seg($(".nth"), [[1, "All"], [2, "2nd"], [3, "3rd"], [4, "4th"]], card.nth, (v) => commit({ nth: v }));
            seg($(".snd"), [["keep", mi && !mi.audio ? "Keep (none in file)" : "Keep"], ["drop", "Drop"]], card.sound, (v) => commit({ sound: v }));
            seg($(".prec"), [["fp16", "fp16 (half the memory)"], ["fp32", "fp32"]], card.precision, (v) => commit({ precision: v }));
            $(".fitrow").style.display = card.size === "canvas" ? "" : "none";
        };

        function commit(patch = {}) {
            const m = readMedia(node);
            if (!m.video[idx]) return;
            m.video[idx] = { ...m.video[idx], start: +start.toFixed(6), frames, ...patch };
            writeMedia(node, m);
            render();
        }

        function draw() {
            const fps = outFps(), T = dur(), s = clipS();
            iSt.value = clock(start);
            iFr.value = String(frames);
            $(".fl").textContent = `${s.toFixed(2)} s at ${+fps.toFixed(3)} fps`;
            if (T) {
                win.style.left = `${Math.min(start, T) / T * 100}%`;
                win.style.width = `${Math.max(0.6, Math.min(s, Math.max(0, T - start)) / T * 100)}%`;
                $(".tag").textContent = `${frames} f · ${s.toFixed(2)} s`;
                $(".zr").textContent = `${clock(start)} – ${clock(start + s)}`;
            }
            const [w, h] = outSize();
            const kept = Math.ceil(frames / Math.max(1, card.nth));
            const gb = w && h ? kept * w * h * 3 * (card.precision === "fp16" ? 2 : 4) / 1024 ** 3 : 0;
            let msg = w ? `Will decode <b>${kept} frames at ${w}×${h}</b> = <b>${gb.toFixed(2)} GB</b> as ${card.precision}.` : "";
            if (gb > MEMORY_CAP_GB) msg += ` <span class="w">That is more than the ${MEMORY_CAP_GB} GB this node allows; the run will refuse it.</span>`;
            if (card.count === "target" && Number(card.nth) > 1)
                msg += `<br><span class="w">Every Nth on the H3 grid makes H3 play the clip faster (it assumes 24 fps) and its sound no longer matches — the run refuses it. Keep every frame, or set Frames to Free.</span>`;
            if (card.size === "canvas" && !(ww.value > 0 && wh.value > 0))
                msg += `<br><span class="w">Match canvas needs <b>width</b> and <b>height</b> wired; until then the clip keeps its shape at a 768 short edge.</span>`;
            if (T && start + s > T + 1e-3)
                msg += `<br><span class="w">The clip ends ${(start + s - T).toFixed(2)} s before the window does; the run takes what is there${card.count === "target" ? ", cut down to the H3 grid" : ""}.</span>`;
            if (mi) {
                const how = mi.fps && Math.abs(fps - mi.fps) > 0.01 ? (fps < mi.fps ? "drops frames" : "repeats frames") : "unchanged";
                msg += `<br>${+mi.fps.toFixed(2)} → ${+fps.toFixed(2)} fps (${how}). MiniMax H3 sees it as <b>&lt;Video ${idx + 1}&gt;</b>${card.sound === "keep" && mi.audio ? ", its sound as the &lt;Audio&gt; right before it" : ""}.`;
            }
            $(".luna-al-astat").innerHTML = msg;
        }

        const ruler = () => {
            const T = dur(), r = $(".luna-al-ruler");
            r.replaceChildren();
            if (!T) return;
            const stp = T > 120 ? 30 : T > 40 ? 10 : T > 15 ? 5 : T > 6 ? 2 : 1;
            for (let t = 0; t <= T + 1e-6; t += stp) {
                const sp = document.createElement("span");
                sp.style.left = `${t / T * 100}%`;
                sp.textContent = `${t}s`;
                r.appendChild(sp);
            }
        };

        opts();
        draw();
        mediaInfo(card.file).then((info) => {
            if (!ved.contains(win)) return;
            mi = info;
            $(".meta").textContent = `${info.width}×${info.height} · ${+(info.fps || 0).toFixed(2)} fps · ${(info.duration || 0).toFixed(2)} s · ${info.audio ? "sound" : "no sound"}`;
            opts(); ruler();
            setTimeout(draw, 0);
        }).catch(() => { $(".meta").textContent = "this clip cannot be read"; });

        let drag = null;
        win.addEventListener("pointerdown", (e) => {
            if (!mi) return;
            const edge = e.target.classList.contains("h") ? (e.target.classList.contains("l") ? "l" : "r") : "m";
            drag = { edge, x: e.clientX, s: start, f: frames };
            win.setPointerCapture(e.pointerId);
            e.preventDefault();
        });
        win.addEventListener("pointermove", (e) => {
            if (!drag) return;
            const dt = (e.clientX - drag.x) / strip.getBoundingClientRect().width * dur();
            if (drag.edge === "m") start = clampStart(drag.s + dt);
            else if (drag.edge === "r") frames = Math.max(1, Math.round(drag.f + dt * outFps()));
            else {
                const s0 = Math.max(0, Math.min(drag.s + drag.f / outFps() - 0.05, drag.s + dt));
                frames = Math.max(1, Math.round(drag.f - (s0 - drag.s) * outFps()));
                start = s0;
            }
            draw();
        });
        const end = () => {
            if (!drag) return;
            const resized = drag.edge !== "m";
            drag = null;
            if (resized) frames = snapCount(frames);
            commit();
        };
        win.addEventListener("pointerup", end);
        win.addEventListener("pointercancel", end);
        strip.addEventListener("pointerdown", (e) => {
            if (!mi || win.contains(e.target)) return;
            const r = strip.getBoundingClientRect();
            start = clampStart((e.clientX - r.left) / r.width * dur() - clipS() / 2);
            commit();
        });
        ved.querySelectorAll("[data-n]").forEach((b) => {
            b.onclick = () => { start = clampStart(start + Number(b.dataset.n) / (mi?.fps || H3_FPS)); commit(); };
        });
        ved.querySelectorAll("[data-f]").forEach((b) => {
            b.onclick = () => {
                frames = card.count === "target" ? stepH3Frames(frames, Number(b.dataset.f)) : Math.max(1, frames + Number(b.dataset.f));
                commit();
            };
        });
        iSt.onchange = () => { const v = parseClock(iSt.value); if (v != null) start = clampStart(v); commit(); };
        iFr.onchange = () => { const v = Math.round(Number(iFr.value)); if (v >= 1) frames = snapCount(v); commit(); };
        for (const inp of [iSt, iFr]) inp.addEventListener("keydown", (e) => { if (e.key === "Enter") inp.blur(); });

        let vt = 0;
        $(".luna-al-play").onclick = () => {
            if (!mi) return;
            if (!video.paused) { video.pause(); clearTimeout(vt); $(".luna-al-play").textContent = "▶"; return; }
            video.currentTime = start;
            video.play().catch(() => notice("The browser would not start playback."));
            $(".luna-al-play").textContent = "■";
            clearTimeout(vt);
            vt = setTimeout(() => { video.pause(); $(".luna-al-play").textContent = "▶"; }, Math.min(clipS(), dur() - start) * 1000);
        };
        video.addEventListener("loadedmetadata", () => { try { video.currentTime = start; } catch { /* not seekable yet */ } });
    }

    // Added up from its rows, like AUDIO_H; never measured. + Role, + At frame.
    const videoHeight = () => {
        const c = readMedia(node).video[selVideo];
        return 572 + 28 + (c && clipRole(c) === "guide" ? 28 : 0);
    };
    const timelineHeight = () => {
        const m = readMedia(node);
        return readPaths(node).length || m.video.length || m.audio.length ? 222 : 0;
    };

    return { root, render, selectCard: (i) => { selected = i; renderPanel(); }, natural,
             audioOpen: () => selAudio >= 0, audioExtraRows,
             videoOpen: () => selVideo >= 0, videoHeight, timelineHeight,
             contOpen: () => selCont && !!readMedia(node).continuation?.on };
}

/* ---------------------------------------------------------------- register */

app.registerExtension({
    name: "LunaSaveSimple.AssetLoader",
    setup() { patchDeserialize(); },
    beforeConfigureGraph(graphData) {
        const moved = migrateWorkflowJSON(graphData);
        if (moved.length) console.info("[Luna Asset Loader] updated a workflow saved before the audio/refs/timeline outputs:", moved);
    },
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
            // The song editor's height, added up from its rows (head 20, song 64,
            // ruler 12, zoom label 14, zoom 40, two number rows 52, two option
            // rows 50, status 42, gaps and padding 66). Arithmetic, never measured.
            const AUDIO_H = 360;
            const cardsHeight = () => {
                const list = readPaths(this);
                const md = readMedia(this), sounds = md.audio.length + md.video.length + (md.continuation?.on ? 1 : 0);
                const cols = Math.max(1, Math.floor((this.size[0] - 24) / CELL));
                const rows = Math.max(1, Math.ceil((list.length + sounds) / cols));
                const tlh = ui.timelineHeight();
                if (ui.contOpen()) {
                    const h = 250 + tlh;   // head, strip, label, four rows, status — added up, never measured
                    return Math.min(MAXH + h, BAR + PAD + rows * CELL + h);
                }
                if (ui.videoOpen()) {
                    const h = ui.videoHeight() + tlh;
                    return Math.min(MAXH + h, BAR + PAD + rows * CELL + h);
                }
                if (ui.audioOpen()) {
                    const h = AUDIO_H + ui.audioExtraRows() * 28 + tlh;   // Position, Shot + Overlap, Role, At frame
                    return Math.min(MAXH + h, BAR + PAD + rows * CELL + h);
                }
                // The resize panel only exists once there is something to resize,
                // and grows a row when a mode or a ratio is chosen (and with the role rows).
                let panel = 0;
                if (list.length) {
                    const st = itemAt(this, 0);
                    const key = readMedia(this).pictures.some((p) => p?.role === "key");
                    panel = 118 + (st.mode !== "off" ? 26 : 0) + (st.ratio ? 26 : 0) + 28 + (key ? 28 : 0);
                }
                // The preview is a fixed block, so it stays arithmetic like the
                // rest — nothing here is measured from the rendered layout.
                const pv = list.length ? PREVIEW_H + 6 : 0;
                return Math.min(MAXH + tlh, Math.max(MINH, BAR + PAD + rows * CELL + pv + panel + tlh));
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
        nodeType.prototype.onConfigure = function (info) {
            const r = onConfigure?.apply(this, arguments);
            if (info?.outputs?.[4]?.name === "image_1") {
                setTimeout(() => {
                    const n = migrateLiveNode(this);
                    if (n) console.info(`[Luna Asset Loader] moved ${n} wire(s) of a pasted pre-v3 node up by three slots.`);
                }, 0);
            }
            requestAnimationFrame(() => { applyCount(this); this._lunaRender?.(); });
            return r;
        };

        // The run reports what the song window really delivered (and whether the
        // file ran out); the editor shows it as "Last run".
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const r = onExecuted?.apply(this, arguments);
            const s = message?.luna_asset_audio?.[0];
            if (s) _lastSong.set(this.id, s);
            this._lunaRender?.();
            return r;
        };

        // Wiring or unwiring `seconds` / `shot` locks or frees the song's duration
        // and shot number at once.
        const onConn = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, slot, connected, link, ioSlot) {
            const r = onConn?.apply(this, arguments);
            // setTimeout, not requestAnimationFrame: a background tab never runs the
            // latter, and the lock must be right whenever the node is next seen.
            if (WIRED_INPUTS.includes(ioSlot?.name)) setTimeout(() => this._lunaRender?.(), 0);
            return r;
        };

        // Right-click > Colors fires no event, so pick the change up on the next
        // draw. syncAccent early-outs unless the colour actually differs.
        const onDraw = nodeType.prototype.onDrawForeground;
        nodeType.prototype.onDrawForeground = function (ctx) {
            const r = onDraw?.apply(this, arguments);
            if (this._lunaRoot) syncAccent(this, this._lunaRoot);
            const sig = wiredSignature(this);
            if (sig !== this._lunaWiredSig) {
                const first = this._lunaWiredSig === undefined;
                this._lunaWiredSig = sig;
                if (!first) setTimeout(() => this._lunaRender?.(), 0);
            }
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
