"""The Skutils Style Selector node.

Combines a main positive prompt, a base negative, and zero or more entries
from the bundled style library into the positive/negative strings a
text-encoder needs.  Two modes:

  * **Combine** — all selected styles go into one prompt (Clio-style).
  * **Batch** — one output per selected style, so standard ComfyUI list
    fan-out runs the downstream graph once per style (OreX-style).

The selection itself lives in the ``select_styles`` widget as a JSON array.
The frontend hides that widget behind the visual picker; keeping a plain
STRING means an old workflow or a headless client can still drive the node
by writing ``["Anime Style", "Film Noir"]`` (or just ``Anime Style``,
comma-separated).
"""

from __future__ import annotations

import json
import re

try:  # package import inside ComfyUI
    from .library import filename_slug, resolve
except ImportError:  # pragma: no cover - direct import for tests
    from library import filename_slug, resolve

DEFAULT_TEMPLATE = "Style: {name}: {style}. Subject: {prompt}"
DEFAULT_SEPARATOR = ", "
MAX_FILE_NAME = 80

_PLACEHOLDER = re.compile(r"\{(name|style|prompt)\}")


def parse_selection(raw):
    """The selected style names from the ``select_styles`` widget value.

    Accepts a JSON array (of strings or ``{"name": ...}`` objects), a real
    list, or — as a hand-typed fallback — a comma-separated string.
    """
    if isinstance(raw, (list, tuple)):
        items = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, list):
            items = parsed
        else:
            items = [part.strip().strip('"') for part in text.split(",")]

    names = []
    seen = set()
    for item in items:
        if isinstance(item, dict):
            item = item.get("name")
        if not isinstance(item, str):
            continue
        name = item.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _render(template, name, style, prompt):
    """One-pass placeholder substitution in ``template``.

    A one-pass regex (rather than chained ``str.replace``) means braces
    inside the user's prompt are never mistaken for placeholders.
    """
    values = {"name": name, "style": style, "prompt": prompt}
    return _PLACEHOLDER.sub(lambda match: values[match.group(1)], template or "")


def _render_entry(template, name, style, prompt, separator):
    """Render one template, appending an unsubstituted main prompt.

    Mirrors OreX: a template that does not mention ``{prompt}`` still gets
    the subject appended, so style prose can never silently drop it.
    """
    text = _render(template, name, style, prompt).strip()
    prompt = (prompt or "").strip()
    if prompt and "{prompt}" not in (template or ""):
        text = f"{text}{separator}{prompt}" if text else prompt
    return text


def _merge_negative(base, entries):
    """Base negative followed by each entry's own negative, deduplicated."""
    parts = []
    seen = set()
    for text in [base] + [entry.get("negative") for entry in entries]:
        if not isinstance(text, str):
            continue
        part = text.strip()
        if not part:
            continue
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        parts.append(part)
    return ", ".join(parts)


def _combine_prompt(entries, positive, template, separator):
    """The single combined prompt for combine mode."""
    if all(not entry.get("template") for entry in entries):
        # Pure wrap-style selection: one template around all of the prose.
        names = separator.join(entry["name"] for entry in entries)
        styles = separator.join(entry["prompt"].strip() for entry in entries)
        return _render_entry(template, names, styles, positive, separator)

    # A mix (or only inline templates): render each entry, then join.  The
    # main prompt goes into the first chunk only, so the subject is not
    # repeated once per style.
    chunks = []
    for index, entry in enumerate(entries):
        entry_template = entry.get("template")
        if index > 0 and not entry_template:
            chunk = entry["prompt"].strip()
        else:
            chunk = _render_entry(
                entry_template or template,
                entry["name"],
                entry["prompt"],
                positive if index == 0 else "",
                separator,
            )
        if chunk:
            chunks.append(chunk)
    return separator.join(chunks)


def _file_name(names):
    """Filename-friendly slug(s), matching the node's own naming rule."""
    slugs = [filename_slug(name) for name in names]
    slugs = [slug for slug in slugs if slug]
    if not slugs:
        return ""
    if len(slugs) == 1:
        return slugs[0][:MAX_FILE_NAME]
    return "_".join(slugs)[:MAX_FILE_NAME]


class SkutilsStyleSelector:
    """Skutils Style Selector — bundled style picker with positive/negative output."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "select_styles": (
                    "STRING",
                    {
                        "default": "[]",
                        "multiline": False,
                        "dynamicPrompts": False,
                        "tooltip": "JSON array of selected style names (managed by the style picker).",
                    },
                ),
                "batch_mode": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "label_on": "Batch: one run per style",
                        "label_off": "Combine styles",
                        "tooltip": "Batch mode emits one positive/negative pair per selected style, so the downstream graph runs once per style.",
                    },
                ),
                "template": (
                    "STRING",
                    {
                        "multiline": False,
                        "default": DEFAULT_TEMPLATE,
                        "dynamicPrompts": False,
                        "advanced": True,
                        "tooltip": "Wrap template for styles without their own template. Placeholders: {name}, {style}, {prompt}.",
                    },
                ),
            },
            "optional": {
                "positive": (
                    "STRING",
                    {
                        "forceInput": True,
                        "dynamicPrompts": False,
                        "tooltip": "Main subject prompt (connect a text/String output).",
                    },
                ),
                "negative": (
                    "STRING",
                    {
                        "forceInput": True,
                        "dynamicPrompts": False,
                        "tooltip": "Base negative prompt; each selected style may add its own.",
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("positive", "negative", "file_name")
    FUNCTION = "execute"
    CATEGORY = "utils/style"
    OUTPUT_IS_LIST = (True, True, True)

    def execute(self, select_styles="[]", batch_mode=False,
                template=DEFAULT_TEMPLATE, positive="", negative=""):
        positive = positive if isinstance(positive, str) else ""
        negative = negative if isinstance(negative, str) else ""
        separator = DEFAULT_SEPARATOR
        entries = resolve(parse_selection(select_styles))

        if not entries:
            return ([positive], [negative], [""])

        if batch_mode:
            positives = [
                _render_entry(
                    entry.get("template") or template,
                    entry["name"],
                    entry["prompt"],
                    positive,
                    separator,
                )
                for entry in entries
            ]
            negatives = [
                _merge_negative(negative, [entry])
                for entry in entries
            ]
            file_names = [_file_name([entry["name"]]) for entry in entries]
            return (positives, negatives, file_names)

        combined = _combine_prompt(entries, positive, template, separator)
        names = [entry["name"] for entry in entries]
        return (
            [combined],
            [_merge_negative(negative, entries)],
            [_file_name(names)],
        )
