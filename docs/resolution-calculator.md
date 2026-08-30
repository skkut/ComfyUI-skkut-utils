# Skutils Resolution Calculator

A resolution-selector node that outputs **width** and **height** from an **aspect-ratio preset** and a **megapixel target** — like the built-in ComfyUI *Resolution Selector*, but with double the aspect-ratio options and a fixed megapixel dropdown instead of a free float.

## Overview

| | |
|---|---|
| **Python backend** | `resolution_calculator/__init__.py` (node mapping) + `resolution_calculator/resolution_calculator.py` (node) |
| **Frontend extension** | none (plain custom node) |
| **Dependency** | none beyond ComfyUI itself |

Node name: **Skutils Resolution Calculator** · Category: `utils/resolution`

## Node configuration

| Input | Type | Default | Description |
|---|---|---|---|
| `aspect_ratio` | COMBO (20 presets) | `1:1 (Square)` | Aspect-ratio preset; see the table below |
| `megapixels` | COMBO (10 values) | `1.0` | Target total megapixels — `0.5` to `5.0` in **0.5 steps** (values are plain numbers, e.g. `1.0`) |
| `multiple` | COMBO (advanced) | `8` | Round both dimensions to a multiple of this — dropdown: `8` / `16` / `32` / `64` / `128`. `8` divides all of 16/32/64, so it works for every model family; use `16`/`32`/`64` for Flux and video models |

Outputs: **`width`** (`INT`) and **`height`** (`INT`) — connect them straight into an **Empty Latent Image** node.

All three inputs are dropdowns: aspect-ratio preset, megapixels (0.5–5.0), and rounding multiple (8/16/32/64/128).

## How it works

Each preset is anchored to the **canonical resolution the community uses at ~1 MP** (SDXL / SD3 / Flux / video ladders). The node scales that anchor by the square root of the megapixel target and rounds both sides to `multiple` — the same math as the built-in *Resolution Selector*:

```
scale  = sqrt(megapixels)
width  = round(anchor_w × scale / multiple) × multiple
height = round(anchor_h × scale / multiple) × multiple
```

So at `1.0 MP` the node reproduces the familiar ladder values exactly (e.g. `16:9` → `1344×768`, the SDXL/Flux widescreen), and at other megapixel values it scales smoothly (e.g. `1:1` at `2.0 MP` → `1448×1448`).

## Preset table

The first 8 presets use the **exact option strings of the built-in node**, so workflows built with it drop in unchanged. The rest extend the ladder.

| Preset | Anchor @ 1 MP | Ratio | Typical use |
|---|---|---|---|
| `1:1 (Square)` | 1024×1024 | 1:1 | Native square — SDXL / SD3 / Flux |
| `4:5 (Social Portrait)` | 896×1152 | ~4:5 | SDXL ladder portrait, social media |
| `3:4 (Portrait Standard)` | 768×1024 | 3:4 | Flux official portrait |
| `2:3 (Portrait Photo)` | 832×1216 | ~2:3 | SDXL ladder portrait photo |
| `3:5 (Cinematic Portrait)` | 768×1280 | 3:5 | Video portrait (HunyuanVideo, LTX) |
| `9:16 (Portrait Widescreen)` | 768×1344 | ~9:16 | SDXL / Flux portrait widescreen, vertical video |
| `1:2 (Portrait Panorama)` | 728×1448 | 1:2 | Tall panorama (SD1.5 ultratall class) |
| `5:12 (Ultra Portrait)` | 640×1536 | ~5:12 | SDXL / Flux ultratall (the ladder's "9:21") |
| `1:3 (Super Portrait)` | 592×1776 | 1:3 | Ultra-tall posters / vertical 3:1 |
| `9:32 (Super Tall)` | 544×1928 | 9:32 | Ultra-tall vertical (mirror of 32:9) |
| `5:4 (Social Landscape)` | 1152×896 | ~5:4 | SDXL ladder landscape |
| `4:3 (Standard)` | 1024×768 | 4:3 | Flux official landscape |
| `3:2 (Photo)` | 1216×832 | ~3:2 | SDXL ladder photo |
| `5:3 (Cinematic Landscape)` | 1280×768 | 5:3 | Video landscape (HunyuanVideo, LTX) |
| `16:9 (Widescreen)` | 1344×768 | ~16:9 | SDXL / Flux widescreen (the ladder's "16:9") |
| `2:1 (Panorama)` | 1448×728 | 2:1 | Panorama (SD1.5 ultrawide class) |
| `21:9 (Ultrawide)` | 1536×640 | ~21:9 | SDXL / Flux ultrawide |
| `12:5 (Cinema Scope)` | 1584×664 | 12:5 | True 2.4:1 anamorphic widescreen |
| `3:1 (Super Panorama)` | 1776×592 | 3:1 | Extreme panoramas (3:1 photo standard) |
| `32:9 (Super Ultrawide)` | 1928×544 | 32:9 | Dual-monitor class (5120×1440 / 3840×1080) |

Notes on anchors:

- `~` labels are the *industry* names for near-matches (e.g. `1344×768` is mathematically 7:4 but is universally called "16:9" in SDXL/Flux material).
- Anchors are the canonical ~1 MP sizes, so a preset's area can be slightly under/over 1.0 MP (e.g. Flux `3:4` = 768×1024 ≈ 0.79 MP). That is intentional — the anchor is what the model family actually trains/generates at.
- The "SD1.5 class" entries cover the 512/768-base era ratios; SD1.5 generation typically happens at `0.5–0.6 MP` with `multiple = 64`.

## Example

`1:1 (Square)` + megapixels `2.0` + `multiple 8` → `width 1448`, `height 1448` (≈2.1 MP, divisible by 8).

## Files

- `resolution_calculator/resolution_calculator.py` — node implementation: `RESOLUTION_OPTIONS`, `MEGAPIXEL_OPTIONS`, `SkutilsResolutionCalculator`.
- `resolution_calculator/__init__.py` — registers the node mapping.

## Installation

The feature ships as part of the unified `ComfyUI-skkut-utils` repo — see the [root README](../README.md). Restart ComfyUI after installing.
