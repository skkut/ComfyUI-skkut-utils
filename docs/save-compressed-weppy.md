# Save Compressed Weppy

Saves images as compressed WebP files (`.webp`) while embedding the ComfyUI prompt and workflow metadata in the EXIF tags — with large binary blobs stripped so the metadata never hits EXIF size limits.

## Overview

| | |
|---|---|
| **Python backend** | `save_compressed_weppy/__init__.py` (HTTP route) + `save_compressed_weppy/save_compressed_weppy.py` (node) + `save_compressed_weppy/download_name.py` (download naming) |
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

The server resolves the image via `folder_paths.get_directory_by_type`, re-encodes it as WebP (quality 80, lossy), embeds the metadata, and returns the file as an attachment (`Content-Disposition: attachment`). The frontend turns the response into a browser download — in ComfyUI Desktop (or browsers set to ask) this opens the native save dialog.

### Download filename

The context menu can only send what the browser already holds: the image it was opened on, plus the current graph serialised as an API prompt. It cannot send any node's *computed* output — core only emits the `executed` websocket event for nodes that return ui data, so a node whose output is a plain `STRING` never publishes its value to the frontend. The menu has nothing to read, even when a node already computes a filename.

The name is therefore derived **server-side from the prompt**, which does carry the widget values. `download_name.py` holds one small reader per supported node class in `NAME_PROVIDERS`:

| Node class | Name taken from |
|---|---|
| `OrexStyleSelector` (OreX) | The selected style's `thumbnail` basename — the same string the node's own `file_name` output carries |
| `ClioStyle` / `ClioStyleEncode` (Clio Style Library) | The `style` dropdown selection, as `Krea2/<style name>` — the same string the node's own `filename_prefix` output carries |

The reader mirrors the node's own rule rather than re-inventing one. Note that the Clio name is *not* a slug of the OreX style: the two packs share no style vocabulary, and OreX's thumbnail name is not always a slug of its style name either — `emotions` uses `__Happiness`, `Klein_Edit` uses `_Make_Photo_1` — which is why the style file is read rather than the name slugified.

**Clio details.** The pack writes `Krea2/<style name>` into its `filename_prefix`, keeping the style name's own punctuation, so `Cover Art` becomes `Krea2_Cover_Art_<suffix>.webp` (the `/` is flattened like any other separator). Two cases collapse to `Krea2/unstyled`, matching the node: the `✨ none` dropdown entry, and a style that no longer has a paragraph in the pack's `styles.json` — which Clio re-reads on every call, so entries can vanish without a ComfyUI restart. If that file cannot be read at all, the style is assumed to exist rather than renaming every save to `unstyled`.

The response is named `<name>_<5 random letters>.webp` (e.g. `collage_kzqrv.webp`); a graph with no supported node keeps the default `ComfyUI_Weppy_<5 random letters>.webp`. The random suffix is retained so repeated saves never collide or overwrite silently.

Resolution is best-effort and never fails a save: a missing pack, an unreadable or unrecognised style set, or an unknown selection all fall back to the default prefix. Derived names are flattened to `[A-Za-z0-9._-]` before reaching the header (so `__Happiness` becomes `Happiness`), and a style-set name taken from the prompt is validated before it is used to build a path.

A `style` input that arrives as a *link* (the widget converted to an input socket) yields nothing — the linked value is not in the prompt — so the name falls through to another supported node or the default. The same applies to any reader whose inputs are all linked.

To teach the menu about another pack's filename output, add an entry to `NAME_PROVIDERS` — the readers are plain `inputs -> str | None` functions.

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
- `save_compressed_weppy/download_name.py` — download filename policy: `NAME_PROVIDERS`, the OreX and Clio style readers, the style-catalog lookups, and `safe_slug()`.
- `save_compressed_weppy/__init__.py` — registers the node mapping and the `/save_compressed_weppy` route.
- `web/save_compressed_weppy.js` — context-menu extension (extension name `SaveCompressedWeppy.ContextMenu`).
