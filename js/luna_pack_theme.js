// Applies the Luna house theme to this pack's nodes.
//
// Roles come from the section tints in luna_theme.mjs: a loader is an input, the
// save nodes are outputs. One line per node — copy this file into another pack
// and change the map.

import { app } from "../../scripts/app.js";
import { registerLunaTheme } from "./luna_theme.mjs";
import { registerLunaHelp } from "./luna_help.mjs";
import { registerLunaCollapse } from "./luna_collapse.mjs";

// Title-bar tinting is off for now — Peti prefers ComfyUI's default red header,
// with the widget's own amber/green palette inside. The role map stays here so
// turning it back on is uncommenting one call; the colours are also editable in
// Settings > Luna > Node colours.
//
// registerLunaTheme(app, {
//     LunaAssetLoader: "input",
//     SaveImageSimple: "output",
//     SaveVideoSimple: "output",
// }, "LunaSaveSimple.Theme");

// The ⓘ on the title bar. Content is each node's Python DESCRIPTION plus its
// input tooltips, so there is no separate help file to keep up to date.
registerLunaHelp(app, ["LunaAssetLoader", "SaveImageSimple", "SaveVideoSimple", "LunaImagePrecision", "VAEDeGrid", "LunaH3ReferenceLoader", "LunaH3RefsOut"], "LunaSaveSimple.Help");

// The chevron beside it folds the settings away, leaving sockets and whatever the
// node draws for itself — Save Image keeps its preview, Save Video keeps the
// player, the frame checkboxes, Autoplay and Download. The Asset Loader is not
// listed: it is cards rather than settings, so there is little to fold.
//
// The H3 Reference Loader is listed because it is nothing BUT settings — 27 stock
// widgets, 9 of them picture slots that are usually left on (none). Folding it
// leaves the five sockets, which is all a wired graph needs to show. It is a
// stopgap: the node deserves the Asset Loader's card treatment, and the chevron
// only hides the problem rather than solving it.
registerLunaCollapse(app, ["SaveImageSimple", "SaveVideoSimple", "LunaH3ReferenceLoader"], "LunaSaveSimple.Collapse");
