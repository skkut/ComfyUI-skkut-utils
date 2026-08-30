"""
Skutils Resolution Calculator — node implementation.

Calculates width and height from an aspect-ratio preset and a megapixel
target, mirroring the built-in "Resolution Selector" node (aspect ratio +
megapixels + rounding multiple) with a much larger list of aspect-ratio
presets and a fixed megapixel dropdown (0.5–5.0 MP in 0.5 steps).

The first 8 aspect-ratio options are the exact option strings of the
built-in node, so workflows built with it drop in unchanged; the rest are
additional presets covering the SD1.5 / SDXL / SD3-Flux / video-model
ladders.  See docs/resolution-calculator.md for the full table.
"""

import math

# Aspect-ratio presets: label -> (width, height) anchor at 1.0 MP.
# Anchors are the canonical resolutions the community uses at ~1 MP
# (SDXL / SD3 / Flux / video ladders).  Other megapixel values scale the
# anchor by sqrt(MP) and round to `multiple`, exactly like the built-in
# Resolution Selector node.
RESOLUTION_OPTIONS = {
    "1:1 (Square)": (1024, 1024),
    "4:5 (Social Portrait)": (896, 1152),
    "3:4 (Portrait Standard)": (768, 1024),
    "2:3 (Portrait Photo)": (832, 1216),
    "3:5 (Cinematic Portrait)": (768, 1280),
    "9:16 (Portrait Widescreen)": (768, 1344),
    "1:2 (Portrait Panorama)": (728, 1448),
    "5:12 (Ultra Portrait)": (640, 1536),
    "1:3 (Super Portrait)": (592, 1776),
    "9:32 (Super Tall)": (544, 1928),
    "5:4 (Social Landscape)": (1152, 896),
    "4:3 (Standard)": (1024, 768),
    "3:2 (Photo)": (1216, 832),
    "5:3 (Cinematic Landscape)": (1280, 768),
    "16:9 (Widescreen)": (1344, 768),
    "2:1 (Panorama)": (1448, 728),
    "21:9 (Ultrawide)": (1536, 640),
    "12:5 (Cinema Scope)": (1584, 664),
    "3:1 (Super Panorama)": (1776, 592),
    "32:9 (Super Ultrawide)": (1928, 544),
}

# Megapixel dropdown: 0.5 to 5.0 in 0.5 steps.
MEGAPIXEL_OPTIONS = [f"{mp:.1f}" for mp in (i * 0.5 for i in range(1, 11))]

# Rounding-multiple dropdown. 8 is the minimal value that divides all the
# model families' requirements (SD1.5 wants 64, Flux wants 16/32, video
# models 16/32/64), so it stays the default.
MULTIPLE_OPTIONS = [8, 16, 32, 64, 128]


class SkutilsResolutionCalculator:
    """Calculate width and height from an aspect-ratio preset and a
    megapixel target.  Useful for setting up Empty Latent Image dimensions."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "aspect_ratio": (
                    list(RESOLUTION_OPTIONS.keys()),
                    {"default": "1:1 (Square)",
                     "tooltip": "The aspect ratio for the output dimensions."},
                ),
                "megapixels": (
                    MEGAPIXEL_OPTIONS,
                    {"default": "1.0",
                     "tooltip": "Target total megapixels. 1.0 ≈ 1024x1024 for square."},
                ),
                "multiple": (
                    MULTIPLE_OPTIONS,
                    {"default": 8, "advanced": True,
                     "tooltip": "Round both dimensions to a multiple of this. 8 divides 16/32/64, so it works for every model family; use 16/32/64 for Flux and video models."},
                ),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "calculate"
    CATEGORY = "utils/resolution"

    def calculate(self, aspect_ratio, megapixels, multiple):
        base_w, base_h = RESOLUTION_OPTIONS[aspect_ratio]
        mp = float(megapixels)
        scale = math.sqrt(mp)
        width = round(base_w * scale / multiple) * multiple
        height = round(base_h * scale / multiple) * multiple
        return (width, height)
