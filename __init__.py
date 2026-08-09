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
"""

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .video_nodes import (
    NODE_CLASS_MAPPINGS as _VIDEO_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as _VIDEO_DISPLAY_MAPPINGS,
)
from .asset_loader import (
    NODE_CLASS_MAPPINGS as _LOADER_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as _LOADER_DISPLAY_MAPPINGS,
)

NODE_CLASS_MAPPINGS.update(_VIDEO_CLASS_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(_VIDEO_DISPLAY_MAPPINGS)
NODE_CLASS_MAPPINGS.update(_LOADER_CLASS_MAPPINGS)
NODE_DISPLAY_NAME_MAPPINGS.update(_LOADER_DISPLAY_MAPPINGS)

WEB_DIRECTORY = "./js"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
