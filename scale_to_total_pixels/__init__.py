"""
Skutils Scale Image to Total Pixels — feature subpackage of
ComfyUI-skkut-utils.

A "Scale Image to Total Pixels" custom node whose **image input is
optional**.  The inputs, widget ranges, rounding and resize math are those
of ComfyUI's core node of the same name, so it is a drop-in replacement —
but with nothing plugged into ``image`` it outputs ``None`` and the
workflow still queues, instead of failing prompt validation.

That difference matters because ComfyUI validates required inputs
statically and is not lazy-aware: the core node's required ``image`` makes
any optional image slot upstream impossible to leave empty, no matter what
switch protects it.  See ``docs/scale-to-total-pixels.md``.
"""

from .scale_to_total_pixels import SkutilsScaleImageToTotalPixels

NODE_CLASS_MAPPINGS = {
    "SkutilsScaleImageToTotalPixels": SkutilsScaleImageToTotalPixels,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SkutilsScaleImageToTotalPixels": "Skutils Scale Image to Total Pixels",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
