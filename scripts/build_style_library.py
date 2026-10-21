#!/usr/bin/env python3
"""Regenerate the bundled style library for the Skutils Style Selector.

Dev-only tool: it reads the installed Clio and OreX packs, merges their
style sets with Clio taking precedence, downscales the thumbnails, and
writes:

    skutils_style_selector/styles.json
    skutils_style_selector/assets/thumbs/*.webp

Usage (from the repo root):

    python scripts/build_style_library.py

WARNING: this rewrites styles.json from the source packs and therefore
discards the hand-curated data currently committed there — the per-style
negative prompts, 40 name normalizations, 5 duplicate removals, the
17-section taxonomy, the hand-added Raja Ravi Varma Style, and the custom
style-named thumbnails.  Re-run it only when intentionally rebuilding the
library, then restore/merge the curation before committing.

Both source roots can be overridden:

    python scripts/build_style_library.py \
        --clio-root  /path/to/clio-style-node \
        --orex-root  /path/to/comfyui-orex

Licensing: Clio's style descriptions were compiled by u/Dear-Spend-2865
(Reddit) and Clio's LICENSE explicitly does not claim them under MIT.
OreX ships no license file.  The Fooocus set (GPL-3.0) is deliberately
excluded.  Credits travel with the generated styles.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - only the thumbnail step needs it
    Image = None
    ImageOps = None


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "skutils_style_selector")
THUMBS_DIR = os.path.join(OUT_DIR, "assets", "thumbs")

DEFAULT_CLIO_ROOT = r"C:\Programs\ComfyDocs\custom_nodes\clio-style-node"
DEFAULT_OREX_ROOT = r"C:\Programs\ComfyDocs\custom_nodes\comfyui-orex"

# OreX style set -> section name in the merged library.  krea2_style is the
# one set that mostly duplicates Clio; only its genuinely new entries are
# kept.  favorite.json / my_styles.json are user data and are ignored.
OREX_SETS = (
    ("krea2_style", "OreX"),
    ("emotions", "Emotion"),
    ("Klein_Edit", "Edit"),
)

THUMB_SIZE = 512
THUMB_QUALITY = 82

CREDITS = {
    "style_texts": (
        "Style descriptions were compiled and shared publicly by "
        "u/Dear-Spend-2865 (Reddit) and are distributed with the Clio Style "
        "Library (clio-style-node, MIT). Clio's LICENSE states that these "
        "descriptions are not claimed under that license."
    ),
    "style_sets": (
        "Clio Style Library styles (clio-style-node), plus the OreX "
        "Cyberpunk, Emotion and Edit sets (comfyui-orex, which ships no "
        "license file)."
    ),
    "excluded": (
        "The Fooocus style set (GPL-3.0) is intentionally not included; the "
        "two Fooocus modifier entries without positive prose are excluded "
        "with it."
    ),
    "generator": "scripts/build_style_library.py",
}


def dedupe_key(name: str) -> str:
    """Name identity used to drop OreX copies of Clio styles."""
    key = re.sub(r"\s+", " ", name.lower().strip())
    return re.sub(r"\s*\(\d+\)$", "", key)


def slugify(text: str, fallback: str = "style") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or fallback


def _unique_thumb_name(name: str, source: str, used: set) -> str:
    base = f"{source}__{slugify(name)}"
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base}-{index}"
        index += 1
    used.add(candidate)
    return candidate + ".webp"


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_clio(root: str):
    """Clio entries in their original order, with gallery thumbnail paths."""
    styles_path = os.path.join(root, "styles.json")
    gallery_path = os.path.join(root, "gallery", "manifest.json")
    styles = _read_json(styles_path)
    if not isinstance(styles, list):
        raise SystemExit(f"{styles_path}: expected a list")

    thumbs = {}
    if os.path.exists(gallery_path):
        manifest = _read_json(gallery_path)
        section = (manifest.get("sections") or {}).get("krea2") or {}
        for image in section.get("images") or []:
            style_name = image.get("style")
            thumb = image.get("thumb") or image.get("file")
            if isinstance(style_name, str) and isinstance(thumb, str):
                thumbs[style_name] = os.path.join(root, "gallery", thumb)

    entries = []
    for style in styles:
        name = style.get("name")
        prompt = style.get("prompt")
        if not isinstance(name, str) or not isinstance(prompt, str):
            continue
        entries.append(
            {
                "name": name,
                "section": style.get("section") or "Styles",
                "prompt": prompt,
                "negative": "",
                "template": None,
                "source": "clio",
                "_thumb_src": thumbs.get(name),
            }
        )
    return entries


def load_orex(root: str, seen_keys: set):
    """OreX sets, keeping only names Clio does not already provide."""
    styles_dir = os.path.join(root, "styles")
    samples_dir = os.path.join(styles_dir, "samples")
    entries = []
    skipped_duplicates = Counter()

    for set_name, section in OREX_SETS:
        path = os.path.join(styles_dir, f"{set_name}.json")
        if not os.path.exists(path):
            print(f"  ! missing OreX set: {path}")
            continue
        data = _read_json(path)
        if not isinstance(data, list):
            print(f"  ! {path}: expected a list, skipped")
            continue
        for style in data:
            name = style.get("name")
            prompt = style.get("prompt")
            if not isinstance(name, str) or not isinstance(prompt, str) or not prompt.strip():
                continue
            key = dedupe_key(name)
            if key in seen_keys:
                skipped_duplicates[set_name] += 1
                continue
            seen_keys.add(key)

            thumbnail = style.get("thumbnail")
            if isinstance(thumbnail, (list, tuple)):
                thumbnail = thumbnail[0] if thumbnail else None
            source = None
            if isinstance(thumbnail, str) and thumbnail:
                source = os.path.join(samples_dir, os.path.basename(thumbnail))

            negative = style.get("negative_prompt")
            if not isinstance(negative, str) or not negative.strip():
                negative = ""

            entries.append(
                {
                    "name": name,
                    "section": section,
                    "prompt": prompt,
                    "negative": negative,
                    # OreX prose already embeds the subject via {prompt}, so
                    # the entry carries its own template instead of using the
                    # node's global wrap template.
                    "template": prompt,
                    "source": "orex",
                    "_thumb_src": source,
                }
            )

    for set_name, count in skipped_duplicates.items():
        print(f"  · {set_name}: dropped {count} duplicate name(s)")
    return entries


def write_thumbnail(source: str, destination: str) -> bool:
    if Image is None:
        raise SystemExit("Pillow is required to build thumbnails (pip install pillow)")
    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "L"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "RGBA":
                    background.paste(image, mask=image.getchannel("A"))
                else:
                    background.paste(image.convert("RGB"))
                image = background
            elif image.mode == "L":
                image = image.convert("RGB")
            image.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
            image.save(destination, "WEBP", quality=THUMB_QUALITY, method=6)
        return True
    except Exception as error:  # noqa: BLE001 - report and keep going
        print(f"  ! thumbnail failed for {source}: {error}")
        return False


def build(clio_root: str, orex_root: str, force: bool) -> int:
    print(f"Clio root: {clio_root}")
    print(f"OreX root: {orex_root}")

    entries = load_clio(clio_root)
    print(f"  · Clio: {len(entries)} styles")

    seen_keys = {dedupe_key(entry["name"]) for entry in entries}
    orex_entries = load_orex(orex_root, seen_keys)
    entries.extend(orex_entries)
    print(f"  · OreX additions: {len(orex_entries)} styles")

    if not entries:
        print("No styles found - aborting.")
        return 1

    os.makedirs(THUMBS_DIR, exist_ok=True)
    used_names = set()
    missing_thumbs = []
    written = 0
    for entry in entries:
        source = entry.pop("_thumb_src", None)
        entry["thumb"] = None
        if not source:
            missing_thumbs.append(entry["name"])
            continue
        if not os.path.exists(source):
            missing_thumbs.append(entry["name"])
            continue
        thumb_name = _unique_thumb_name(entry["name"], entry["source"], used_names)
        destination = os.path.join(THUMBS_DIR, thumb_name)
        if force or not os.path.exists(destination):
            if not write_thumbnail(source, destination):
                missing_thumbs.append(entry["name"])
                continue
            written += 1
        entry["thumb"] = thumb_name

    names = [entry["name"] for entry in entries]
    duplicates = [name for name, count in Counter(names).items() if count > 1]
    if duplicates:
        print(f"Duplicate style names: {duplicates}")
        return 1

    sections = []
    for entry in entries:
        if entry["section"] not in sections:
            sections.append(entry["section"])

    library = {
        "version": 1,
        "credits": CREDITS,
        "sections": sections,
        "styles": entries,
    }
    styles_path = os.path.join(OUT_DIR, "styles.json")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(styles_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(library, handle, ensure_ascii=False, indent=1)
        handle.write("\n")

    total_bytes = os.path.getsize(styles_path)
    for entry in entries:
        if entry["thumb"]:
            total_bytes += os.path.getsize(os.path.join(THUMBS_DIR, entry["thumb"]))

    print()
    print(f"Wrote {styles_path}")
    print(f"  styles:   {len(entries)}")
    print(f"  sections: {len(sections)} -> {', '.join(sections)}")
    print(f"  thumbs:   {len(entries) - len(missing_thumbs)}")
    print(f"  new webp: {written}")
    print(f"  size:     {total_bytes / (1024 * 1024):.1f} MiB")
    if missing_thumbs:
        print(f"  ! no thumbnail ({len(missing_thumbs)}): {missing_thumbs[:10]}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clio-root", default=DEFAULT_CLIO_ROOT)
    parser.add_argument("--orex-root", default=DEFAULT_OREX_ROOT)
    parser.add_argument(
        "--force",
        action="store_true",
        help="rewrite thumbnails that already exist",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.clio_root):
        print(f"Clio root not found: {args.clio_root}")
        return 1
    if not os.path.isdir(args.orex_root):
        print(f"OreX root not found: {args.orex_root}")
        return 1
    return build(args.clio_root, args.orex_root, args.force)


if __name__ == "__main__":
    sys.exit(main())
