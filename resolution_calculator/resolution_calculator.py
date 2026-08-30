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

# Aspect-ratio presets: label -> (width, height) anchor at ~1 MP.
# Anchors are the canonical resolutions the community uses at ~1 MP
# (SDXL / SD3 / Flux / video ladders); their exact pixel count is not
# always 1,000,000 (e.g. Flux 3:4 = 768x1024 ≈ 0.79 MP).  Other megapixel
# values scale the anchor so the result has the requested total or just
# below (never above), with both sides a multiple of `multiple` and the
# 1:1 preset always an exact square.
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
                     "tooltip": "Target total megapixels (1 MP = 1,000,000 px); the result never exceeds this."},
                ),
                "multiple": (
                    MULTIPLE_OPTIONS,
                    {"default": 8, "advanced": True,
                     "tooltip": "Both dimensions are multiples of this, and the total is at most the selected megapixels. 8 divides 16/32/64, so it works for every model family; use 16/32/64 for Flux and video models."},
                ),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "calculate"
    CATEGORY = "utils/resolution"

    def calculate(self, aspect_ratio, megapixels, multiple):
        base_w, base_h = RESOLUTION_OPTIONS[aspect_ratio]
        # Megapixels are decimal: 1 MP = 1,000,000 pixels.  Anchors are the
        # model ladders' canonical ~1 MP sizes, which are not exactly
        # 1,000,000 px, so the scale is computed relative to the anchor's
        # actual pixel count.
        target_px = float(megapixels) * 1_000_000
        # A square preset must stay square: the largest multiple-compatible
        # square at or below the target (e.g. 1:1 at 1.5 MP -> 1224x1224).
        if base_w == base_h:
            side = math.floor(math.sqrt(target_px) / multiple) * multiple
            return (side, side)
        pixels = base_w * base_h
        scale = math.sqrt(target_px / pixels)
        w0 = base_w * scale
        h0 = base_h * scale
        # Never exceed the target: among the multiples of `multiple` around
        # the ideal size, find the largest w*h at or below target_px.  For
        # each candidate width the best height is the largest multiple that
        # still fits, so the result stays within one `multiple` of the
        # achievable maximum.
        lo = math.floor(w0 / multiple) - 3
        hi = math.floor(w0 / multiple) + 3
        best_area = 0
        candidates = []
        for kw in range(lo, hi + 1):
            w = kw * multiple
            if w <= 0:
                continue
            h = math.floor(target_px / w / multiple) * multiple
            if h <= 0:
                continue
            area = w * h
            candidates.append((area, w, h))
            if area > best_area:
                best_area = area
        # Max area alone can distort the shape for tiny gains (e.g. 16:9 at
        # 1.0 MP would come out 1344x744 instead of 1328x752).  Among
        # candidates within one grid step of the best area, prefer the
        # closest aspect ratio; beyond that, more pixels win.
        slack = multiple * min(w0, h0)
        best_w = best_h = 0
        best_ratio_err = float("inf")
        for area, w, h in candidates:
            if area < best_area - slack:
                continue
            ratio_err = abs(w / h - w0 / h0)
            if ratio_err < best_ratio_err:
                best_w, best_h, best_ratio_err = w, h, ratio_err
        return (best_w, best_h)
