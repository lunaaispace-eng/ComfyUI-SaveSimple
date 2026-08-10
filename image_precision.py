"""Luna Image Precision — cast an IMAGE batch between fp32 and fp16.

One knob, one purpose: halve what a long frame batch costs in RAM before it
reaches a node that sizes its own output buffer from the input dtype.

The case this was written for. `(Deno) RTX Video Super Resolution (2 Pass)`
takes `out_dtype = images.dtype` and preallocates `[batch, h, w, 3]` in it, so a
2688x1536 frame costs 49.5 MB in fp32 and 24.7 MB in fp16 — over a 247-frame
interpolated clip that is 12.2 GB against 6.1 GB. GIMM-VFI cannot supply the
fp16: `interpolate()` ends with `.cpu().float()`, which discards whatever its own
`precision` widget ran at. This node is the only place to change it.

fp16 holds ~11 bits across the 0-1 range, comfortably more than the 8- or 10-bit
video at the far end. What changes is the dtype the batch is *stored* in, not the
precision anything computes in — nodes that need fp32 internally still cast up.

Worth knowing before wiring one in: ComfyUI caches every node's output for the
duration of a run, so the fp32 batch upstream does not disappear when you cast.
The saving lands on what the *downstream* node allocates, minus the cost of the
fp16 copy itself.
"""

from __future__ import annotations

import torch

_DTYPES = {"fp16": torch.float16, "fp32": torch.float32}


def _size(tensor) -> str:
    """Bytes as GB or MB — a still image batch in GB is a row of zeroes."""
    mb = tensor.element_size() * tensor.nelement() / 1024 ** 2
    return f"{mb / 1024:.2f} GB" if mb >= 1024 else f"{mb:.0f} MB"


class LunaImagePrecision:
    DESCRIPTION = (
        "Cast an IMAGE batch to fp16 or fp32.\n\n"
        "fp16 halves what the batch occupies in RAM, which matters when the next "
        "node preallocates its output buffer from the input dtype. No visible "
        "quality cost for 8- or 10-bit video output — fp16 keeps ~11 bits across "
        "the 0-1 range.\n\n"
        "Place it immediately before the node whose buffer you want to shrink."
    )

    # Luna/Image rather than Luna/Save: this one neither loads nor saves, it sits
    # mid-chain. See CATEGORY in nodes.py for how the section tints read it.
    CATEGORY = "Luna/Image"
    FUNCTION = "cast"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "The batch to cast."}),
                "precision": (list(_DTYPES), {
                    "default": "fp16",
                    "tooltip": "fp16 halves the memory the batch occupies. "
                               "fp32 casts back, for a node that will not take fp16.",
                }),
            }
        }

    def cast(self, images, precision):
        target = _DTYPES[precision]

        if images.dtype == target:
            # Same tensor out, not a copy — nothing to gain and a whole batch to lose.
            print(f"[Luna Image Precision] already {precision}, passed through.")
            return (images,)

        before = _size(images)
        out = images.to(target)
        source = str(images.dtype).replace("torch.", "")
        print(f"[Luna Image Precision] {images.shape[0]} frame(s) {source} -> {precision}: "
              f"{before} -> {_size(out)}")
        return (out,)


NODE_CLASS_MAPPINGS = {"LunaImagePrecision": LunaImagePrecision}
NODE_DISPLAY_NAME_MAPPINGS = {"LunaImagePrecision": "Luna Image Precision"}
