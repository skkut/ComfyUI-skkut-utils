"""Download filename policy for the right-click "Save Compressed Weppy" route.

The context-menu entry (`web/save_compressed_weppy.js`) can only send what the
browser already holds: the image it was opened on, plus the current graph
serialised as an API prompt.  It cannot send any node's *computed* output —
core emits the `executed` websocket event only for nodes that return ui data,
so a node whose output is a plain STRING never publishes its value to the
frontend, and the menu has nothing to read.

Where such a value is meant to name the file — the OreX style selector's
`file_name` output, derived from the selected style's thumbnail — it is
therefore re-derived here from the prompt, which does carry the widget values.
Each supported node class contributes one small reader to `NAME_PROVIDERS`, so
the coupling to a third-party pack's data layout stays in one place, and a pack
that is missing or has changed simply falls back to the default prefix.
"""

import glob
import json
import os
import random
import re

DEFAULT_PREFIX = "ComfyUI_Weppy"

# Same alphabet as SaveCompressedWeppy.prefix_append (sic — the pack has always
# skipped "w"), kept identical so both save paths name files the same way.
_ALPHABET = "abcdefghijklmnopqrstupvxyz"
_SUFFIX_LEN = 5

# A style-set name arrives from the prompt and is used to build a path, so only
# allow characters that cannot escape it: no separators, no glob syntax, and no
# leading dot.
_SAFE_STYLE_SET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]*$")

# The resolved prefix ends up inside a Content-Disposition header.
_UNSAFE_IN_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_SLUG_LEN = 80


def random_suffix():
    """The 5-letter collision-avoidance suffix both save paths append."""
    return "".join(random.choice(_ALPHABET) for _ in range(_SUFFIX_LEN))


def safe_slug(text):
    """Flatten `text` into something safe for a filename and an HTTP header."""
    return _UNSAFE_IN_NAME.sub("_", str(text)).strip("._-")[:_MAX_SLUG_LEN]


def build(prompt=None, ext="webp"):
    """The full download filename, as `<prefix>_<suffix>.<ext>`.

    The prefix comes from the prompt when a supported node supplies one, and
    falls back to `DEFAULT_PREFIX` otherwise — or on any error.  Naming is a
    nicety here; it must never be allowed to fail the save itself.
    """
    try:
        prefix = _resolve_prefix(prompt)
    except Exception:
        prefix = None
    return f"{prefix or DEFAULT_PREFIX}_{random_suffix()}.{ext}"


def _orex_style_name(inputs):
    """Reproduce the `file_name` output of OreX's style selector.

    OreX takes the basename of each selected style's `thumbnail`, drops the
    extension, and joins them with "_" — this returns that same string, so the
    download carries the name the node's own output would have carried.
    """
    styles_set = inputs.get("styles")
    selected = inputs.get("select_styles")
    if selected is None:
        selected = inputs.get("styles_grid")  # extra widget in some builds
    if not styles_set or selected is None:
        return None

    if isinstance(selected, (list, tuple)):
        wanted = [str(value).strip() for value in selected]
    else:
        wanted = [value.strip() for value in str(selected).split(",")]
    wanted = [value for value in wanted if value]
    if not wanted:
        return None

    catalog = _load_catalog(styles_set)
    if not catalog:
        return None

    slugs = []
    for name in wanted:
        entry = catalog.get(name)
        if not isinstance(entry, dict):
            continue
        thumbnail = entry.get("thumbnail")
        if isinstance(thumbnail, (list, tuple)):
            thumbnail = thumbnail[0] if thumbnail else ""
        base = os.path.splitext(os.path.basename(str(thumbnail or "")))[0]
        if base:
            slugs.append(base)
    return "_".join(slugs) if slugs else None


def _load_catalog(styles_set):
    """Load `<styles_set>.json` as `{style name: entry}`, or None.

    OreX keeps its style sets in a `styles/` folder beside the node, but that
    pack's directory name is not ours to assume, so the file is looked up under
    every registered custom_nodes root.
    """
    name = str(styles_set)
    if not _SAFE_STYLE_SET.match(name):
        return None

    try:
        import folder_paths

        roots = folder_paths.get_folder_paths("custom_nodes")
    except Exception:
        return None

    for root in roots:
        for path in sorted(glob.glob(os.path.join(root, "*", "styles", f"{name}.json"))):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, ValueError):
                continue
            if not isinstance(data, list):
                continue
            catalog = {
                entry["name"]: entry
                for entry in data
                if isinstance(entry, dict) and isinstance(entry.get("name"), str)
            }
            if catalog:
                return catalog
    return None


# class_type -> reader(inputs) -> str | None.  Add an entry to teach the
# context menu about another pack's filename output.
NAME_PROVIDERS = {
    "OrexStyleSelector": _orex_style_name,
}


def _resolve_prefix(prompt):
    """First supported node in the prompt that yields a usable name."""
    if not isinstance(prompt, dict):
        return None
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        reader = NAME_PROVIDERS.get(node.get("class_type"))
        if reader is None:
            continue
        try:
            name = reader(node.get("inputs") or {})
        except Exception:
            name = None
        if name:
            slug = safe_slug(name)
            if slug:
                return slug
    return None
