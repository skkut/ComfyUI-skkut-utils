# Skutils Resolution Calculator

A resolution-selector node that outputs **width** and **height** from an **aspect-ratio preset** and a **megapixel target** — like the built-in ComfyUI *Resolution Selector*, but with double the aspect-ratio options and a megapixel **dropdown of presets that also accepts any value** you type.

## Overview

| | |
|---|---|
| **Python backend** | `resolution_calculator/__init__.py` (node mapping) + `resolution_calculator/resolution_calculator.py` (node) |
| **Frontend extension** | `web/resolution_calculator.js` — adds the **Custom…** entry to the megapixels dropdown |
| **Dependency** | none beyond ComfyUI itself |

Node name: **Skutils Resolution Calculator** · Category: `skkut-utils` (Nodes → Extensions → skkut-utils)

## Node configuration

| Input | Type | Default | Description |
|---|---|---|---|
| `aspect_ratio` | COMBO (20 presets) | `1:1 (Square)` | Aspect-ratio preset; see the table below |
| `megapixels` | COMBO (10 presets + **Custom…**) | `1.0` | Target total megapixels — pick one of the prominent presets `0.5`, `1.0`, `2.0`, `3.0`, `4.0`, `6.0`, `8.0`, `12.0`, `16.0`, `20.0`, or choose **Custom…** and type any positive number (e.g. `1.5`, `3.75`, `24`, `0.3`) |
| `multiple` | COMBO (advanced) | `8` | Round both dimensions to a multiple of this — dropdown: `8` / `16` / `32` / `64` / `128`. `8` divides all of 16/32/64, so it works for every model family; use `16`/`32`/`64` for Flux and video models |

Outputs: **`width`** (`INT`) and **`height`** (`INT`) — connect them straight into an **Empty Latent Image** node.

All three inputs are dropdowns: aspect-ratio preset, megapixels, and rounding multiple (8/16/32/64/128). The megapixel list is deliberately short — **10 prominent points**, spaced roughly geometrically from `0.5` to `20.0` MP (drafts, the ~1 MP native size, and the common 2×/4×/8×/16× upscale ladder) — and the frontend appends a **Custom…** entry so any other positive value (in between, or above 20 MP) is one click away without leaving the dropdown. See [Custom megapixel values](#custom-megapixel-values).

## How it works

Each preset is anchored to the **canonical resolution the community uses at ~1 MP** (SDXL / SD3 / Flux / video ladders). The node scales that anchor so the result has the **requested total megapixels — or just below, never above** — with both sides a multiple of `multiple`:

```
target_px = megapixels × 1,000,000     # 1 MP = 1,000,000 pixels
pixels    = anchor_w × anchor_h
scale     = sqrt(target_px / pixels)
```

The scale is computed relative to the anchor's **actual** pixel count (not an assumed exact 1.0 MP), so the result lands on the target regardless of the anchor. Then, among the multiples of `multiple` around the ideal size, the node picks the **largest `width × height` that does not exceed `target_px`**; when two candidates are within one grid step of the best area, the one closest to the preset's aspect ratio wins, and the `1:1` preset always returns an exact square. The result is therefore capped at the selected megapixels:

- `1:1` at `3.0 MP`, `multiple 8` → `1728×1728` ≈ **2.986 MP** — an exact square, never above
- `3:4` at `2.0 MP`, `multiple 8` → `1224×1632` ≈ **1.998 MP** (≤ 2.0)
- `16:9` at `1.0 MP`, `multiple 8` → `1328×752` ≈ **0.999 MP** (≤ 1.0)
- `32:9` at `6.0 MP`, `multiple 128` → `4608×1280` ≈ **5.898 MP** (≤ 6.0)
- `1:1` at `20.0 MP`, `multiple 8` → `4472×4472` ≈ **19.999 MP** (≤ 20.0)
- `16:9` at `20.0 MP`, `multiple 8` → `5920×3376` ≈ **19.986 MP** (≤ 20.0)
- `1:1` at `1.0 MP`, `multiple 8` → `1000×1000` = **exactly 1.0 MP**

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
- Anchors are the canonical ~1 MP sizes, so a preset's area can be slightly under/over 1.0 MP (e.g. Flux `3:4` = 768×1024 ≈ 0.79 MP). That is intentional — the anchor is what the model family actually trains/generates at. The anchor only sets the **shape**; the scale math above always lands on the selected megapixel target (or just under it).
- The "SD1.5 class" entries cover the 512/768-base era ratios; SD1.5 generation typically happens at `0.5–0.6 MP` with `multiple = 64`.

## Example

`1:1 (Square)` + megapixels `2.0` + `multiple 8` → `width 1408`, `height 1408` (≈1.98 MP — exact square, divisible by 8, never above the target).

With a value typed through **Custom…**: `16:9 (Widescreen)` + megapixels `24` + `multiple 8` → `width 6472`, `height 3704` (≈23.972 MP — under the target, both sides divisible by 8).

## Custom megapixel values

The megapixels dropdown keeps its 10 presets and gains one extra entry,
**Custom…**, which asks for a number:

1. Pick **Custom…** (the last entry in the dropdown).
2. Type any positive number — `3.75`, `24`, `0.3`, `12.25` — and confirm.
3. The value becomes the widget value and is inserted into the dropdown in
   numeric order, so the node shows it like a preset and you can re-select
   it later without retyping.

Behaviour details:

- **Formatting** — values are canonicalised to at most 4 decimal places and
  written with at least one decimal (`7` → `7.0`, `3.75` → `3.75`), matching
  the preset style.
- **Persistence** — the value is stored in the widget like a preset, so it is
  saved in the workflow JSON and sent in the API prompt. Loading the workflow
  re-adds the value to that node's dropdown and displays it as the current
  selection.
- **Cancel** restores the previously selected value; invalid input (text,
  zero, negative) shows a message and asks again.
- **Validation** — the backend's `VALIDATE_INPUTS(megapixels)` accepts any
  positive number and exempts the input from ComfyUI's combo-membership
  check; non-numeric or non-positive values still fail with a clear error.
- The `Custom…` entry and any custom values live only in the browser: the
  server's preset list is unchanged, and other nodes of this type are not
  affected.

## Files

- `resolution_calculator/resolution_calculator.py` — node implementation: `RESOLUTION_OPTIONS`, `MEGAPIXEL_OPTIONS`, `SkutilsResolutionCalculator`, `VALIDATE_INPUTS`.
- `resolution_calculator/__init__.py` — registers the node mapping.
- `web/resolution_calculator.js` — adds the **Custom…** dropdown entry and its prompt; re-adds saved custom values when a workflow loads.

## Installation

The feature ships as part of the unified `ComfyUI-skkut-utils` repo — see the [root README](../README.md). Restart ComfyUI after installing.

## Troubleshooting

- **No Custom… entry in the dropdown.** The frontend extension did not load.
  Restart ComfyUI (the extension list is built at startup) and hard-refresh
  the browser (Ctrl+F5 / Cmd+Shift+R) so the new `web/resolution_calculator.js`
  is fetched.
- **Queueing fails with "megapixels must be a number/positive number".** The
  widget holds something that is not a positive number — for example the
  literal `Custom…` value, if a workflow was saved while the prompt was open.
  Pick a preset, or choose Custom… and enter a number.
- **A custom value shows with a red outline in the new node UI.** The value is
  not in that node's dropdown list. It is re-added automatically when the
  workflow is loaded; re-picking or retyping it also fixes it.
- **Custom values above 20 MP produce enormous images.** That is expected:
  only the presets are capped at 20 MP. Check available VRAM before queueing.
