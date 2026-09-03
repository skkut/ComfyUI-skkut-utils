"""
Skutils Text Preview — feature subpackage of ComfyUI-skkut-utils.

A "Skutils Text Preview" custom node: display a text anywhere in your
workflow and have that text saved inside the workflow JSON itself
(standard File → Save, or embedded in saved images) — unlike the built-in
display-only text-preview nodes, whose text disappears on save/reload.

Implementation notes:
  * text_preview.py — the node. Returns the text as UI output.
  * web/text_preview.js — the frontend half. Copies each executed text
    into the node's regular (serialized) widget, which is what the
    workflow JSON stores and restores.
"""

from .text_preview import SkutilsTextPreview

NODE_CLASS_MAPPINGS = {
    "SkutilsTextPreview": SkutilsTextPreview,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SkutilsTextPreview": "Skutils Text Preview",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
