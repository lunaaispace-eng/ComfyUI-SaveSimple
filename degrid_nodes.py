"""Luna VAE DeGrid — removes the 2px pixel grid left by the Qwen Image / Wan 2.1 VAEs.

Ported into this pack on 2026-08-28 from the standalone ComfyUI-DeGrid repo
(github.com/lunaaispace-eng/ComfyUI-DeGrid), which is now retired. The grid fix
belongs with the other post-decode / pre-save image tools rather than in a repo
of its own. Class id `VAEDeGrid` and the two image outputs are unchanged, so
saved workflows keep resolving once this pack is installed.

The V3 `io.ComfyNode` wrapper was rewritten as a V1 node to match the rest of
the pack — ComfyUI's loader is either/or (NODE_CLASS_MAPPINGS *or*
comfy_entrypoint, never both), so a V3 node here would have hidden the pack's
other four. The status line that was `ui.PreviewText` is now the built-in
`{"ui": {"text": ...}}` render path (same one core's `PreviewAny` uses), which
needs `OUTPUT_NODE = True`.

Math core is degrid_core.py — pure torch, no ComfyUI imports, testable
standalone. Left untouched in the port.
"""

from __future__ import annotations

import torch

from .degrid_core import degrid, NEGLIGIBLE_AMP

_DESCRIPTION = (
    "Removes the 2px pixel grid left by the Qwen Image / Wan 2.1 VAEs "
    "(Krea2, Qwen Image, Anima...). Wire directly after VAE Decode, before any "
    "sharpening or upscaling.\n\n"
    "Defaults are the zero-config path: leave mode on 'auto' and the node "
    "measures each image and calibrates itself. After a run, the node shows the "
    "measured grid strength, so you can see it did something even if the change "
    "is invisible at normal zoom.\n\n"
    "The removed_grid output shows WHAT was subtracted. The artifact is only "
    "2px, so in 'full frame' view it looks like faint gray noise — that is "
    "correct behavior, not a failure. Switch grid_view to 4x/8x zoom to see the "
    "actual lattice pattern."
)


def _status_line(mode: str, stats: list) -> str:
    s = stats[0]
    amp = s["amp_255"]
    lim = s["limit"]
    src = "auto" if mode == "auto" else "manual"
    if amp < NEGLIGIBLE_AMP * 255.0:
        verdict = f"grid ≈ {amp:.2f}/255 — negligible, image already clean"
    else:
        verdict = f"grid ≈ {amp:.2f}/255 — removed (limit {lim:.3f} {src})"
    line = f"{verdict} · edges protected: {s['clipped_pct']:.1f}%"
    if len(stats) > 1:
        line += f" · batch of {len(stats)} (first shown)"
    return line


class VAEDeGrid:
    DESCRIPTION = _DESCRIPTION
    # Luna/Image, next to Luna Image Precision: neither loads nor saves, it sits
    # mid-chain right after VAE Decode.
    CATEGORY = "Luna/Image"
    FUNCTION = "run"
    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("image", "removed_grid")
    OUTPUT_TOOLTIPS = (
        "The degridded image — same size as the input. Send this onward to "
        "sharpening / upscaling / save.",
        "Visualization of what was subtracted (amplified by grid_gain, centered "
        "on gray). Healthy result: a uniform fine grid / noise texture. If you "
        "can recognize faces or fabric here, the limit is too high. Preview only "
        "— not meant for further processing.",
    )
    OUTPUT_NODE = True
    SEARCH_ALIASES = ["degrid", "notch", "grid artifact", "qwen vae", "krea2", "pixel grid"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "Wire straight from VAE Decode."}),
                "enabled": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Off = the image passes through completely untouched. "
                               "Use it to A/B compare with and without degrid.",
                }),
                "mode": (["auto", "manual"], {
                    "default": "auto",
                    "tooltip": "auto (recommended): measures the grid strength of each "
                               "image and sets the removal limit itself — nothing to "
                               "tune. manual: uses the 'limit' value below instead; use "
                               "it only if auto visibly under- or over-corrects.",
                }),
                "limit": ("FLOAT", {
                    "default": 0.02, "min": 0.0, "max": 0.10, "step": 0.001,
                    "tooltip": "MANUAL MODE ONLY (ignored in auto). Maximum per-pixel "
                               "correction on the 0-1 scale. The VAE grid is usually "
                               "0.005-0.02, so 0.02 is a good start. Too low = grid "
                               "partially survives in contrasty areas. Too high = fine "
                               "2-3px texture (pores, fabric) gets slightly softened.",
                }),
                "grid_gain": ("FLOAT", {
                    "default": 10.0, "min": 1.0, "max": 50.0, "step": 1.0,
                    "tooltip": "Brightness amplification of the removed_grid preview "
                               "ONLY — it never affects the cleaned image. Raise it if "
                               "the preview looks like flat gray and you want to see "
                               "the removed pattern more clearly.",
                }),
                "grid_view": (["full frame", "4x zoom", "8x zoom"], {
                    "default": "4x zoom",
                    "tooltip": "Framing of the removed_grid preview. The artifact is "
                               "only 2px, so 'full frame' aliases into gray noise at "
                               "node-preview size — normal, but hard to read. '4x "
                               "zoom' / '8x zoom' show a magnified center crop where "
                               "the actual 2px lattice is visible. Preview only; the "
                               "cleaned image is never cropped.",
                }),
            }
        }

    def run(self, image, enabled, mode, limit, grid_gain, grid_view):
        if not enabled:
            return {
                "ui": {"text": ("bypassed (enabled = off)",)},
                "result": (image, torch.full_like(image, 0.5)),
            }
        cleaned, vis, stats = degrid(
            image, mode=mode, limit=limit, grid_gain=grid_gain, grid_view=grid_view,
        )
        return {
            "ui": {"text": (_status_line(mode, stats),)},
            "result": (cleaned, vis),
        }


NODE_CLASS_MAPPINGS = {"VAEDeGrid": VAEDeGrid}
NODE_DISPLAY_NAME_MAPPINGS = {"VAEDeGrid": "VAE DeGrid (Nyquist Notch)"}
