"""
Skutils Text Preview — node implementation.

A text display node that does what the built-in display-only text nodes
don't: the text it shows is stored in the saved workflow JSON.

Any input type
--------------
The ``text`` port is a wildcard (``"*"``), so any output in the graph can
be connected — not just STRING.  Whatever arrives is converted to
displayable text before it is shown or stored:

* strings are shown as-is;
* booleans, numbers and ``None`` use their Python text form;
* tensors / arrays are summarised by shape, dtype and device instead of
  being dumped value-by-value (an IMAGE or LATENT would otherwise produce
  a gigantic string);
* dicts, lists, tuples and sets are pretty-printed, with nested arrays
  summarised, huge containers capped and nesting depth limited;
* any other object falls back to a (truncated) ``repr()``.

Why a frontend extension is needed
----------------------------------
ComfyUI serializes *widget values* into the workflow JSON when you save.
The built-in text-preview nodes never rely on that — their display
widgets are marked ``serialize: false`` and are filled from execution
output at runtime, so nothing survives a save/reload.

This node's input is a port-only wildcard input (no widget of its own,
same idea as the built-in "Preview Any").  web/text_preview.js is the
display half: after each run it copies the executed text into a real,
serialized multiline widget (ComfyWidgets["STRING"]), and when a saved
workflow is loaded it rebuilds that widget from the stored value.  The
widget value — what you see — is therefore what a workflow save writes
to the JSON, and what a workflow load restores.

The input is optional.  An unconnected ``text`` port (or an upstream
empty string) makes the next run clear the displayed widget instead of
failing prompt validation, so a preview left over from an earlier run
does not masquerade as the current one.

The node also exposes the text it displays as a ``STRING`` output.  That
lets a save node (e.g. Save Compressed Weppy) store the *corresponding*
prompt in each saved image's embedded workflow when a batch run produces
one prompt per style, rather than every prompt from the batch.
"""

import pprint

try:
    import numpy as _np
except Exception:  # pragma: no cover - ComfyUI always has numpy
    _np = None

try:
    import torch as _torch
except Exception:  # pragma: no cover - ComfyUI always has torch
    _torch = None

# Converting an arbitrary object cannot be unbounded: an IMAGE tensor or a
# deeply nested structure would generate megabytes of text and bloat the
# workflow JSON that stores it.
_MAX_DEPTH = 6
_MAX_ITEMS = 200
_MAX_REPR = 2000


class _Summary:
    """Already-formatted text, printed unquoted inside containers."""

    __slots__ = ("text",)

    def __init__(self, text):
        self.text = text

    def __repr__(self):
        return self.text


def _binary_text(value):
    try:
        return bytes(value).decode("utf-8")
    except UnicodeDecodeError:
        return f"<{len(value)} bytes of binary data>"


def _is_np_scalar(value):
    return _np is not None and isinstance(value, _np.generic)


def _looks_like_array(value):
    """True for torch tensors, numpy arrays and similar shaped data."""
    if _torch is not None and isinstance(value, _torch.Tensor):
        return True
    if _np is not None and isinstance(value, _np.ndarray):
        return True
    shape = getattr(value, "shape", None)
    if shape is None or isinstance(shape, (str, bytes)):
        return False
    try:
        return len(shape) > 0 and getattr(value, "dtype", None) is not None
    except TypeError:
        return False


def _describe_array(value):
    parts = []
    shape = getattr(value, "shape", None)
    if shape is not None:
        try:
            parts.append("shape=(" + ", ".join(str(d) for d in shape) + ")")
        except TypeError:
            pass
    dtype = getattr(value, "dtype", None)
    if dtype is not None:
        parts.append(f"dtype={dtype}")
    device = getattr(value, "device", None)
    if device is not None:
        parts.append(f"device={device}")
    return f"{type(value).__name__}({', '.join(parts)})"


def _safe_repr(value):
    try:
        text = repr(value)
    except Exception as exc:  # a bad __repr__ must not break the node
        return f"<{type(value).__name__}: repr() failed: {exc}>"
    if len(text) > _MAX_REPR:
        text = text[:_MAX_REPR] + f"… (truncated, {len(text)} characters)"
    return text


def _sanitize_mapping(value, depth):
    result = {}
    for index, (key, item) in enumerate(value.items()):
        if index >= _MAX_ITEMS:
            result["..."] = f"({len(value) - _MAX_ITEMS} more items omitted)"
            break
        result[str(key)] = _sanitize(item, depth + 1)
    return result


def _sanitize_sequence(value, depth):
    items = []
    for item in value:
        if len(items) >= _MAX_ITEMS:
            try:
                omitted = len(value) - _MAX_ITEMS
                items.append(_Summary(f"... ({omitted} more items omitted)"))
            except TypeError:
                items.append(_Summary("..."))
            break
        items.append(_sanitize(item, depth + 1))

    if isinstance(value, tuple):
        return tuple(items)
    if isinstance(value, frozenset):
        return frozenset(items)
    if isinstance(value, set):
        return set(items)
    return items


def _sanitize(value, depth):
    """Turn ``value`` into something ``pprint`` can render compactly."""
    if value is None or isinstance(value, (bool, int, float, complex, str)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return _Summary(_binary_text(value))
    if _is_np_scalar(value):
        return _Summary(str(value.item()))
    if _looks_like_array(value):
        return _Summary(_describe_array(value))
    if isinstance(value, dict):
        if depth >= _MAX_DEPTH:
            return _Summary(f"<dict (max depth {_MAX_DEPTH})>")
        return _sanitize_mapping(value, depth)
    if isinstance(value, (list, tuple, set, frozenset)):
        if depth >= _MAX_DEPTH:
            return _Summary(f"<{type(value).__name__} (max depth {_MAX_DEPTH})>")
        return _sanitize_sequence(value, depth)
    return _Summary(_safe_repr(value))


def _convert(value):
    if isinstance(value, str):
        return value
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float, complex)):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return _binary_text(value)
    if _is_np_scalar(value):
        return str(value.item())
    if _looks_like_array(value):
        return _describe_array(value)
    if isinstance(value, (dict, list, tuple, set, frozenset)):
        try:
            return pprint.pformat(
                _sanitize(value, 0), width=100, compact=True, sort_dicts=False
            )
        except Exception:
            return _safe_repr(value)
    return _safe_repr(value)


def to_text(value):
    """Convert any node output value to the text shown in the preview."""
    try:
        return _convert(value)
    except Exception as exc:  # never fail a run because of the preview
        return f"<unable to convert {type(value).__name__} to text: {exc}>"


class SkutilsTextPreview:
    """Show ``text`` in the node and keep it in the saved workflow.

    The wildcard input is optional: when it is unconnected (or an empty
    string), a run clears the displayed text instead of failing prompt
    validation.  Any connected value is converted to text.  The displayed
    text lives in a serialized widget, so a workflow save writes it to the
    JSON and a load restores it without a re-run.

    The same converted text is also returned as a ``STRING`` output, so a
    downstream save node can embed the prompt that produced each image
    (in batch mode the output is one string per execution, in order).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "optional": {
                "text": (
                    "*",
                    {
                        "forceInput": True,
                        "tooltip": (
                            "Any value to display. Strings are shown as-is, "
                            "numbers and booleans converted to text, tensors/"
                            "arrays as a shape + dtype summary, and dicts/lists "
                            "pretty-printed. The converted text shown after a "
                            "run is stored in the node and saved with the "
                            "workflow JSON. Leave unconnected to clear the "
                            "preview on the next run."
                        ),
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "preview"
    OUTPUT_NODE = True
    CATEGORY = "skkut-utils"

    def preview(self, text=None):
        # The UI payload is picked up by web/text_preview.js, which stores
        # it in a serialized widget so it survives a workflow save.  An
        # empty list tells the frontend to remove the display widget when
        # nothing was received.
        converted = "" if text is None else to_text(text)
        return {
            "ui": {"text": [] if text is None else [converted]},
            # The same text is exposed as an output for save nodes that
            # want to embed the prompt of the image they are saving.
            "result": (converted,),
        }
