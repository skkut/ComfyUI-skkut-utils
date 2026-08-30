# Save Compressed Weppy

Saves images as compressed WebP files (`.webp`) while embedding the ComfyUI prompt and workflow metadata in the EXIF tags — with large binary blobs stripped so the metadata never hits EXIF size limits.

## Overview

| | |
|---|---|
| **Python backend** | `save_compressed_weppy/__init__.py` (HTTP route) + `save_compressed_weppy/save_compressed_weppy.py` (node) |
| **Frontend extension** | `web/save_compressed_weppy.js` |
| **Dependency** | `piexif` (optional — graceful fallback to Pillow's native EXIF writer) |

Two ways to save:

1. **Save Compressed Weppy node** — add the node to a workflow; every image is saved to the ComfyUI `output` directory as `.webp` during execution.
2. **Right-click context menu** — right-click any image preview (e.g. from a preview or output node) and choose **"Save Compressed Weppy"** (inserted right after the native "Save Image" entry) to re-encode it and trigger a browser/OS download.

## Node configuration

Node name: **Save Compressed Weppy** · Category: `image` · Output node (shows images in the UI)

| Input | Type | Default | Description |
|---|---|---|---|
| `images` | `IMAGE` | — | The image tensor(s) to save |
| `filename_prefix` | `STRING` | `ComfyUI_Weppy` | Prefix for saved files (a random 5-letter suffix is appended) |
| `quality` | `INT` | `80` | WebP quality, 1–100. Higher = better quality, larger file |
| `lossless` | `BOOLEAN` | `False` | Use lossless WebP encoding (quality then controls compression level) |
| `prompt` / `extra_pnginfo` | hidden | — | Auto-captured execution prompt and workflow layout |

Each image is saved as `{prefix}_{suffix}_{counter:05}.webp` in the output directory.

## Right-click context menu (backend route)

The context-menu entry sends `POST /save_compressed_weppy` with:

```json
{
  "filename": "…",      // filename from the image preview URL
  "type": "output",     // output | temp | input
  "subfolder": "…",
  "prompt": {…},        // current graph as prompt (optional)
  "workflow": {…}       // current graph layout (optional)
}
```

The server resolves the image via `folder_paths.get_directory_by_type`, re-encodes it as WebP (quality 80, lossy), embeds the metadata, and returns the file as an attachment (`Content-Disposition: attachment`) with a random name like `ComfyUI_Weppy_abcde.webp`. The frontend turns the response into a browser download — in ComfyUI Desktop (or browsers set to ask) this opens the native save dialog.

## Metadata handling

- **`prompt`** is embedded in the EXIF **Make** tag (`prompt:<json>`); **`workflow`** is embedded in the **ImageDescription** tag (`workflow:<json>`), so the workflow can be recovered by drag-and-dropping the `.webp` back into ComfyUI.
- **EXIF size protection**: `strip_binary_from_workflow()` recursively walks the JSON and removes
  - base64 data URIs (`data:…;base64,…`), and
  - any string longer than 10 KB without spaces (typically raw embedded binary data),
  so the metadata stays well under the EXIF size limit and the files stay small.
- **Writer selection**: if `piexif` is installed it is used (`piexif.dump`); otherwise the code falls back to Pillow's native EXIF writer (`Image.getexif()` + tag `0x010f`/`0x010e`).

## Installation

The feature ships as part of the unified `ComfyUI-skkut-utils` repo — see the [root README](../README.md). `piexif` is optional; install it for the primary EXIF path (`pip install piexif` — it is listed in `requirements.txt`). Restart ComfyUI after installing.

## Files

- `save_compressed_weppy/save_compressed_weppy.py` — node implementation and `strip_binary_from_workflow()`.
- `save_compressed_weppy/__init__.py` — registers the node mapping and the `/save_compressed_weppy` route.
- `web/save_compressed_weppy.js` — context-menu extension (extension name `SaveCompressedWeppy.ContextMenu`).
