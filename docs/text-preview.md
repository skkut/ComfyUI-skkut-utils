# Skutils Text Preview

A display node that **keeps the text it shows inside the saved workflow JSON** — the one thing the built-in display-only text-preview nodes (e.g. core *Preview as Text*) don't do. Connect **any output** into it (text, boolean, number, image, latent, dict, …), run the workflow, save — the converted text is right there in the `.json`. Load the workflow later and the text is back on the node, with no re-run and no external file.

## Overview

| | |
|---|---|
| **Python backend** | `text_preview/__init__.py` (node mapping) + `text_preview/text_preview.py` (node) |
| **Frontend extension** | `web/text_preview.js` (writes the executed text into the widget) |
| **Dependency** | none beyond ComfyUI itself |

Node name: **Skutils Text Preview** · Category: `skkut-utils` (Nodes → Extensions → skkut-utils)

## Node configuration

| Input | Type | Default | Description |
|---|---|---|---|
| `text` | wildcard `*` (input port, **optional**) | unconnected | Value to display — connect **any** upstream output: a string, a boolean, a number, an image/latent tensor, a dict, etc. The value is converted to text (see [how values are converted](#how-values-are-converted)). If left unconnected (or fed an empty string), the next run clears the preview |

| Output | Type | Description |
|---|---|---|
| `text` | `STRING` | The same converted text that is displayed (and stored), so one or more downstream nodes can consume it — e.g. **Save Compressed Weppy**'s `enhanced_prompt` input to embed the corresponding prompt in each saved image. In a batch run the output is one string per execution, in the same order as the incoming list; an unconnected input outputs `""` |

### How values are converted

The backend converts whatever arrives at the `text` port before showing or storing it, so non-string outputs such as a boolean preview correctly:

| Connected value | Shown as |
|---|---|
| `STRING` | The text itself, unchanged |
| `BOOLEAN` | `True` / `False` |
| `INT`, `FLOAT` | The number as text (`42`, `3.5`) |
| `None` | The preview is cleared (same as unconnected) |
| `IMAGE`, `MASK`, `LATENT` (torch tensors, numpy arrays) | A compact summary instead of a value dump, e.g. `Tensor(shape=(1, 1024, 1024, 3), dtype=torch.float32, device=cuda:0)`; arrays nested inside dicts (e.g. a `LATENT`'s `samples`) are summarised the same way |
| `dict`, `list`, `tuple`, `set` | Pretty-printed Python-style text, with arrays summarised, at most 200 items per container, nesting limited to 6 levels (larger containers end with a `more items omitted` marker) |
| Anything else (model, clip, custom object, …) | Its `repr()`, truncated to 2,000 characters |

Strings are displayed in full and are never truncated or summarised. The caps above exist so that a preview of a large tensor or nested structure cannot bloat the workflow JSON that stores the displayed text.

The node has **no outputs** — it is a terminal display node (`OUTPUT_NODE`). The text it displayed on its last run is shown in a read-only text area in the node body, and that same text is what gets saved.

Because `text` is optional, the node can sit on a branch whose text may not always exist without blocking the whole workflow from queueing. A run that receives no text clears the display instead of keeping a stale preview from an earlier run.

## How it works

The trick is *where* the text lives. ComfyUI persists **widget values** into the workflow JSON when you save (Ctrl+S / File → Save), and restores them when you load. The built-in text-preview nodes never use that: their display widgets are marked `serialize: false` and are only filled from the ephemeral execution output — so they show text while the app is open and forget it the moment you save or switch workflows.

**Skutils Text Preview** instead keeps the text in a regular, serialized `text` widget:

```
                    ┌───────────────────────────────────────────────┐
 upstream ANY    ──►│  Skutils Text Preview                         │
                    │                                               │
                    │  ┌─────────────────────────────────────────┐  │
                    │  │  text  (serialized read-only widget)    │  │
                    │  │  "the converted value lives here"       │  │
                    │  └─────────────────────────────────────────┘  │
                    └───────────────────────────────────────────────┘
                         │  web/text_preview.js creates that widget
                         │  and fills it with the executed text
                         ▼
              workflow JSON save: text is in the file
```

1. **Connect any output** into the optional `text` port (the node has no text widget of its own, same as the built-in "Preview Any"). Leaving the port unconnected is valid.
2. On each run the backend converts the received value to text and returns it as a UI output (`[]` when no value was received).
3. The frontend extension `web/text_preview.js` creates a real, serialized multiline widget in the node body and writes the text into it — or removes the widget when the run produced no text.
4. When you **save the workflow**, that widget value is serialized into the JSON, so the displayed text is stored *inside* the workflow file itself.
5. When you **load the workflow**, the extension rebuilds the widget from the stored value — the text is displayed again immediately, cached runs included, no execution needed.

The display widget is **read-only**: its value is always the text that was executed (or the text that was saved with the workflow), so what you see is exactly what the JSON contains. After a run with no text the widget is removed and the node body is empty; that cleared state is what the next workflow save stores.

### Batch runs and per-image prompts

When a list reaches `text` (for example **Skutils Style Selector** in *Batch: one run per style* mode), the backend runs once per item and ComfyUI sends the frontend one merged payload containing **every** item. The node draws them all, one read-only text widget per item, in list order — so a 40-style batch shows 40 prompts and the next workflow save contains all 40.

The node's `STRING` output is still the per-item text, in order. Connect it to **Save Compressed Weppy**'s `enhanced_prompt` input and each saved image's embedded workflow is rewritten to contain only the prompt that produced that image (see [per-image preview text](save-compressed-weppy.md#per-image-preview-text)). The extra output does not change the on-node display.

### What is and isn't stored

| Place | Stored? | Why |
|---|---|---|
| Workflow JSON from **File → Save / Ctrl+S** (the usual `.json`) | ✅ | Widget values are serialized into it |
| Workflow JSON embedded in images by save nodes (incl. [Save Compressed Weppy](save-compressed-weppy.md)) | ✅ | Same UI workflow document, embedded as metadata — drag the image back and the text returns |
| **Save (API format)** JSON | ❌ | That format stores only the executable graph (links/inputs), never widget values — same limitation as *every* node's widgets (seeds, prompts, …) |
| Text that only ever ran headless (CLI `--prompt`, no browser open) | ❌ | Nothing is shown, so nothing can be copied into the widget |

## Example

1. Add a **Skutils Text Preview** node.
2. Connect any output into its `text` port — e.g. a text node's `STRING`, a `BOOLEAN`, a number, or an `IMAGE`.
3. Run the workflow once — the converted value appears in the read-only text area inside the node.
4. **Ctrl+S** and reopen the workflow: the text is still displayed, even if you never run it again.

## Files

- `text_preview/text_preview.py` — node implementation: optional port-only wildcard `text` input (`"*"`, `forceInput`), `to_text()` conversion of any value (string, boolean, number, tensor summary, pretty-printed containers, `repr()` fallback), returns the converted text both as a `STRING` output and as `{"ui": {"text": [...]}}` (or `{"ui": {"text": []}}` and `""` when nothing was received).
- `text_preview/__init__.py` — registers the node mapping.
- `web/text_preview.js` — frontend extension that creates the serialized display widget, fills it (or removes it when empty) from `onExecuted`, and rebuilds it from stored values on `configure`/`onConfigure`.

## Installation

The feature ships as part of the unified `ComfyUI-skkut-utils` repo — see the [root README](../README.md). Restart ComfyUI after installing.
