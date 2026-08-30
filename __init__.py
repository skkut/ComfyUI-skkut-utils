"""
ComfyUI-skkut-utils — a collection of small utilities for ComfyUI.

Features
--------
- auto_dark_mode        — detects the OS colour-scheme and switches the
  ComfyUI theme to match in real time (browser + ComfyUI Desktop).
- detailed_jobstatus    — floating execution timer (MM:SS) shown while a
  job runs, from actual execution start (web-only feature).
- save_compressed_weppy — saves images as compressed WebP with embedded
  prompt/workflow metadata: a custom node plus a right-click
  "Save Compressed Weppy" context-menu entry.
- resolution_calculator — "Skutils Resolution Calculator" node: aspect-ratio
  preset (20 options) + megapixel dropdown (0.5–5.0 MP) → width/height.

Layout
------
- Each feature is a self-contained subpackage (e.g. auto_dark_mode/).
- Frontend extensions live in web/ (one file per feature) and are exposed
  to ComfyUI via the single WEB_DIRECTORY below.
- Per-feature documentation: docs/<feature>.md
"""

from . import auto_dark_mode  # noqa: F401  (registers HTTP routes, starts theme polling)
from . import detailed_jobstatus  # noqa: F401  (web-only feature)
from . import save_compressed_weppy  # noqa: F401  (registers node + /save_compressed_weppy route)
from . import resolution_calculator  # noqa: F401  (registers node mapping)

from .save_compressed_weppy import (
    NODE_CLASS_MAPPINGS as _SAVE_COMPRESSED_WEPPY_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as _SAVE_COMPRESSED_WEPPY_DISPLAY_MAPPINGS,
)
from .resolution_calculator import (
    NODE_CLASS_MAPPINGS as _RESOLUTION_CALCULATOR_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as _RESOLUTION_CALCULATOR_DISPLAY_MAPPINGS,
)

NODE_CLASS_MAPPINGS = {
    **_SAVE_COMPRESSED_WEPPY_CLASS_MAPPINGS,
    **_RESOLUTION_CALCULATOR_CLASS_MAPPINGS,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    **_SAVE_COMPRESSED_WEPPY_DISPLAY_MAPPINGS,
    **_RESOLUTION_CALCULATOR_DISPLAY_MAPPINGS,
}

WEB_DIRECTORY = "./web"

__all__ = ["WEB_DIRECTORY", "NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
