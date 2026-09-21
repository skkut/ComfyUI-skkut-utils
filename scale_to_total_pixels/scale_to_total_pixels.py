"""
Skutils Scale Image to Total Pixels — node implementation.

A drop-in replacement for ComfyUI's core "Scale Image to Total Pixels"
(``comfy_extras/nodes_post_processing.py``) with exactly one behavioural
difference: the ``image`` input is **optional**.  The widgets, their order,
their ranges and the resize math are copied verbatim, so this node can take
the core node's place in a graph without touching anything else in it.

Problem statement
-----------------
Why a second node is needed at all.

**1. ComfyUI validates a prompt's inputs statically, and that validation is
not lazy-aware.**  Before a single node executes, every node in the prompt
is checked, and a *required* link-only input with nothing plugged into it
fails the whole submission with ``Prompt outputs failed validation``.  It
does not matter that the node sits on a branch nothing will ever request —
for example behind a ``lazy`` switch that selects the other side.  "The
branch is never taken" is not a defence, because the check happens before
execution begins.

**2. The core node's ``image`` is required, and its execute body has no
``None`` guard.**  It opens with ``samples = image.movedim(-1, 1)``, so an
absent image is an immediate ``AttributeError`` as well as a validation
failure.  The practical effect: a workflow that offers optional image slots
— "plug in image_1 and, if you have one, image_2" — cannot be queued at all
unless *every* slot is filled.  The resize that exists to *support* the
optional slot is precisely what makes that slot impossible to leave empty.

**3. The available workarounds are worse than the problem.**

- *Feed the resize a dummy image.*  Keeps validation happy, but the graph
  now resizes and carries an image nobody asked for; anything downstream
  that consumes it produces a silent wrong result, and the run pays for an
  extra encode.
- *Put a switch after the resize.*  No effect at all: validation runs
  before the switch is ever evaluated, so the required input is still
  missing and the prompt is still rejected.
- *Use ``LayerUtility: ImageScaleByAspectRatio V2``* (comfyui_layerstyle).
  Its ``image`` is genuinely optional and it does return ``None`` when
  nothing is plugged in, which solves the validation problem — but it is a
  *different node*: an eleven-widget aspect-ratio tool whose budget is in
  kilo-pixels, whose rounding rounds **up** instead of to nearest, and
  whose filter list starts elsewhere.  Dropping it in for the core node
  changes the resulting dimensions, so it is a workaround, not a
  replacement.

**So this node removes the constraint instead of working around it.**  It
keeps the core node's inputs, ranges, defaults, output and arithmetic
exactly as they are, and makes ``image`` optional: nothing connected in,
``None`` out.  A resize nobody asked for then costs nothing and blocks
nothing.

Behaviour
---------
``image`` connected
    Identical numbers to the core node — same ``common_upscale`` call, same
    rounding, same filter list.
``image`` absent
    Returns ``None`` and queues cleanly.  The ``None`` then propagates like
    any other value, so whatever consumes the output must tolerate it.  An
    autogrow image container such as ``TextEncodeQwenImage21``'s ``images``
    does; a plain required ``IMAGE`` input does not, and will fail
    validation in its turn — put this node at the *end* of an optional
    branch, not in the middle of one that must always produce an image.

Compatibility notes
-------------------
- Because ``image`` is optional, ComfyUI renders its port *below* the three
  widgets rather than above them.  That is the frontend's rendering rule
  for the optional section, not a behavioural difference; the input names,
  types and widget settings are otherwise the core node's.
- ``upscale_method`` is declared with an explicit default of
  ``nearest-exact``, which is the first entry of the core node's option
  list and therefore the value its UI starts on.
- ``resolution_steps`` keeps the core node's ``advanced`` flag, so the
  node body looks the same as the core one out of the box.
"""

import math

# Copied verbatim from the core node so the two offer identical choices in
# identical order.
UPSCALE_METHODS = ["nearest-exact", "bilinear", "area", "bicubic", "lanczos"]


class SkutilsScaleImageToTotalPixels:
    """Scale an image so its total pixel count reaches ``megapixels``.

    Same inputs and same arithmetic as the core "Scale Image to Total
    Pixels" node, except that ``image`` is optional: with nothing connected
    the node returns ``None`` and the workflow still queues.
    """

    DESCRIPTION = (
        "Same inputs and math as the core 'Scale Image to Total Pixels' node, "
        "but the image input is optional: leave it unconnected and the node "
        "outputs nothing instead of failing prompt validation. Use it to "
        "resize an image slot that may be left empty."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "upscale_method": (
                    UPSCALE_METHODS,
                    {"default": "nearest-exact",
                     "tooltip": "Resampling filter — the same list, in the same order, as the core node."},
                ),
                "megapixels": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.01, "max": 16.0, "step": 0.01,
                     "tooltip": "Target total pixel count in megapixels (1 MP = 1024×1024 px). The image is scaled by sqrt(target / actual), exactly as the core node does."},
                ),
                "resolution_steps": (
                    "INT",
                    {"default": 1, "min": 1, "max": 256, "advanced": True,
                     "tooltip": "Round width and height to a multiple of this. The core node's default is 1 — no rounding."},
                ),
            },
            "optional": {
                "image": (
                    "IMAGE",
                    {"tooltip": "Optional. Leave unconnected to skip the resize and output nothing."},
                ),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "scale"
    CATEGORY = "utils/resolution"

    def scale(self, upscale_method, megapixels, resolution_steps, image=None):
        # Imported here rather than at module scope: comfy.utils only
        # resolves inside ComfyUI's process, and the repo keeps every module
        # importable outside it.
        import comfy.utils

        if image is None:
            # Nothing to resize.  Returning None is what keeps the
            # surrounding workflow queueable — see the module docstring.
            return (None,)

        # Verbatim from comfy_extras/nodes_post_processing.py.  The entire
        # point of this node is that the numbers do not change, so do not
        # "improve" the arithmetic here.
        samples = image.movedim(-1, 1)
        total = megapixels * 1024 * 1024
        scale_by = math.sqrt(total / (samples.shape[3] * samples.shape[2]))
        width = round(samples.shape[3] * scale_by / resolution_steps) * resolution_steps
        height = round(samples.shape[2] * scale_by / resolution_steps) * resolution_steps
        s = comfy.utils.common_upscale(samples, int(width), int(height), upscale_method, "disabled")
        s = s.movedim(1, -1)
        return (s,)
