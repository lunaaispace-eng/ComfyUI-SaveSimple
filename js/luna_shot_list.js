// Luna Shot List — the table under the script: every scene's song window, editable.
//
// The script text is the truth (it is what runs, what a song analysis writes, what
// a wire can replace). The table is drawn from the server's reading of it — the same
// shot_plan.py the run uses, through /lunasave/shot-list — and an edit in the table
// rewrites only that scene's line, so comments and settings lines stay.
//
// The node also answers lunaValueOf(output) for the scene picked now, so Luna Asset
// Loader can lock its song window to this scene before a run (sourceValue in
// luna_asset_loader.js).

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { LUNA } from "./luna_theme.mjs";

const NODE = "LunaShotList";
const KEYS = ["script", "grid", "overlap", "scene"];
const ROW_H = 24, HEAD_H = 24, FOOT_H = 52, MAX_ROWS = 12;

const W = (node, name) => node.widgets?.find((w) => w.name === name);
const clock = (s) => {
    s = Math.max(0, Number(s) || 0);
    const m = Math.floor(s / 60);
    return `${m}:${(s - m * 60).toFixed(2).padStart(5, "0")}`;
};
// shot_plan.scene_line, for writing an edited row back.
const sceneLine = (start, length, prompt) =>
    `${start.trim().padEnd(8)} | ${length.trim().padEnd(6)} | ${prompt.trim()}`.trimEnd();

let _css = false;
function injectCSS() {
    if (_css) return;
    _css = true;
    const C = LUNA;
    const s = document.createElement("style");
    s.id = "luna-sl-css";
    s.textContent = `
.luna-sl{display:flex;flex-direction:column;width:100%;height:100%;box-sizing:border-box;font:12px Inter,system-ui,sans-serif;color:${C.text}}
.luna-sl [hidden]{display:none!important}
.luna-sl-tb{flex:1 1 auto;min-height:0;overflow:auto;border:1px solid ${C.border};border-radius:6px;background:${C.bg}}
.luna-sl table{width:100%;border-collapse:collapse;table-layout:fixed}
.luna-sl th{position:sticky;top:0;background:${C.panel};color:${C.muted};font-weight:500;text-align:left;padding:0 5px;height:${HEAD_H}px;border-bottom:1px solid ${C.border}}
.luna-sl td{height:${ROW_H - 1}px;padding:0 5px;border-bottom:1px solid ${C.border}55;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.luna-sl tr.cur td{background:${C.accentSoft}}
.luna-sl tr.cur td.n{color:${C.accent};font-weight:600}
.luna-sl td.n{cursor:pointer;color:${C.muted};text-align:right}
.luna-sl td.n:hover{color:${C.accent}}
.luna-sl td.dim{color:${C.muted}}
.luna-sl td input{width:100%;box-sizing:border-box;background:transparent;border:1px solid transparent;border-radius:3px;color:${C.text};font:inherit;padding:1px 3px}
.luna-sl td input:hover{border-color:${C.border}}
.luna-sl td input:focus{outline:none;border-color:${C.accent};background:${C.panel}}
.luna-sl td input.auto{color:${C.muted};font-style:italic}
.luna-sl td.x{cursor:pointer;color:${C.muted};text-align:center}
.luna-sl td.x:hover{color:${C.danger}}
.luna-sl-ft{display:flex;align-items:flex-start;gap:8px;padding-top:5px;min-height:0}
.luna-sl-add{flex:0 0 auto;cursor:pointer;padding:2px 9px;border:1px solid ${C.border};border-radius:4px;color:${C.accent}}
.luna-sl-add:hover{border-color:${C.accent}}
.luna-sl-st{flex:1;color:${C.muted};line-height:1.35}
.luna-sl-st.err{color:${C.danger}}
`;
    document.head.appendChild(s);
}

const signature = (node) => KEYS.map((k) => String(W(node, k)?.value ?? "")).join("\u0001");
const scriptWired = (node) => {
    const inp = node.inputs?.find((i) => i.name === "script");
    return !!inp && inp.link != null;
};

async function refresh(node) {
    const ui = node._lunaSL;
    const sig = signature(node);
    ui.asking = sig;
    let r;
    try {
        const res = await api.fetchApi("/lunasave/shot-list", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ script: String(W(node, "script")?.value ?? ""),
                                   grid: W(node, "grid")?.value, overlap: Number(W(node, "overlap")?.value) || 0 }),
        });
        r = await res.json();
    } catch { r = { error: "could not ask the server" }; }
    if (ui.asking !== sig) return;
    ui.plan = r.error ? null : r;
    ui.error = r.error || "";
    draw(node);
}

function editLine(node, lineNo, text) {
    const w = W(node, "script");
    const lines = String(w.value ?? "").split("\n");
    if (text === null) lines.splice(lineNo, 1); else lines[lineNo] = text;
    w.value = lines.join("\n");
    w.callback?.(w.value);
    node.setDirtyCanvas(true, true);
}

function setScene(node, n) {
    const w = W(node, "scene");
    if (!w) return;
    w.value = n;
    w.callback?.(n);
    node.setDirtyCanvas(true, true);
    draw(node);
}

function draw(node) {
    const ui = node._lunaSL;
    if (!ui) return;
    const plan = ui.plan, wired = scriptWired(node);
    const cur = Number(W(node, "scene")?.value) || 1;
    const editable = !!plan && !wired && plan.scenes.every((s) => s.line != null);
    ui.body.replaceChildren();
    for (const s of plan?.scenes || []) {
        const tr = document.createElement("tr");
        if (s.scene === cur) tr.className = "cur";
        const td = (cls, text) => { const c = document.createElement("td"); if (cls) c.className = cls; if (text != null) c.textContent = text; tr.appendChild(c); return c; };
        const n = td("n", String(s.scene));
        n.title = "Make this the scene the next run makes";
        n.onclick = () => setScene(node, s.scene);
        const field = (value, ph, cls, onSet) => {
            const c = td(), i = document.createElement("input");
            i.value = value;
            i.placeholder = ph;
            if (cls) i.className = cls;
            i.readOnly = !editable;
            i.onchange = () => onSet(i.value);
            i.addEventListener("keydown", (e) => { if (e.key === "Enter") i.blur(); e.stopPropagation(); });
            c.appendChild(i);
            return i;
        };
        // What the line says now, so one cell's edit keeps the other two as written.
        const raw = () => {
            const line = String(W(node, "script")?.value ?? "").split("\n")[s.line] ?? "";
            const [a = "", b = "", ...p] = line.split("|");
            return { start: a.split("#")[0].trim(), length: b.split("#")[0].trim(), prompt: p.join("|").trim() };
        };
        const st = field(s.auto_start ? "" : clock(s.start), clock(s.start), s.auto_start ? "auto" : "",
                         (v) => { const r = raw(); editLine(node, s.line, sceneLine(v, r.length, r.prompt)); });
        st.title = s.auto_start ? `Follows scene ${s.scene - 1}${s.overlap ? `, sharing ${s.overlap} frames` : ""}. Type a time to pin it.` : "Song time this scene starts. Clear it to follow the scene before.";
        td("dim", clock(s.start + s.seconds));
        const ln = field(s.unit === "frames" ? `${s.asked}f` : (s.asked / plan.fps).toFixed(2), "", "",
                         (v) => { const r = raw(); editLine(node, s.line, sceneLine(r.start, v, r.prompt)); });
        ln.title = "Seconds (5.17) or frames (124f)";
        td("dim", `${s.frames}f · ${s.seconds.toFixed(2)}s`).title = s.frames !== s.asked ? `asked ${s.asked} frames, the grid gives ${s.frames}` : "";
        td("dim", s.overlap ? String(s.overlap) : "");
        field(s.prompt, "prompt", "", (v) => { const r = raw(); editLine(node, s.line, sceneLine(r.start, r.length, v)); }).title = s.prompt;
        const x = td("x", editable ? "✕" : "");
        if (editable) { x.title = "Remove this scene"; x.onclick = () => editLine(node, s.line, null); }
        ui.body.appendChild(tr);
    }
    ui.add.hidden = !(editable || (!wired && !plan));
    const st = ui.status;
    st.className = "luna-sl-st" + (ui.error ? " err" : "");
    if (ui.error) st.textContent = `The script: ${ui.error}.`;
    else if (plan) {
        const total = plan.scenes.length, s = plan.scenes[cur - 1];
        st.textContent = `${total} scene${total === 1 ? "" : "s"} at ${plan.fps} fps, song ${clock(Math.min(...plan.scenes.map((x) => x.start)))}–${clock(plan.end)}. `
            + (s ? `This run: scene ${cur}, ${clock(s.start)}–${clock(s.start + s.seconds)}, ${s.frames} frames.`
                 : `Scene ${cur} is past the end — the run will stop.`)
            + (wired ? " The script comes from a wire: shown as written here, edit it at its source." : "")
            + (!editable && !wired ? " A JSON script: edit the text above." : "");
    } else st.textContent = "";
    fit(node);
}

// Arithmetic height (rows x row height), never measured from the layout.
const rowsShown = (node) => Math.max(1, Math.min(MAX_ROWS, node._lunaSL?.plan?.scenes?.length || 1));
const tableHeight = (node) => HEAD_H + rowsShown(node) * ROW_H + 4 + FOOT_H;
function fit(node) {
    const want = node.computeSize()[1];
    if (node.size[1] < want) node.setSize([node.size[0], want]);
    node.setDirtyCanvas(true, true);
}

function buildTable(node) {
    injectCSS();
    const root = document.createElement("div");
    root.className = "luna-sl";
    root.innerHTML = `<div class="luna-sl-tb"><table><colgroup><col style="width:28px"><col style="width:70px"><col style="width:62px"><col style="width:56px"><col style="width:84px"><col style="width:30px"><col><col style="width:22px"></colgroup>
        <thead><tr><th>#</th><th>start</th><th>end</th><th>length</th><th>grid</th><th title="frames shared with the scene before">ovl</th><th>prompt</th><th></th></tr></thead><tbody></tbody></table></div>
        <div class="luna-sl-ft"><span class="luna-sl-add" title="Add a scene after the last one">+ scene</span><span class="luna-sl-st"></span></div>`;
    for (const ev of ["pointerdown", "mousedown", "touchstart"]) root.addEventListener(ev, (e) => e.stopPropagation());
    root.querySelector(".luna-sl-tb").addEventListener("wheel", (e) => e.stopPropagation(), { passive: true });
    const ui = { root, body: root.querySelector("tbody"), add: root.querySelector(".luna-sl-add"),
                 status: root.querySelector(".luna-sl-st"), plan: null, error: "", seen: null, asking: null, timer: 0 };
    ui.add.onclick = () => {
        const w = W(node, "script");
        const text = String(w.value ?? "").replace(/\s+$/, "");
        w.value = `${text}${text ? "\n" : ""}${sceneLine("", "124f", "")}\n`;
        w.callback?.(w.value);
        node.setDirtyCanvas(true, true);
    };
    node._lunaSL = ui;
    const widget = node.addDOMWidget("luna_sl_table", "table", root, {
        serialize: false, hideOnZoom: false, getHeight: () => tableHeight(node),
    });
    widget.serialize = false;
    widget.computeSize = (width) => [width, tableHeight(node)];
}

// The value a wired output carries for the scene picked now, or null when not known
// yet; undefined for an output this does not cover.
function valueOf(node, out) {
    const ui = node._lunaSL;
    if (!["seconds", "song_start", "frames", "scene", "scenes", "overlap"].includes(out)) return undefined;
    if (!ui?.plan || scriptWired(node)) return null;
    const n = Number(W(node, "scene")?.value) || 1, s = ui.plan.scenes[n - 1];
    if (out === "scenes") return ui.plan.scenes.length;
    if (!s) return null;
    return { seconds: s.seconds, song_start: s.start, frames: s.frames, scene: n, overlap: s.overlap }[out];
}

function watch(node) {
    const ui = node._lunaSL;
    if (!ui) return;
    const sig = signature(node) + (scriptWired(node) ? "|w" : "");
    if (sig === ui.seen) return;
    const onlyScene = ui.seen && ui.seen.split("\u0001").slice(0, 3).join() === sig.split("\u0001").slice(0, 3).join()
        && ui.seen.endsWith("|w") === sig.endsWith("|w");
    ui.seen = sig;
    if (onlyScene) { draw(node); return; }   // the scene moved: no need to ask the server
    clearTimeout(ui.timer);
    ui.timer = setTimeout(() => refresh(node), 250);
}

app.registerExtension({
    name: "LunaSaveSimple.ShotList",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== NODE) return;
        const P = nodeType.prototype;

        const onCreated = P.onNodeCreated;
        P.onNodeCreated = function () {
            const r = onCreated?.apply(this, arguments);
            buildTable(this);
            this.lunaValueOf = (out) => valueOf(this, out);
            this.setSize([Math.max(this.size[0], 560), Math.max(this.size[1], this.computeSize()[1])]);
            return r;
        };

        const onDraw = P.onDrawForeground;
        P.onDrawForeground = function () {
            const r = onDraw?.apply(this, arguments);
            watch(this);
            return r;
        };

        const onRemoved = P.onRemoved;
        P.onRemoved = function () {
            clearTimeout(this._lunaSL?.timer);
            return onRemoved?.apply(this, arguments);
        };
    },
});
