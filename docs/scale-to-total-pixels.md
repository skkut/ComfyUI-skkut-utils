# Skutils Scale Image to Total Pixels

ComfyUI's built-in **Scale Image to Total Pixels** node with an **optional** `image` input — same widgets, same ranges, same resize math, but with nothing plugged in it outputs nothing instead of failing prompt validation.

## Overview

| | |
|---|---|
| **Python backend** | `scale_to_total_pixels/__init__.py` (node mapping) + `scale_to_total_pixels/scale_to_total_pixels.py` (node) |
| **Frontend extension** | none (plain custom node) |
| **Dependency** | none beyond ComfyUI itself |

Node name: **Skutils Scale Image to Total Pixels** · Category: `utils/resolution`

## The problem this node solves

This node exists for one reason: **ComfyUI validates a prompt's required inputs before it executes anything, and that validation is not lazy-aware.**

### 1. Validation is static — a switch does not protect a broken branch

When you queue a prompt, every node in it is checked up front. A node with a *required* link-only input and nothing plugged into it fails the entire submission with:

```
Prompt outputs failed validation
```

It makes no difference that the node sits on a branch nothing will ever request — behind a `lazy` switch that selects the other side, for example. The check runs **before** execution begins, so "that branch is never taken" is not a defence. The workflow is rejected outright.

### 2. The built-in node makes optional image slots impossible

The built-in node's `image` input is required, and its own body opens with `samples = image.movedim(-1, 1)` — so there is no `None` guard either; an absent image would be an immediate `AttributeError` on top of the validation failure.

That produces a specific, common dead end. You want a workflow that offers optional image slots:

> *"Plug in `image_1`. If you also have a second reference, plug in `image_2` and it gets resized to the same pixel budget."*

The moment an `ImageScaleToTotalPixels` node is wired to `image_2`, **the workflow can no longer be queued at all** unless `image_2` is filled. The resize that exists to *support* the optional slot is exactly what makes that slot impossible to leave empty. And it is not conditional on any setting — a `custom_size` boolean upstream does not help, because validation does not evaluate booleans either.

### 3. The workarounds are worse than the problem

| Workaround | Why it fails |
|---|---|
| **Feed the resize a dummy image** | Validation passes, but the graph now resizes and carries an image nobody asked for. Anything downstream that consumes it produces a silent wrong result, and the run pays for an extra encode. |
| **Put a switch after the resize** | No effect. Validation runs before the switch is evaluated, so the required input is still missing and the prompt is still rejected. |
| **Use `LayerUtility: ImageScaleByAspectRatio V2`** (comfyui_layerstyle) | Its `image` really is optional, so it does solve the validation problem — but it is a *different node*: an eleven-widget aspect-ratio tool whose budget is in **kilo-pixels**, whose rounding rounds **up** rather than to nearest, and whose filter list starts elsewhere. Different dimensions come out. It is a workaround, not a replacement. |

### The fix: remove the constraint instead of working around it

This node keeps the built-in node's inputs, ranges, defaults, output and arithmetic exactly as they are, and makes `image` optional. Nothing connected in, `None` out. A resize nobody asked for then costs nothing and blocks nothing — and the numbers, when it *is* asked for, are the built-in node's numbers.

## Node configuration

| Input | Type | Default | Section | Description |
|---|---|---|---|---|
| `upscale_method` | COMBO | `nearest-exact` | required | Resampling filter: `nearest-exact` / `bilinear` / `area` / `bicubic` / `lanczos` — the built-in node's list, in its order |
| `megapixels` | FLOAT | `1.0` | required | Target total pixel count, `0.01`–`16.0` in `0.01` steps |
| `resolution_steps` | INT *(advanced)* | `1` | required | Round width and height to a multiple of this, `1`–`256` |
| `image` | IMAGE | *(unconnected)* | **optional** | The image to scale. Leave it unconnected to skip the resize and output nothing |

Output: **`image`** (`IMAGE`) — or `None` when the input was not connected.

Every value defaults to the built-in node's, so the node can be dropped in as a direct replacement without re-tuning anything.

## How it works

With an image connected, the arithmetic is copied verbatim from `comfy_extras/nodes_post_processing.py`:

```
samples   = image.movedim(-1, 1)
total     = megapixels × 1024 × 1024
scale_by  = sqrt(total / (width × height))
new_width = round(width  × scale_by / resolution_steps) × resolution_steps
new_height= round(height × scale_by / resolution_steps) × resolution_steps
out       = common_upscale(samples, new_width, new_height, upscale_method, "disabled")
```

Note this is a **1024-based** megapixel (1 MP = 1,048,576 px), unlike the decimal megapixel used by [Skutils Resolution Calculator](resolution-calculator.md). The two are deliberately different: this node matches the built-in resize node pixel for pixel, and changing it would break drop-in substitution.

With **no image connected**, the node returns `None` and stops there — no resize is attempted and no error is raised.

### What happens to the `None`

`None` propagates like any other value, so whatever consumes the output has to tolerate it:

- **Tolerates `None`** — an autogrow image container such as `TextEncodeQwenImage21`'s `images`, and `ComfySwitchNode`'s `on_false` / `on_true` inputs (both are optional, so an absent branch is fine).
- **Does not tolerate `None`** — a plain required `IMAGE` input. It will fail validation in its turn.

So place this node at the **end** of an optional branch, not in the middle of one that must always produce an image.

## Example

`image_2` is an optional reference image, resized only when the upstream `custom_size` boolean is on:

```
                       ┌─────────────────────────────────┐
 image_2 ──────────────┤ Skutils Scale Image to Total    ├──────► on_true
   │                   │ Pixels  (megapixels 3, steps 32)│
   │                   └─────────────────────────────────┘        ┌──────────────┐
   │                                                              │ ComfySwitch  │
   └──────────────────────────────────────────────────────────────► on_false     │
                                                                  │              │
                                            custom_size ─────────►│ switch       │
                                                                  └──────┬───────┘
                                                                         ▼
                                                     TextEncodeQwenImage21.images.image_2
```

Leave `image_2` unconnected and the whole graph still queues: the resize node returns `None`, the switch selects whichever branch `custom_size` names, and the encoder's image slot accepts a `None` either way.

That is the shape this node exists to make possible. Swap the *built-in* Scale Image to Total Pixels into the same position and the workflow stops queueing entirely — `image_2` unconnected is a validation failure, and `custom_size` cannot rescue it, because validation does not evaluate the boolean.

## Troubleshooting

**The node outputs nothing / the image is missing downstream.**
That is the optional path working as designed — either `image` is unconnected, or whatever feeds it produced `None`. Check the upstream slot first.

**A downstream node now fails validation where it used to pass.**
The `None` reached a required `IMAGE` input. Only some node types tolerate `None` (see *What happens to the `None`* above); move this node to the end of the optional branch, or interpose a switch that selects a real image on the other side.

**`resolution_steps` produces surprising dimensions.**
The built-in node rounds to the **nearest** multiple, while `LayerUtility: ImageScaleByAspectRatio V2` rounds **up**. If you are replacing one with the other, expect results up to one step apart — that is the difference this node was built to avoid, not a bug.

**The `image` port sits below the widgets, unlike the built-in node.**
Expected. ComfyUI renders every `optional` input after the `required` ones, and making `image` optional is the entire point of this node. It is a rendering rule, not a behavioural difference; the input names, types and settings are otherwise the built-in node's.

**Very large images with a tiny `megapixels` and a large `resolution_steps` can round a dimension to 0.**
Inherited from the built-in node, which computes the same value and then fails inside `common_upscale`; the arithmetic here is kept identical on purpose. Raise `megapixels` or lower `resolution_steps`.

## Files

- `scale_to_total_pixels/scale_to_total_pixels.py` — node implementation: `UPSCALE_METHODS`, `SkutilsScaleImageToTotalPixels` (the module docstring carries the full problem statement).
- `scale_to_total_pixels/__init__.py` — registers the node mapping.

## Installation

The feature ships as part of the unified `ComfyUI-skkut-utils` repo — see the [root README](../README.md). Restart ComfyUI after installing.
