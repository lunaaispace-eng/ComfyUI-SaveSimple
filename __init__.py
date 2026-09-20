"""ComfyUI-SaveSimple — clean, minimal save nodes.

Save Image (Simple): prefix, format (png/jpg/webp), optional output path,
quality/dpi, timestamp, preview, and a single yes/no toggle for embedding the
workflow+prompt metadata. Nothing else.

Save Video Simple: an IMAGE batch to a video file, with the same prompt-sidecar
idea applied to video. Derived from ComfyUI-DaSiWa-Nodes under Apache-2.0 — see
the header of video_nodes.py for the attribution and the list of changes.

Luna Asset Loader: one ordered set of reference images feeding both the MiniMax
H3 reference sockets (each at its original size) and the prompt writers (as a
conformed batch), so a picture is loaded once instead of once per consumer.

Luna H3 Reference Loader: all four of MiniMax H3's reference families — pictures,
clips, clip soundtracks, standalone audio — picked from dropdowns with upload
buttons, and handed on as one `refs` link. The Asset Loader is unchanged; this is
its full-fat sibling for graphs that reference video and sound as well as stills.

Luna H3 Refs Out: turns that one `refs` link back into every H3 reference socket,
so the loader can sit anywhere on the canvas behind a single wire.

Luna Image Precision: casts an IMAGE batch to fp16 or fp32, to halve what a long
frame batch costs downstream in a node that sizes its output from the input dtype.

VAE DeGrid: removes the 2px pixel grid the Qwen Image / Qwen Image 2.1 / Wan 2.1
VAEs leave on decoded images. Wire straight after VAE Decode. Ported here
2026-08-28 from the standalone ComfyUI-DeGrid repo; math core is degrid_core.py.
That repo was un-retired on 2026-09-20 and is live again, so the same node id now
exists in two installable packs — see _standalone_degrid() below, which makes
this pack stand down rather than let the two fight over the id.
"""

import os

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .video_nodes import (
    NODE_CLASS_MAPPINGS as _VIDEO_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as _VIDEO_DISPLAY_MAPPINGS,
)
from .asset_loader import (
    NODE_CLASS_MAPPINGS as _LOADER_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as _LOADER_DISPLAY_MAPPINGS,
)
from .image_precision import (
    NODE_CLASS_MAPPINGS as _PRECISION_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as _PRECISION_DISPLAY_MAPPINGS,
)
from .degrid_nodes import (
    NODE_CLASS_MAPPINGS as _DEGRID_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as _DEGRID_DISPLAY_MAPPINGS,
)
from .h3_reference_loader import (
    NODE_CLASS_MAPPINGS as _H3LOADER_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as _H3LOADER_DISPLAY_MAPPINGS,
)
from .h3_refs_out import (
    NODE_CLASS_MAPPINGS as _REFSOUT_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as _REFSOUT_DISPLAY_MAPPINGS,
)

NODE_CLASS_MAPPINGS.update(_VIDEO_CLASS_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(_VIDEO_DISPLAY_MAPPINGS)
NODE_CLASS_MAPPINGS.update(_LOADER_CLASS_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(_LOADER_DISPLAY_MAPPINGS)
NODE_CLASS_MAPPINGS.update(_PRECISION_CLASS_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(_PRECISION_DISPLAY_MAPPINGS)

def _standalone_degrid():
    """Path of a separately installed ComfyUI-DeGrid pack, or None.

    That pack registers the same node id, `VAEDeGrid`. Two packs claiming one id
    means whichever loads last silently wins, and a saved workflow then resolves
    to whichever copy that happened to be — so this pack stands down instead.
    Only THIS side yields; the standalone always registers, otherwise both could
    defer and the node would vanish.

    Matched by content (a sibling folder carrying degrid_core.py) rather than by
    name, because a ZIP install lands as ComfyUI-DeGrid-main.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    parent, me = os.path.dirname(here), os.path.basename(here)
    try:
        names = os.listdir(parent)
    except OSError:
        return None
    for name in names:
        if name == me:
            continue
        p = os.path.join(parent, name)
        if os.path.isfile(os.path.join(p, "degrid_core.py")):
            return p
    return None


_DEGRID_ELSEWHERE = _standalone_degrid()
if _DEGRID_ELSEWHERE:
    print(
        "[ComfyUI-SaveSimple] VAE DeGrid not registered here: the standalone pack at "
        f"{_DEGRID_ELSEWHERE} already provides the same node id 'VAEDeGrid'. "
        "Both ship the same node, so this one stands down. Delete one of the two "
        "folders to silence this."
    )
else:
    NODE_CLASS_MAPPINGS.update(_DEGRID_CLASS_MAPPINGS)
    NODE_DISPLAY_NAME_MAPPINGS.update(_DEGRID_DISPLAY_MAPPINGS)
NODE_CLASS_MAPPINGS.update(_H3LOADER_CLASS_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(_H3LOADER_DISPLAY_MAPPINGS)
NODE_CLASS_MAPPINGS.update(_REFSOUT_CLASS_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(_REFSOUT_DISPLAY_MAPPINGS)

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
