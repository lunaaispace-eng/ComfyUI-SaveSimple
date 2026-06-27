# ComfyUI-SaveSimple

ComfyUI-SaveSimple is a minimal image-saving node for ComfyUI. It keeps the save workflow focused: choose a filename prefix, image format, output folder, quality, DPI, preview behavior, and whether to keep ComfyUI metadata.

The node also supports saving readable positive and negative prompt text beside each image, so you can keep clean prompt records for PNG, JPG, and WEBP outputs.

## Node

| Setting | Value |
| --- | --- |
| Display name | `Save Image (Simple)` |
| Category | `Luna` |
| Internal class | `SaveImageSimple` |
| Output | `file_path` (`STRING`) |

## Features

- Save images as `png`, `jpg`, or `webp`.
- Save to the ComfyUI output folder, a subfolder, or an absolute path.
- Optional ComfyUI preview for files saved under the output folder.
- Optional PNG workflow/prompt metadata for drag-and-drop reloads in ComfyUI.
- Optional readable positive/negative prompt sidecar text files.
- Optional PNG metadata fields for `positive_prompt` and `negative_prompt`.
- JPG/WEBP quality control.
- WEBP lossless mode.
- PNG/JPG DPI control.
- Timestamped filenames.
- Batch image saving with auto-numbered filenames.

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `images` | required | Image or image batch to save. |
| `filename_prefix` | `ComfyUI` | Base filename. Files are auto-numbered, for example `ComfyUI_00001.png`. |
| `format` | `png` | Output format: `png`, `jpg`, or `webp`. |
| `save_metadata` | `yes` | For PNG only, embeds ComfyUI prompt/workflow metadata. Turn off for a clean file. |
| `output_path` | empty | Empty saves to the ComfyUI output folder. Relative paths save to an output subfolder. Absolute paths save directly there. |
| `quality` | `95` | JPG/WEBP quality. |
| `webp_lossless` | `off` | Enables WEBP lossless mode. |
| `dpi` | `96` | PNG/JPG DPI value. |
| `add_timestamp` | `off` | Adds `_YYYYMMDD-HHMMSS` to the filename. |
| `save_prompt_text` | `off` | Saves readable positive and negative prompt text beside each image. |
| `preview` | `on` | Shows saved images in the node when the file is inside the ComfyUI output folder. |

## Outputs

| Output | Type | Description |
| --- | --- | --- |
| `file_path` | `STRING` | Absolute saved image path. For batches, paths are newline-separated. |

## Prompt Text Saving

When `save_prompt_text` is enabled, the node tries to extract positive and negative conditioning text from the ComfyUI prompt graph.

For each image, it writes a sidecar file:

```text
ComfyUI_00001.png
ComfyUI_00001.txt
```

The sidecar file uses this format:

```text
Positive:
your positive prompt

Negative:
your negative prompt
```

For PNG files, if `save_metadata` is also enabled, the same text is embedded as PNG text chunks:

```text
positive_prompt
negative_prompt
```

The full ComfyUI workflow metadata is still saved in the normal `prompt` and extra PNG info fields when `save_metadata` is enabled.

## Filename Behavior

The node generates filenames like:

```text
ComfyUI_00001.png
ComfyUI_00002.png
```

With timestamps enabled:

```text
ComfyUI_20260627-154422_00001.png
```

The counter is based on existing files in the target folder that match the selected prefix.

## Installation

1. Copy this folder into your ComfyUI custom nodes directory:

```text
ComfyUI/custom_nodes/ComfyUI-SaveSimple
```

2. Install dependencies if needed:

```bash
pip install -r requirements.txt
```

3. Restart ComfyUI.
4. Hard-refresh the browser page with `Ctrl+F5`.
5. Add the node from `Luna -> Save Image (Simple)`.

## Dependencies

The node depends on:

- `Pillow`
- `numpy`

ComfyUI normally provides the runtime image tensor and `folder_paths` integration.

## Notes

- PNG metadata is only available for PNG output.
- JPG and WEBP are always saved without ComfyUI workflow metadata.
- The readable `.txt` prompt sidecar works for PNG, JPG, and WEBP.
- If you save to an absolute path outside the ComfyUI output folder, the file is saved correctly, but ComfyUI will not show an in-node preview because it only serves known output folders.
- Prompt extraction is designed for common ComfyUI graphs where sampler nodes receive positive and negative conditioning from `CLIPTextEncode` nodes. Complex workflows with multiple samplers, regional prompting, conditioning merges, or custom conditioning nodes may produce combined or partial prompt text.

## License

Apache License 2.0. See [LICENSE](LICENSE).
