"""Merge the curated Classified_Styles file into the bundled library.

Produces ``skutils_style_selector/styles2.json`` for manual comparison. The
runtime library remains ``styles.json``; this script never modifies it.

Within each section the existing styles come first (in their original order),
followed by the Classified_Styles additions. Any style without a usable
thumbnail is pointed at ``placeholder.webp`` in ``assets/thumbs``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_EXISTING = os.path.join(ROOT, "skutils_style_selector", "styles.json")
DEFAULT_CLASSIFIED = os.path.join(ROOT, "scripts", "classified_styles_v18_curated.json")
DEFAULT_OUTPUT = os.path.join(ROOT, "skutils_style_selector", "styles2.json")
DEFAULT_THUMBS = os.path.join(ROOT, "skutils_style_selector", "assets", "thumbs")

# Existing sections in their current order, with the two new sheet-only
# sections inserted before the utility Emotion/Edit sections.
MERGED_SECTION_ORDER = (
    "Anime",
    "Cartoon",
    "Comics",
    "Drawing",
    "Painting",
    "Digital Painting",
    "Printmaking",
    "Craft & Collage",
    "Photography",
    "Design",
    "Cover Art",
    "3D Render",
    "Sculpture & Toys",
    "Stop-Motion & Puppetry",
    "Video Games",
    "Illustration",
    "Character & Creature Design",
    "Emotion",
    "Edit",
)


def load_library(path: str, label: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        raise ValueError(f"could not read {label} {path}: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("styles"), list):
        raise ValueError(f"{label} {path} has no styles list")
    for style in data["styles"]:
        if not isinstance(style, dict):
            raise ValueError(f"{label} {path} contains a non-object style")
        if not isinstance(style.get("name"), str) or not style["name"].strip():
            raise ValueError(f"{label} {path} contains a style without a name")
        if not isinstance(style.get("section"), str) or not style["section"].strip():
            raise ValueError(f"{path} style {style['name']!r} has no section")
        if not isinstance(style.get("prompt"), str) or not style["prompt"].strip():
            raise ValueError(f"{path} style {style['name']!r} has no prompt")
    return data


def group_by_section(styles: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for style in styles:
        grouped.setdefault(style["section"], []).append(style)
    return grouped


def merge(existing: dict, classified: dict, thumbs_dir: str, placeholder: str) -> tuple[dict, dict]:
    placeholder_path = os.path.join(thumbs_dir, placeholder)
    if not os.path.isfile(placeholder_path):
        raise ValueError(f"placeholder thumbnail not found: {placeholder_path}")

    existing_groups = group_by_section(existing["styles"])
    classified_groups = group_by_section(classified["styles"])

    unknown = (set(existing_groups) | set(classified_groups)) - set(MERGED_SECTION_ORDER)
    if unknown:
        raise ValueError(
            "section order is missing: " + ", ".join(sorted(unknown))
        )

    merged_styles: list[dict] = []
    for section in MERGED_SECTION_ORDER:
        for source_style in existing_groups.get(section, []):
            merged_styles.append(dict(source_style))
        for source_style in classified_groups.get(section, []):
            merged_styles.append(dict(source_style))

    placeholder_count = 0
    for style in merged_styles:
        thumb = style.get("thumb")
        thumb_path = os.path.join(thumbs_dir, thumb) if isinstance(thumb, str) else ""
        if not isinstance(thumb, str) or not thumb or not os.path.isfile(thumb_path):
            style["thumb"] = placeholder
            placeholder_count += 1

    names = set()
    for style in merged_styles:
        key = style["name"].casefold()
        if key in names:
            raise ValueError(f"duplicate merged style name: {style['name']!r}")
        names.add(key)

    used_sections = [
        section
        for section in MERGED_SECTION_ORDER
        if any(style["section"] == section for style in merged_styles)
    ]

    credits = dict(existing.get("credits") or {})
    classified_credits = classified.get("credits") or {}
    for key, source_key in (
        ("classified_styles_texts", "style_texts"),
        ("classified_styles_source", "source"),
        ("classified_styles_cleaning", "cleaning"),
        ("classified_styles_filtering", "filtering"),
        ("classified_styles_sections", "sections"),
        ("classified_styles_negatives", "negatives"),
        ("classified_styles_generator", "generator"),
    ):
        value = classified_credits.get(source_key)
        if isinstance(value, str) and value:
            credits[key] = value
    credits["merge"] = (
        "styles2.json is a manual-comparison merge of styles.json and "
        "classified_styles_v18_curated.json. Existing styles are followed by "
        "Classified_Styles additions within each section; styles without a "
        f"thumbnail use {placeholder}."
    )

    data = {
        "version": existing.get("version", 1),
        "credits": credits,
        "sections": used_sections,
        "styles": merged_styles,
    }
    stats = {
        "existing": len(existing["styles"]),
        "classified": len(classified["styles"]),
        "merged": len(merged_styles),
        "sections": len(used_sections),
        "placeholder_thumbs": placeholder_count,
        "counts": Counter(style["section"] for style in merged_styles),
    }
    return data, stats


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge styles.json with the curated Classified_Styles file into "
            "styles2.json for manual comparison; never writes styles.json."
        )
    )
    parser.add_argument("--existing", default=DEFAULT_EXISTING)
    parser.add_argument("--classified", default=DEFAULT_CLASSIFIED)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--thumbs-dir", default=DEFAULT_THUMBS)
    parser.add_argument(
        "--placeholder",
        default="placeholder.webp",
        help="thumbnail filename used for styles with no usable image",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare with the existing output file instead of writing",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        existing = load_library(args.existing, "existing library")
        classified = load_library(args.classified, "classified library")
        data, stats = merge(
            existing, classified, args.thumbs_dir, args.placeholder
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(
        "existing: {existing} | classified: {classified} | merged: {merged} | "
        "sections: {sections} | placeholder thumbs: {placeholder_thumbs}".format(
            **stats
        )
    )
    for section in data["sections"]:
        print(f"  {section:32} {stats['counts'][section]:3}")

    generated = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    if args.check:
        try:
            with open(args.output, encoding="utf-8") as handle:
                actual = handle.read()
        except OSError as error:
            print(f"error: could not read {args.output}: {error}", file=sys.stderr)
            return 1
        if actual != generated:
            print(
                f"error: {args.output} does not match the merged output",
                file=sys.stderr,
            )
            return 1
        return 0

    with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(generated)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
