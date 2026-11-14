"""
Skutils Resolution Calculator — feature subpackage of ComfyUI-skkut-utils.

A "Resolution Calculator" custom node: pick an aspect-ratio preset
(20 options — the built-in "Resolution Selector" list plus the
SD1.5 / SDXL / SD3-Flux / video-model ladders and ultra-wide / ultra-tall
tiers) and a megapixel target from a short dropdown of prominent presets
(0.5–20.0 MP, or any positive value through the frontend's "Custom…"
entry) and get the matching width and height, ready to feed an Empty
Latent Image node.
"""

from .resolution_calculator import SkutilsResolutionCalculator

NODE_CLASS_MAPPINGS = {
    "SkutilsResolutionCalculator": SkutilsResolutionCalculator,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SkutilsResolutionCalculator": "Skutils Resolution Calculator",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
