// Luna Load Video — the node's face: a player for the chosen file, a line saying
// what a run will load, a ⚙ on the title bar that opens the settings panel.
//
// Player idea after Load Video Pixaroma (ComfyUI-Pixaroma, MIT, (c) 2026 pixaroma,
// js/load_video/index.js): the SOURCE plays on the node before any run. The panel
// follows this pack's Asset Loader ⚙ (itself after LLM Prompt / Pixaroma
// node_panel.mjs, MIT): against the node's right edge, follows pan and zoom, closes
// only on ⚙ / ✕ / Done / Esc, blurs a focused field before it goes.
//
// The five ⚙ settings are ordinary widgets, hidden on the face, so the workflow, the
// API format and Python see plain values. Their sockets refuse links while hidden
// (LLM Prompt's isValidTarget rule): a link onto a socket you cannot see is a trap.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { LUNA } from "./luna_theme.mjs";

const NODE = "LunaLoadVideo";
const PANEL = ["frame_grid", "every_nth", "audio", "precision", "memory_cap_gb"];
const DEFAULTS = { frame_grid: "free", every_nth: 1, audio: "keep", precision: "fp32", memory_cap_gb: 6 };
const PLAN_KEYS = ["video", "start", "frames", "fps", "width", "height", "fit", ...PANEL];
const SOURCE_KEYS = ["source", "path", "folder", "video_count"];
// Which widgets each source shows on the face (the rest of the source widgets hide).
const BY_SOURCE = { "upload": ["video", "upload_video"], "path / URL": ["path"], "folder": ["folder", "video_count"] };
// The widget order before the sources were added (2026-10-22): a save made without
// named values is restored through these names instead of by position.
const OLD_ORDER = ["video", "start", "frames", "fps", "width", "height", "fit", ...PANEL];
const GEAR_R = 7;
const GEAR_INSET = 56;      // ⓘ at size[0] - 16, chevron at - 36
const PLAYER_MIN = 140;     // video area, px at 100 % zoom
const INFO_H = 46;          // the two lines under it

const W = (node, name) => node.widgets?.find((w) => w.name === name);

/* ------------------------------------------------------------------ css */

let _css = false;
function injectCSS() {
    if (_css) return;
    _css = true;
    const C = LUNA;
    const s = document.createElement("style");
    s.id = "luna-lv-css";
    s.textContent = `
.luna-lv [hidden]{display:none!important}
.luna-lv{display:flex;flex-direction:column;gap:4px;width:100%;height:100%;box-sizing:border-box;font:12px Inter,system-ui,sans-serif;color:${C.text}}
.luna-lv-media{position:relative;flex:1 1 auto;min-height:0;background:#000;border-radius:6px;overflow:hidden}
.luna-lv-media video{width:100%;height:100%;object-fit:contain;display:block}
.luna-lv-empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:${C.muted};text-align:center;padding:12px}
.luna-lv-src{color:${C.muted};white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.luna-lv-plan{color:${C.accent};line-height:1.3}
.luna-lv-plan.err{color:${C.danger}}
.luna-lv-plan .w{color:${C.danger}}
.luna-lv-plan .n{color:${C.muted}}
.luna-lv-sp{position:fixed;z-index:1300;width:340px;transform-origin:0 0;background:${C.panel};border:1px solid ${C.accent}66;border-radius:8px;box-shadow:0 10px 30px #000a;font:13px Inter,system-ui,sans-serif;color:${C.text}}
.luna-lv-sp .hd{display:flex;align-items:center;gap:8px;padding:9px 12px;border-bottom:1px solid ${C.border};user-select:none}
.luna-lv-sp .hd .t{flex:1;font-weight:600}
.luna-lv-sp .x,.luna-lv-sp .rs{cursor:pointer;color:${C.muted}}
.luna-lv-sp .x:hover,.luna-lv-sp .rs:hover{color:${C.accent}}
.luna-lv-sp .bd{padding:4px 12px 10px}
.luna-lv-sp .rw{display:grid;grid-template-columns:110px 1fr;align-items:center;gap:8px;margin:7px 0}
.luna-lv-sp .ch{display:flex;gap:4px;flex-wrap:wrap}
.luna-lv-sp .ch span{padding:2px 8px;border:1px solid ${C.border};border-radius:4px;cursor:pointer;color:${C.muted}}
.luna-lv-sp .ch span:hover{color:${C.text}}
.luna-lv-sp .ch span.on{border-color:${C.accent};color:${C.accent};background:${C.accentSoft}}
.luna-lv-sp .nb{width:64px;box-sizing:border-box;background:${C.bg};border:1px solid ${C.border};border-radius:4px;color:${C.text};text-align:center;padding:2px 0}
.luna-lv-sp .nb:focus{outline:none;border-color:${C.accent}}
.luna-lv-sp .nt{color:${C.muted};font-size:11.5px;margin:-3px 0 6px 118px;line-height:1.3}
.luna-lv-sp .ft{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-top:1px solid ${C.border}}
.luna-lv-sp .dn{cursor:pointer;padding:3px 14px;border-radius:4px;background:${C.accent};color:#1a1a1a;font-weight:600}
`;
    document.head.appendChild(s);
}

/* ------------------------------------------------------------- the face */

function viewURL(name) {
    // "sub/clip.mp4 [input]" -> /view?filename=clip.mp4&subfolder=sub&type=input
    let file = String(name || ""), type = "input";
    const m = file.match(/^(.*) \[(input|output|temp)\]$/);
    if (m) { file = m[1]; type = m[2]; }
    const cut = file.lastIndexOf("/");
    const p = new URLSearchParams({ filename: cut >= 0 ? file.slice(cut + 1) : file,
                                    subfolder: cut >= 0 ? file.slice(0, cut) : "", type });
    return api.apiURL(`/view?${p}`);
}

const clock = (s) => {
    s = Math.max(0, Number(s) || 0);
    const m = Math.floor(s / 60);
    return `${m}:${(s - m * 60).toFixed(2).padStart(5, "0")}`;
};

function signature(node) {
    return [...SOURCE_KEYS, ...PLAN_KEYS].map((k) => String(W(node, k)?.value ?? "")).join("|");
}

// What the face can show for the chosen source. A path inside ComfyUI's input folder
// (relative) previews like an upload; a web link plays straight from the web; an
// absolute path or a folder is only read by the run.
const cleanPath = (t) => String(t ?? "").trim().replace(/^["']+|["']+$/g, "").trim();
function current(node) {
    const source = W(node, "source")?.value || "upload";
    if (source === "path / URL") {
        const t = cleanPath(W(node, "path")?.value);
        if (!t) return { kind: "none", msg: "No path or link yet — type one in path." };
        if (/^https?:\/\//i.test(t)) return { kind: "url", url: t };
        if (/^([a-z]:|[\\/]|~)/i.test(t)) return { kind: "local", path: t };
        return { kind: "file", file: t.replace(/\\/g, "/") };
    }
    if (source === "folder") {
        const f = cleanPath(W(node, "folder")?.value), n = Number(W(node, "video_count")?.value) || 0;
        return f ? { kind: "folder", folder: f, count: n } : { kind: "none", msg: "No folder yet — type one in folder." };
    }
    const v = W(node, "video")?.value;
    return v ? { kind: "file", file: v } : { kind: "none", msg: "No video — upload one or pick one from the list." };
}

// The plan line: what a run would load, from the same Python the run uses.
async function refreshPlan(node) {
    const ui = node._lunaLV;
    if (!ui) return;
    const cur = current(node);
    const sig = signature(node);
    ui.sig = sig;
    ui.plan.className = "luna-lv-plan";
    const lastRun = () => {
        if (!ui.last?.length) return;
        const d = document.createElement("span");
        d.className = "n";
        d.textContent = ` · last run: ${ui.last.length > 1 ? `${ui.last.length} videos — ` : ""}${ui.last.join("; ")}`;
        ui.plan.append(d);
    };
    if (cur.kind !== "file") {
        ui.src.textContent = cur.kind === "url" ? cur.url : cur.kind === "local" ? cur.path
            : cur.kind === "folder" ? `${cur.folder}${cur.count ? ` · first ${cur.count} video${cur.count === 1 ? "" : "s"}` : " · every video"}` : "";
        ui.plan.textContent = {
            url: "Loads from the web link at run time (downloaded once into input/luna_downloads).",
            local: "Loads this file at run time; there is no preview for files outside ComfyUI's input folder.",
            folder: "Loads the folder's videos in name order at run time; every node after this one runs once per video.",
            none: "",
        }[cur.kind];
        lastRun();
        return;
    }
    const file = cur.file;
    const q = new URLSearchParams({ file });
    for (const k of PLAN_KEYS.slice(1)) q.set(k, String(W(node, k)?.value ?? ""));
    let r;
    try {
        r = await (await api.fetchApi(`/lunasave/load-video-plan?${q}`)).json();
    } catch { r = { error: "could not ask the server" }; }
    if (ui.sig !== sig) return;   // settings moved on while asking
    const src = r.source;
    ui.src.textContent = src
        ? `${file} · ${src.width}×${src.height} · ${Number(src.fps).toFixed(2).replace(/\.?0+$/, "")} fps · ${clock(src.duration)}${src.audio ? " · sound" : " · no sound"}`
        : file;
    if (r.error) {
        ui.plan.className = "luna-lv-plan err";
        ui.plan.textContent = `Will not load: ${r.error}.`;
        return;
    }
    ui.plan.className = "luna-lv-plan";
    const gb = r.gb >= 0.1 ? `${r.gb.toFixed(2)} GB` : `${Math.max(1, Math.round(r.gb * 1000))} MB`;
    ui.plan.innerHTML = "";
    ui.plan.append(`Loads ${r.frames} frames @ ${Number(r.fps.toFixed(3))} fps · ${r.width}×${r.height} · ${r.seconds.toFixed(2)} s · ${gb}`);
    if (r.over) {
        const w = document.createElement("span");
        w.className = "w";
        w.textContent = ` — over the ${r.cap_gb} GB cap (⚙), the run will refuse it`;
        ui.plan.append(w);
    }
    for (const n of r.notes || []) {
        const s = document.createElement("span");
        s.className = "n";
        s.textContent = ` · ${n}`;
        ui.plan.append(s);
    }
    lastRun();
}

function setSource(node) {
    const ui = node._lunaLV;
    if (!ui) return;
    const cur = current(node);
    const src = cur.kind === "file" ? viewURL(cur.file) : cur.kind === "url" ? cur.url : "";
    ui.empty.textContent = cur.kind === "local" ? "This file plays after it is loaded — no preview outside the input folder."
        : cur.kind === "folder" ? "A folder: its videos load at run time." : (cur.msg || "");
    if (ui.file === src) return;
    ui.file = src;
    if (src) {
        ui.video.src = src;
        ui.video.hidden = false;
        ui.empty.hidden = true;
    } else {
        ui.video.removeAttribute("src");
        ui.video.load();
        ui.video.hidden = true;
        ui.empty.hidden = false;
    }
}

// Show only the widgets the chosen source uses. While the settings are folded the
// chevron owns `hidden`, so the wanted state goes where it restores from.
function showSourceWidgets(node) {
    const source = W(node, "source")?.value || "upload";
    const want = new Set(BY_SOURCE[source] || BY_SOURCE.upload);
    const folded = !!node.properties?.lunaSettingsCollapsed;
    let changed = false;
    for (const name of Object.values(BY_SOURCE).flat()) {
        const w = W(node, name);
        if (!w) continue;
        const hide = !want.has(name);
        if (folded) { if (w._lunaWasHidden !== hide) { w._lunaWasHidden = hide; } continue; }
        if (!!w.hidden !== hide) { w.hidden = hide; changed = true; }
    }
    if (changed) {
        // Arithmetic: the widget stack plus the player, as computeSize adds them up.
        node.setSize([node.size[0], node.computeSize()[1]]);
        node.setDirtyCanvas(true, true);
    }
}

// Settings changes have no single hook (typed value, arrows, a link, undo), so the
// face checks a signature of the values on every draw and asks again when it moves.
function watch(node) {
    const ui = node._lunaLV;
    if (!ui) return;
    const sig = signature(node);
    if (sig === ui.seen) return;
    ui.seen = sig;
    showSourceWidgets(node);
    setSource(node);
    clearTimeout(ui.timer);
    ui.timer = setTimeout(() => refreshPlan(node), 250);
}

function hidePanelWidgets(node) {
    for (const name of PANEL) {
        const w = W(node, name);
        if (!w) continue;
        w.hidden = true;
        w.__lunaPanel = true;
    }
    guardSockets(node);
}

const hiddenFree = (node, inp) => !!inp?.widget && inp.link == null && !!W(node, inp.widget.name ?? inp.name)?.__lunaPanel;
function guardSockets(node) {
    for (const inp of node.inputs || []) {
        if (!inp?.widget) continue;
        if (hiddenFree(node, inp)) inp.isValidTarget = () => false;
        else if (Object.prototype.hasOwnProperty.call(inp, "isValidTarget")) delete inp.isValidTarget;
    }
}

function buildFace(node) {
    injectCSS();
    const root = document.createElement("div");
    root.className = "luna-lv";
    root.innerHTML = `<div class="luna-lv-media"><video controls loop playsinline preload="metadata"></video>
        <div class="luna-lv-empty">No video — upload one or pick one from the list.</div></div>
        <div class="luna-lv-src"></div><div class="luna-lv-plan"></div>`;
    const video = root.querySelector("video");
    for (const ev of ["pointerdown", "mousedown", "touchstart", "wheel"]) {
        video.addEventListener(ev, (e) => e.stopPropagation(), { passive: ev === "wheel" });
    }
    const ui = {
        root, video, empty: root.querySelector(".luna-lv-empty"),
        src: root.querySelector(".luna-lv-src"), plan: root.querySelector(".luna-lv-plan"),
        aspect: 16 / 9, file: undefined, seen: null, sig: null, timer: 0,
    };
    video.hidden = true;
    video.addEventListener("loadedmetadata", () => {
        if (video.videoWidth && video.videoHeight) ui.aspect = video.videoWidth / video.videoHeight;
        node.setDirtyCanvas(true, true);
    });
    node._lunaLV = ui;

    const height = () => Math.max(PLAYER_MIN, (node.size[0] - 20) / ui.aspect) + INFO_H;
    const widget = node.addDOMWidget("luna_lv_player", "preview", root, {
        serialize: false, hideOnZoom: false, getHeight: height,
    });
    widget.serialize = false;   // the player holds no value; keeps widgets_values to the real ones
    widget.computeSize = (width) => [width, height()];
}

/* ------------------------------------------------------------- upload */

const VIDEO_EXT = /\.(mp4|mov|mkv|webm|avi|m4v|mpg|mpeg|wmv|flv)$/i;
const isVideo = (f) => (f?.type || "").startsWith("video/") || VIDEO_EXT.test(f?.name || "");

// Into ComfyUI's input folder through its own /upload/image route (it takes any
// file), then picked in the list. Same route core's video upload uses.
async function uploadFile(node, file) {
    const body = new FormData();
    body.append("image", file);
    const res = await api.fetchApi("/upload/image", { method: "POST", body });
    if (res.status !== 200) {
        alert(`Upload failed (${res.status}): ${res.statusText}`);
        return;
    }
    const d = await res.json();
    const name = d.subfolder ? `${d.subfolder}/${d.name}` : d.name;
    const w = W(node, "video");
    const values = w.options?.values;
    if (Array.isArray(values) && !values.includes(name)) values.push(name);
    w.value = name;
    w.callback?.(name);
    node.setDirtyCanvas(true, true);
}

function addUpload(node) {
    const btn = node.addWidget("button", "choose video to upload", null, () => {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = "video/*,.mkv,.webm,.avi,.m4v,.mpg,.mpeg,.wmv,.flv";
        input.onchange = () => { if (input.files?.[0]) uploadFile(node, input.files[0]); };
        input.click();
    }, { serialize: false });
    btn.name = "upload_video";
    btn.label = "choose video to upload";
    btn.serialize = false;
    // Under the file it uploads to.
    const at = node.widgets.indexOf(btn), to = node.widgets.findIndex((w) => w.name === "video") + 1;
    if (at > to) node.widgets.splice(to, 0, ...node.widgets.splice(at, 1));
}

/* ------------------------------------------------------------ ⚙ panel */

let _sp = null;   // { el, node, stop }
function closePanel() {
    if (!_sp) return;
    const p = _sp;
    _sp = null;
    if (p.el.contains(document.activeElement)) document.activeElement.blur();
    p.stop();
    p.el.remove();
}
const panelOpenFor = (node) => !!_sp && _sp.node === node;

function setValue(node, name, v) {
    const w = W(node, name);
    if (!w) return;
    w.value = v;
    w.callback?.(v);
    node.graph?.setDirtyCanvas?.(true, true);
    node.setDirtyCanvas(true, true);
}

function openPanel(node) {
    if (panelOpenFor(node)) { closePanel(); return; }
    closePanel();
    injectCSS();
    const el = document.createElement("div");
    el.className = "luna-lv-sp";
    el.innerHTML = `<div class="hd"><span>⚙</span><span class="t">Load Video settings</span><span class="x" title="Close">✕</span></div>
        <div class="bd"></div><div class="ft"><span class="rs" title="Back to the defaults">reset</span><span class="dn">Done</span></div>`;
    const body = el.querySelector(".bd");
    const val = (n) => W(node, n)?.value;
    const note = (text) => { const d = document.createElement("div"); d.className = "nt"; d.textContent = text; body.appendChild(d); };
    const chips = (label, name, opts) => {
        const r = document.createElement("div");
        r.className = "rw";
        r.innerHTML = `<span class="l"></span><span class="ch"></span>`;
        r.querySelector(".l").textContent = label;
        for (const [v, text] of opts) {
            const c = document.createElement("span");
            c.textContent = text;
            if (String(v) === String(val(name))) c.className = "on";
            c.onclick = () => { setValue(node, name, v); draw(); };
            r.querySelector(".ch").appendChild(c);
        }
        body.appendChild(r);
    };
    const number = (label, name, unit, lo, hi, isInt) => {
        const r = document.createElement("div");
        r.className = "rw";
        r.innerHTML = `<span class="l"></span><span class="ch"><input class="nb"> ${unit}</span>`;
        r.querySelector(".l").textContent = label;
        const nb = r.querySelector(".nb");
        nb.value = String(val(name));
        nb.onchange = () => {
            const v = isInt ? Math.round(Number(nb.value)) : Number(nb.value);
            if (Number.isFinite(v) && v >= lo && v <= hi) setValue(node, name, v);
            nb.value = String(val(name));
        };
        nb.addEventListener("keydown", (e) => { if (e.key === "Enter") nb.blur(); });
        body.appendChild(r);
    };
    function draw() {
        body.replaceChildren();
        chips("Frame grid", "frame_grid", [["free", "Free"], ["H3 (24 fps, 17k+5)", "H3"], ["LTX (8k+1)", "LTX"]]);
        note({ free: "Any frame count.", "H3 (24 fps, 17k+5)": "24 fps; 5, 22, 39 … 124 … 362 frames.",
               "LTX (8k+1)": "1, 9, 17 … 97 … frames." }[val("frame_grid")] || "");
        number("Every Nth", "every_nth", "frame", 1, 100, true);
        note("1 = every frame. 2 = every second frame, half the fps.");
        chips("Sound", "audio", [["keep", "Keep"], ["drop", "Drop"]]);
        chips("Precision", "precision", [["fp32", "fp32"], ["fp16", "fp16"]]);
        note("fp16 halves the memory; only for nodes that accept it.");
        number("Memory cap", "memory_cap_gb", "GB", 0.5, 128, false);
        note("A bigger load is refused before decoding.");
    }
    draw();
    el.querySelector(".x").onclick = closePanel;
    el.querySelector(".dn").onclick = closePanel;
    el.querySelector(".rs").onclick = () => { for (const [k, v] of Object.entries(DEFAULTS)) setValue(node, k, v); draw(); };
    el.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); closePanel(); } else e.stopPropagation(); });
    el.addEventListener("pointerdown", (e) => e.stopPropagation());
    el.addEventListener("wheel", (e) => e.stopPropagation(), { passive: true });
    document.body.appendChild(el);

    let raf = 0, alive = true;
    const follow = () => {
        if (!alive) return;
        if (!node.graph || app.canvas?.graph !== node.graph) { closePanel(); return; }
        const ds = app.canvas.ds, r = app.canvas.canvas.getBoundingClientRect();
        const th = window.LiteGraph?.NODE_TITLE_HEIGHT || 30;
        el.style.left = `${r.left + (node.pos[0] + node.size[0] + 10 + ds.offset[0]) * ds.scale}px`;
        el.style.top = `${r.top + (node.pos[1] - th + ds.offset[1]) * ds.scale}px`;
        el.style.transform = `scale(${ds.scale})`;
        raf = requestAnimationFrame(follow);
    };
    follow();
    const onEsc = (e) => { if (e.key === "Escape" && !/^(INPUT|TEXTAREA|SELECT)$/.test(e.target?.tagName || "")) closePanel(); };
    document.addEventListener("keydown", onEsc, true);
    _sp = { el, node, stop() { alive = false; cancelAnimationFrame(raf); document.removeEventListener("keydown", onEsc, true); } };
}

/* --------------------------------------------------------- the ⚙ icon */

function gearCentre(node) {
    const h = window.LiteGraph?.NODE_TITLE_HEIGHT ?? 30;
    return [node.size[0] - GEAR_INSET, -h / 2];
}
const onGear = (node, pos) => {
    const [cx, cy] = gearCentre(node);
    return Math.hypot(pos[0] - cx, pos[1] - cy) <= GEAR_R + 3;
};

function drawGear(node, ctx) {
    const [cx, cy] = gearCentre(node);
    const live = node._lunaGearHover || panelOpenFor(node);
    ctx.save();
    ctx.strokeStyle = live ? LUNA.accent : LUNA.muted;
    ctx.fillStyle = live ? LUNA.accent : LUNA.muted;
    ctx.lineWidth = 1.4;
    // Eight teeth around a ring: reads as a cog at 14 px.
    for (let i = 0; i < 8; i++) {
        const a = (i * Math.PI) / 4;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(a) * 4.6, cy + Math.sin(a) * 4.6);
        ctx.lineTo(cx + Math.cos(a) * 7.2, cy + Math.sin(a) * 7.2);
        ctx.lineWidth = 2.2;
        ctx.stroke();
    }
    ctx.beginPath();
    ctx.lineWidth = 1.6;
    ctx.arc(cx, cy, 4.4, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx, cy, 1.6, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
}

/* ---------------------------------------------------------- register */

app.registerExtension({
    name: "LunaSaveSimple.LoadVideo",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== NODE) return;
        const P = nodeType.prototype;
        nodeData.fallbackWidgetsValuesNames = OLD_ORDER;

        const onCreated = P.onNodeCreated;
        P.onNodeCreated = function () {
            const r = onCreated?.apply(this, arguments);
            hidePanelWidgets(this);
            addUpload(this);
            buildFace(this);
            const min = this.computeSize();
            this.setSize([Math.max(this.size[0], 360), Math.max(this.size[1], min[1])]);
            return r;
        };

        const onConfigure = P.onConfigure;
        P.onConfigure = function () {
            const r = onConfigure?.apply(this, arguments);
            hidePanelWidgets(this);
            return r;
        };

        const onDraw = P.onDrawForeground;
        P.onDrawForeground = function (ctx) {
            const r = onDraw?.apply(this, arguments);
            if (!this.flags?.collapsed && ctx) drawGear(this, ctx);
            watch(this);
            guardSockets(this);
            return r;
        };

        const onDown = P.onMouseDown;
        P.onMouseDown = function (e, pos) {
            if (!this.flags?.collapsed && onGear(this, pos)) { openPanel(this); return true; }
            return onDown?.apply(this, arguments);
        };

        const onDbl = P.onDblClick;
        P.onDblClick = function (e, pos) {
            if (!this.flags?.collapsed && onGear(this, pos)) return true;   // no rename editor
            return onDbl?.apply(this, arguments);
        };

        const onMove = P.onMouseMove;
        P.onMouseMove = function (e, pos) {
            const over = !this.flags?.collapsed && onGear(this, pos);
            if (over !== this._lunaGearHover) { this._lunaGearHover = over; this.setDirtyCanvas(true, false); }
            return onMove?.apply(this, arguments);
        };

        // Drag a video file from the desktop onto the node.
        P.onDragOver = function (e) {
            return [...(e?.dataTransfer?.items || [])].some((i) => i.kind === "file");
        };
        const onDrop = P.onDragDrop;
        P.onDragDrop = function (e) {
            const file = [...(e?.dataTransfer?.files || [])].find(isVideo);
            if (!file) return onDrop?.apply(this, arguments) ?? false;
            uploadFile(this, file);
            return true;
        };

        const onConnectInput = P.onConnectInput;
        P.onConnectInput = function (slot) {
            if (hiddenFree(this, this.inputs?.[slot])) return false;
            return onConnectInput ? onConnectInput.apply(this, arguments) : true;
        };

        const onExecuted = P.onExecuted;
        P.onExecuted = function (msg) {
            const r = onExecuted?.apply(this, arguments);
            const lines = msg?.luna_load_video;
            if (Array.isArray(lines) && lines.length && this._lunaLV) {
                this._lunaLV.last = lines;
                this._lunaLV.src.title = `Last run:\n${lines.join("\n")}`;
                refreshPlan(this);
            }
            return r;
        };

        const onRemoved = P.onRemoved;
        P.onRemoved = function () {
            if (panelOpenFor(this)) closePanel();
            clearTimeout(this._lunaLV?.timer);
            return onRemoved?.apply(this, arguments);
        };
    },
});
