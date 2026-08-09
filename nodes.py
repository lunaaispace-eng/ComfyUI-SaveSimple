"""Save Image (Simple) — a no-nonsense save node.

Just the essentials: prefix, format, optional path, quality/dpi, a timestamp
toggle, preview, and a single yes/no for embedding the workflow+prompt metadata.
No history browsers, no blind watermarks, no clutter.
"""

from __future__ import annotations

import json
import os
import re
import time

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

try:
    import folder_paths  # provided by ComfyUI
except Exception:  # pragma: no cover - lets the file import/test outside ComfyUI
    folder_paths = None


def _default_output_dir() -> str:
    if folder_paths is not None:
        try:
            return folder_paths.get_output_directory()
        except Exception:
            pass
    return os.path.join(os.getcwd(), "output")


def _sanitize_prefix(prefix: str) -> str:
    prefix = (prefix or "").strip() or "ComfyUI"
    # keep it a filename, not a path
    return os.path.basename(prefix.replace("\\", "/").rstrip("/")) or "ComfyUI"


def _prompt_node(prompt, node_id):
    if not isinstance(prompt, dict) or node_id is None:
        return None
    return prompt.get(str(node_id)) or prompt.get(node_id)


def _link_node_id(value):
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return None


# input keys that commonly hold prompt text on encode / text / primitive nodes
_TEXT_KEYS = ("text", "text_g", "text_l", "string", "prompt",
              "value", "populated_text", "wildcard_text")


def _collect_conditioning_text(prompt, start_value):
    texts = []
    seen = set()

    def add_text(text):
        text = text.strip()
        if text and text not in texts:
            texts.append(text)

    def walk(value):
        node_id = _link_node_id(value) if isinstance(value, (list, tuple)) else value
        node_id = str(node_id) if node_id is not None else None
        if not node_id or node_id in seen:
            return
        seen.add(node_id)

        node = _prompt_node(prompt, node_id)
        if not isinstance(node, dict):
            return

        inputs = node.get("inputs", {})
        if isinstance(inputs, dict):
            # Grab any literal text held in a known text-bearing key. Key-name
            # filtering keeps us from pulling in ckpt names, seeds, etc.
            for key in _TEXT_KEYS:
                if isinstance(inputs.get(key), str):
                    add_text(inputs[key])
            # Follow every linked child so a wired `text` input is traced back to
            # the primitive / node that actually holds the literal string.
            for child in inputs.values():
                child_id = _link_node_id(child)
                if child_id is not None:
                    walk(child_id)

    walk(start_value)
    return "\n\n".join(texts)


def _extract_prompt_text(prompt):
    positive_texts = []
    negative_texts = []

    def add_unique(target, text):
        if text and text not in target:
            target.append(text)

    if isinstance(prompt, dict):
        for node in prompt.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs", {})
            if not isinstance(inputs, dict):
                continue
            if "positive" in inputs:
                add_unique(positive_texts, _collect_conditioning_text(prompt, inputs["positive"]))
            if "negative" in inputs:
                add_unique(negative_texts, _collect_conditioning_text(prompt, inputs["negative"]))

    return "\n\n".join(positive_texts), "\n\n".join(negative_texts)


def _write_prompt_sidecar(image_path, positive_prompt, negative_prompt):
    prompt_path = os.path.splitext(image_path)[0] + ".txt"
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write("Positive:\n")
        f.write(positive_prompt or "")
        f.write("\n\nNegative:\n")
        f.write(negative_prompt or "")
        f.write("\n")
    return prompt_path


class SaveImageSimple:
    # Luna/Save, beside Save Video Simple. Changing CATEGORY moves the node in the
    # add-node menu only — the node type is the class name, so existing workflows
    # are unaffected.
    CATEGORY = "Luna/Save"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("file_path",)
    FUNCTION = "save"
    OUTPUT_NODE = True
    DESCRIPTION = "Simple image saver with an optional metadata (workflow+prompt) toggle."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "ComfyUI"}),
                "format": (["png", "jpg", "webp"],),
                "save_metadata": ("BOOLEAN", {
                    "default": True, "label_on": "yes", "label_off": "no",
                    "tooltip": "Embed the workflow + prompt so the image can be dragged "
                               "back into ComfyUI. PNG only. Off = clean file."}),
            },
            "optional": {
                "output_path": ("STRING", {
                    "default": "",
                    "tooltip": "Empty = ComfyUI output folder. A relative name = subfolder. "
                               "An absolute path = save there."}),
                "quality": ("INT", {"default": 95, "min": 1, "max": 100,
                                    "tooltip": "JPG / WEBP only."}),
                "webp_lossless": ("BOOLEAN", {"default": False,
                                  "tooltip": "WEBP only: save lossless (quality acts as "
                                             "compression effort)."}),
                "dpi": ("INT", {"default": 96, "min": 1, "max": 2400}),
                "add_timestamp": ("BOOLEAN", {"default": False}),
                "save_prompt_text": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Save readable positive/negative prompt text beside each image."}),
                "positive_prompt": ("STRING", {
                    "default": "", "forceInput": True,
                    "tooltip": "Optional: wire the actual positive prompt here (e.g. from the "
                               "LLM node). Overrides auto-extraction. Needed for LLM-generated "
                               "prompts, which aren't recoverable from the workflow graph."}),
                "negative_prompt": ("STRING", {
                    "default": "", "forceInput": True,
                    "tooltip": "Optional: wire the actual negative prompt here. Overrides "
                               "auto-extraction."}),
                "preview": ("BOOLEAN", {"default": True}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    # always run (output node)
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def save(self, images, filename_prefix, format, save_metadata,
             output_path="", quality=95, webp_lossless=False, dpi=96,
             add_timestamp=False, save_prompt_text=False,
             positive_prompt="", negative_prompt="", preview=True,
             prompt=None, extra_pnginfo=None):
        prefix = _sanitize_prefix(filename_prefix)
        out_dir = _default_output_dir()
        pos, neg = ("", "")
        if save_prompt_text:
            # Positive: auto-extract from the graph as a fallback, but a wired
            # input (e.g. live LLM output) always wins.
            pos, _ = _extract_prompt_text(prompt)
            if positive_prompt.strip():
                pos = positive_prompt
            # Negative: only ever what's explicitly wired in. No graph fallback,
            # so a static "watermark" encode you don't care about stays out.
            if negative_prompt.strip():
                neg = negative_prompt

        # resolve target directory + whether it's inside the output dir (for preview)
        if output_path.strip():
            if os.path.isabs(output_path):
                target_dir = output_path
                subfolder = ""
                under_output = self._is_under(target_dir, out_dir)
            else:
                target_dir = os.path.join(out_dir, output_path)
                subfolder = output_path.replace("\\", "/").strip("/")
                under_output = True
        else:
            target_dir = out_dir
            subfolder = ""
            under_output = True
        os.makedirs(target_dir, exist_ok=True)

        ext = format
        ts = time.strftime("_%Y%m%d-%H%M%S") if add_timestamp else ""
        counter = self._next_counter(target_dir, prefix)

        results = []
        saved_paths = []
        for image in images:
            arr = (255.0 * np.asarray(image.cpu().numpy())).clip(0, 255).astype(np.uint8)
            pil = Image.fromarray(arr)
            fname = f"{prefix}{ts}_{counter:05d}.{ext}"
            fpath = os.path.join(target_dir, fname)

            if format == "png":
                pnginfo = None
                if save_metadata:
                    pnginfo = PngInfo()
                    if prompt is not None:
                        pnginfo.add_text("prompt", json.dumps(prompt))
                    if extra_pnginfo:
                        for k, v in extra_pnginfo.items():
                            pnginfo.add_text(k, json.dumps(v))
                    if save_prompt_text:
                        if pos:
                            pnginfo.add_text("positive_prompt", pos)
                        if neg:
                            pnginfo.add_text("negative_prompt", neg)
                pil.save(fpath, pnginfo=pnginfo, compress_level=4, dpi=(dpi, dpi))
            elif format == "jpg":
                pil.convert("RGB").save(fpath, quality=int(quality), dpi=(dpi, dpi))
            else:  # webp
                pil.save(fpath, quality=int(quality), lossless=bool(webp_lossless))

            if save_prompt_text:
                _write_prompt_sidecar(fpath, pos, neg)

            saved_paths.append(os.path.abspath(fpath))
            counter += 1
            if preview and under_output:
                results.append({"filename": fname, "subfolder": subfolder, "type": "output"})

        return {"ui": {"images": results}, "result": ("\n".join(saved_paths),)}

    @staticmethod
    def _is_under(path: str, parent: str) -> bool:
        try:
            return os.path.commonpath([os.path.abspath(path), os.path.abspath(parent)]) == os.path.abspath(parent)
        except Exception:
            return False

    @staticmethod
    def _next_counter(target_dir: str, prefix: str) -> int:
        mx = 0
        pat = re.compile(re.escape(prefix) + r".*?_(\d+)\.\w+$")
        try:
            for f in os.listdir(target_dir):
                m = pat.match(f)
                if m:
                    mx = max(mx, int(m.group(1)))
        except Exception:
            pass
        return mx + 1


NODE_CLASS_MAPPINGS = {"SaveImageSimple": SaveImageSimple}
NODE_DISPLAY_NAME_MAPPINGS = {"SaveImageSimple": "Save Image (Simple)"}
