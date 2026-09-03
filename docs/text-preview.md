# Skutils Text Preview

A text display node that **keeps the text it shows inside the saved workflow JSON** — the one thing the built-in display-only text-preview nodes (e.g. core *Preview as Text*) don't do. Connect any `STRING` into it, run the workflow, save — the text is right there in the `.json`. Load the workflow later and the text is back on the node, with no re-run and no external file.

## Overview

| | |
|---|---|
| **Python backend** | `text_preview/__init__.py` (node mapping) + `text_preview/text_preview.py` (node) |
| **Frontend extension** | `web/text_preview.js` (writes the executed text into the widget) |
| **Dependency** | none beyond ComfyUI itself |

Node name: **Skutils Text Preview** · Category: `utils/text`

## Node configuration

| Input | Type | Default | Description |
|---|---|---|---|
| `text` | STRING (input port) | — | Text to display — connect any upstream `STRING` output, e.g. a prompt builder, a text parser, or another node's result |

The node has **no outputs** — it is a terminal display node (`OUTPUT_NODE`). The text it displayed on its last run is shown in a read-only text area in the node body, and that same text is what gets saved.

## How it works

The trick is *where* the text lives. ComfyUI persists **widget values** into the workflow JSON when you save (Ctrl+S / File → Save), and restores them when you load. The built-in text-preview nodes never use that: their display widgets are marked `serialize: false` and are only filled from the ephemeral execution output — so they show text while the app is open and forget it the moment you save or switch workflows.

**Skutils Text Preview** instead keeps the text in a regular, serialized `text` widget:

```
                    ┌───────────────────────────────────────────────┐
 upstream STRING ──►│  Skutils Text Preview                         │
                    │                                               │
                    │  ┌─────────────────────────────────────────┐  │
                    │  │  text  (serialized read-only widget)    │  │
                    │  │  "the executed text lives here"         │  │
                    │  └─────────────────────────────────────────┘  │
                    └───────────────────────────────────────────────┘
                         │  web/text_preview.js creates that widget
                         │  and fills it with the executed text
                         ▼
              workflow JSON save: text is in the file
```

1. **Connect a STRING** into the `text` port (the node takes no typed input, same as the built-in "Preview as Text").
2. On each run the backend returns the executed text as a UI output.
3. The frontend extension `web/text_preview.js` creates a real, serialized multiline widget in the node body and writes the text into it.
4. When you **save the workflow**, that widget value is serialized into the JSON, so the displayed text is stored *inside* the workflow file itself.
5. When you **load the workflow**, the extension rebuilds the widget from the stored value — the text is displayed again immediately, cached runs included, no execution needed.

The display widget is **read-only**: its value is always the text that was executed (or the text that was saved with the workflow), so what you see is exactly what the JSON contains.

### What is and isn't stored

| Place | Stored? | Why |
|---|---|---|
| Workflow JSON from **File → Save / Ctrl+S** (the usual `.json`) | ✅ | Widget values are serialized into it |
| Workflow JSON embedded in images by save nodes (incl. [Save Compressed Weppy](save-compressed-weppy.md)) | ✅ | Same UI workflow document, embedded as metadata — drag the image back and the text returns |
| **Save (API format)** JSON | ❌ | That format stores only the executable graph (links/inputs), never widget values — same limitation as *every* node's widgets (seeds, prompts, …) |
| Text that only ever ran headless (CLI `--prompt`, no browser open) | ❌ | Nothing is shown, so nothing can be copied into the widget |

## Example

1. Add a **Skutils Text Preview** node.
2. Connect the `STRING` output of a text node into its `text` port.
3. Run the workflow once — the executed text appears in the read-only text area inside the node.
4. **Ctrl+S** and reopen the workflow: the text is still displayed, even if you never run it again.

## Files

- `text_preview/text_preview.py` — node implementation: port-only `text` input (STRING, `forceInput`), returns `{"ui": {"text": [...]}}`.
- `text_preview/__init__.py` — registers the node mapping.
- `web/text_preview.js` — frontend extension that creates the serialized display widget, fills it from `onExecuted`, and rebuilds it from stored values on `configure`/`onConfigure`.

## Installation

The feature ships as part of the unified `ComfyUI-skkut-utils` repo — see the [root README](../README.md). Restart ComfyUI after installing.
