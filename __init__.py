"""ComfyUI-SaveSimple — a clean, minimal Save Image node.

One node: Save Image (Simple). Prefix, format (png/jpg/webp), optional output
path, quality/dpi, timestamp, preview, and a single yes/no toggle for embedding
the workflow+prompt metadata. Nothing else.
"""

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
