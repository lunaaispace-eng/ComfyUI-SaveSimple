"""Luna H3 Refs Out — one wire in, every MiniMax H3 reference socket out.

The Luna Asset Loader already knows what each thing it loaded is and what number
the model will give it. Carrying that across the canvas as eighteen wires throws
that knowledge away and makes you re-establish it by hand every time the loader
moves. This node takes the loader's single `refs` output and fans it back out
into sockets named exactly like H3's own, so the wiring is mechanical.

Deliberately NOT a generic bundle. The pattern this is modelled on
(PlagueKind's Bundle In / Bundle Out) uses `"*"` wildcard sockets on both ends
and maps them positionally, which works but throws type checking away with it —
nothing stops an AUDIO landing in `ref_image_3`, and nothing complains until the
sampler does. Here the payload's shape is known, so every socket carries its
real type and a mis-wire is refused by the frontend.

There is no Bundle In: the Asset Loader IS the bundle in. A second node to
assemble what one node already assembled would only add a place for the order to
go wrong.

Socket names are 0-based to match H3's (`ref_image_0`), while the prompt tags in
`asset_brief` are 1-based (`<Picture 1>`), because that is H3's own
inconsistency — its Autogrow sockets count from 0 and its tokenizer counts from
1. Absorbing it here is better than renumbering silently and having the brief
disagree with the graph.
"""

from __future__ import annotations

MAX_IMAGES = 9
MAX_VIDEOS = 3
MAX_AUDIOS = 3


def _slot(items, i):
    """Item i, or None when fewer were loaded. Never a black frame — an empty
    socket leaves H3's Autogrow slot unconnected, which is what "not supplied"
    means; a zero tensor would be a silent black reference."""
    if not items or i >= len(items):
        return None
    return items[i]


class LunaH3RefsOut:
    DESCRIPTION = (
        "Unpacks the Luna Asset Loader's `refs` output into every MiniMax H3 reference "
        "socket. Park it beside the H3 node and the loader stays one wire away, wherever "
        "you move it. Socket names match H3's own, so each one drags straight across. "
        "Sockets past what was loaded stay empty."
    )
    CATEGORY = "Luna/Load"
    FUNCTION = "unpack"

    RETURN_TYPES = (
        ("IMAGE",) * MAX_IMAGES
        + ("IMAGE",) * MAX_VIDEOS
        + ("AUDIO",) * MAX_VIDEOS
        + ("AUDIO",) * MAX_AUDIOS
        + ("STRING",)
    )
    RETURN_NAMES = (
        tuple(f"ref_image_{i}" for i in range(MAX_IMAGES))
        + tuple(f"ref_video_{i}" for i in range(MAX_VIDEOS))
        + tuple(f"ref_video_audio_{i}" for i in range(MAX_VIDEOS))
        + tuple(f"ref_audio_{i}" for i in range(MAX_AUDIOS))
        + ("asset_brief",)
    )
    OUTPUT_TOOLTIPS = (
        tuple(
            f"Picture {i + 1} at its original size, for H3's ref_image_{i} socket."
            for i in range(MAX_IMAGES)
        )
        + tuple(
            f"Video {i + 1} as a 24 fps frame batch on H3's 17k+5 grid, for ref_video_{i}."
            for i in range(MAX_VIDEOS)
        )
        + tuple(
            f"The soundtrack of video {i + 1}, trimmed to the same window, for "
            f"ref_video_audio_{i}. Empty if that clip had no audio or none was wanted."
            for i in range(MAX_VIDEOS)
        )
        + tuple(
            f"Standalone reference audio {i + 1}, for ref_audio_{i}."
            for i in range(MAX_AUDIOS)
        )
        + (
            "The same inventory string the loader produced, repeated here so the prompt "
            "writer can be fed from beside the H3 node instead of from across the canvas.",
        )
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "refs": ("LUNA_H3_REFS", {
                    "tooltip": "The `refs` output of Luna Asset Loader.",
                }),
            },
        }

    def unpack(self, refs):
        refs = refs if isinstance(refs, dict) else {}
        images = refs.get("images") or []
        videos = refs.get("videos") or []
        video_audios = refs.get("video_audios") or []
        audios = refs.get("audios") or []
        return (
            tuple(_slot(images, i) for i in range(MAX_IMAGES))
            + tuple(_slot(videos, i) for i in range(MAX_VIDEOS))
            + tuple(_slot(video_audios, i) for i in range(MAX_VIDEOS))
            + tuple(_slot(audios, i) for i in range(MAX_AUDIOS))
            + (refs.get("brief", ""),)
        )


NODE_CLASS_MAPPINGS = {"LunaH3RefsOut": LunaH3RefsOut}
NODE_DISPLAY_NAME_MAPPINGS = {"LunaH3RefsOut": "Luna H3 Refs Out"}
