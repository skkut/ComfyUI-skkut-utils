# Skutils Style Selector

A visual style picker for prompt building: choose one or more styles from a
bundled library of **434 styles**, wire the subject in once, and the node emits
the finished **positive** and **negative** prompts plus a **filename-ready
style name**. It combines what the Clio Style Library and OreX selectors each
do well — a large categorized picker, multi-select, positive *and* negative
prompts, and per-style batch runs — and adds an in-panel editor for your own
custom styles.

## Overview

| | |
|---|---|
| **Python backend** | `skutils_style_selector/` — node, library, HTTP routes |
| **Frontend extension** | `web/skutils_style_selector.js` (picker, node body, editor) |
| **Bundled data** | `skutils_style_selector/styles.json` + `assets/thumbs/*.webp` |
| **Dependencies** | none beyond ComfyUI itself |

Node name: **Skutils Style Selector** · Category: `utils/style`

The library is **fully bundled with the repo** — no runtime dependency on
Clio or OreX, and no files are read from other packs. Updating those packs
does not change this node; updating *this* repo does.

## Node configuration

| Input | Type | Default | Description |
|---|---|---|---|
| `positive` | STRING input socket *(optional)* | `""` | Main prompt. Connect a text/String output — the node deliberately has no text widget for it |
| `negative` | STRING input socket *(optional)* | `""` | Base negative prompt. Connect a text/String output; per-style negatives are appended to it |
| `select_styles` | STRING (hidden) | `"[]"` | JSON array of selected style names. Managed by the picker; the frontend hides the raw widget. A headless client may write `["Anime Style", "Film Noir"]` or a comma-separated list |
| `batch_mode` | BOOLEAN | `False` | `Combine styles` (one prompt) vs `Batch: one run per style` (one output pair per style) |
| `template` | STRING *(advanced)* | `Style: {name}: {style}. Subject: {prompt}` | Wrap template for styles without their own template. Placeholders: `{name}`, `{style}`, `{prompt}` |

| Output | Description |
|---|---|
| `positive` | Finished positive prompt(s) |
| `negative` | Finished negative prompt(s) |
| `file_name` | Filename-safe style name, e.g. `Anime_Style`; `Anime_Style_Film_Noir` in combine mode; empty with no selection |

All three outputs use `OUTPUT_IS_LIST`, matching OreX's mechanism: combine
mode and the no-selection case return one-item lists, batch mode returns one
item per selected style, and ComfyUI fans the graph out into **one downstream
run per style** (the same behavior as OreX's batch mode).

## Using the picker

The `select_styles` widget is hidden and replaced by a small panel: the
selected styles appear as thumbnail cards (the same 124×112 tiles as the
picker strip, with their selection order) above a **Choose styles…** button.

1. Click **Choose styles…** (or **Edit styles (N)**) on the node.
2. Search by name, section, or prose text; filter by section with the
   dropdown. The 17 sections are: Anime, Cartoon, Comics, Drawing, Painting,
   Digital Painting, Printmaking, Craft & Collage, Photography, Design,
   Cover Art, 3D Render, Sculpture & Toys, Stop-Motion & Puppetry,
   Video Games, Emotion, Edit.
3. Click tiles to select them. Selection order is preserved — it is the batch
   order and the order prose is joined in combine mode.
4. Reorder selected styles in the strip at the top (drag a chip, or use the
   `‹` / `›` buttons); remove one with `×`.
5. **Apply** writes the ordered selection back into the node. **Esc** or the
   overlay closes without applying; **Clear** empties the selection.

Selecting a workflow's saved styles or reopening it restores the selection
from `select_styles` — the picker is only a UI over that widget.

### Modes

- **Combine styles** *(default)* — all selected styles become one prompt. If
  every style is a wrap-style entry, the global `template` is applied **once**
  around all the prose. If any selected style carries its own template (the
  OreX-derived sets), each style is rendered separately with the main prompt
  in the first chunk only, then joined with `", "`.
- **Batch: one run per style** — one positive/negative pair is emitted per
  style, in selection order. The downstream graph runs once per style. This
  is OreX's batch mode.

### Examples

With `positive = "a photo of a cat"`:

| Selection / mode | Positive result |
|---|---|
| `Anime Style`, combine | `Style: Anime Style: A clean, expressive illustration… . Subject: a photo of a cat` |
| `Anime Style` + `Film Noir (2)`, combine | `Style: Anime Style, Film Noir (2): <anime prose>, <noir prose>. Subject: a photo of a cat` |
| `Happiness` (OreX), either mode | `a photo of a cat Happiness: Muscles involved…` — its own inline template already places the prompt |
| `Anime Style` + `Happiness`, combine | One template around the anime prose, then the Happiness prose; the subject appears only once |
| Two styles, batch | Two outputs; each rendered with the subject, in selection order |

Negatives are joined from the base `negative` plus each entry's own negative,
de-duplicated case-insensitively and separated by `", "`. The bundled sets
ship no non-empty negatives (OreX's own sets store a blank `negative_prompt`
for every entry), so with a stock library the base negative passes through
unchanged; **custom styles may add their own**.

Other rules:

- Unknown style names are skipped. If nothing resolves, the node passes the
  base positive/negative through and returns an empty `file_name`.
- A template that does not mention `{prompt}` still gets the main prompt
  appended (separated by `", "`), so the subject cannot be silently
  dropped. OreX behaves the same way.
- Placeholders are substituted in **one pass**, so `{prompt}` inside style
  prose is never expanded recursively.
- Empty results stay `""` (`OUTPUT_IS_LIST` still applies).

## Custom styles

Open the picker → **＋ New style**. Fields:

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Must not collide (case-insensitively) with a bundled or custom style |
| `section` | no | Defaults to `Custom`; existing sections are offered as suggestions |
| `prompt` | yes | Style prose. `{prompt}` is replaced by the main prompt if you include it |
| `negative` | no | Added to the base negative in every mode |
| `template` | no | Leave empty to use the node's global wrap template. If set, it must contain `{prompt}` (or the main prompt is appended) |
| `thumbnail` | no | `http://` or `https://` URL only (v1 does not upload images) |

Bundled entries show a pencil button that **clones** them into a custom style
(name suffixed with `(custom)`) instead of editing the read-only data. Custom
entries can be edited, renamed and deleted; the picker updates the node's
selection when a selected style is renamed or removed.

Custom styles are stored per user, outside the workflow:

```
<ComfyUI user directory>/default/skkut_style_selector/custom_styles.json
```

```json
{"version": 1, "styles": [
  {"name": "My Style", "section": "Custom", "prompt": "…",
   "negative": "", "template": null, "thumbnail": "https://…"}
]}
```

Writes are atomic (`os.replace`); a missing or corrupt file is treated as an
empty custom library, never an error. Custom styles survive repo updates and
are separate from workflow JSON — editing one changes how every workflow that
names it renders.

## Bundled library

Originally generated by `scripts/build_style_library.py` (dev-only; excluded
from the published package) from installed Clio/OreX packs, then curated and
committed:

| Source | Styles |
|---|---|
| Clio Style Library | 410 |
| OreX `emotions` | 7 |
| OreX `Klein_Edit` | 16 |
| Hand-added | 1 |
| **Total** | **434** |

The curation pass made the following changes to the generated data:

- **Added one style by hand** — `Raja Ravi Varma Style` (Painting), with a
  supplied oil-painting prompt, a bespoke negative, and a generated preview.
- **Removed 5 duplicate/corrupt entries** — OreX `Cyberpunk` (duplicate of
  `Cyberpunk: Edgerunners Style`), `Toon Shader` (duplicate of `Cel Shading`),
  `Beatrix Potter Style (2)` (corrupted duplicate), `Cross Process
  Photography` and `Modern Lithography` (near-duplicates of their
  `Cross-Processed` / `Contemporary` counterparts).
- **Normalized 40 names** — casing/typo fixes, clearer titles, and verb-first
  names for the Edit nodes.
- **Reorganized sections into 17** — the miscategorized `3D Render` catch-all
  was split into Printmaking, Craft & Collage, Sculpture & Toys,
  Stop-Motion & Puppetry, Video Games and Design; poster styles were
  consolidated under Cover Art.
- **Added a bespoke negative prompt to every style**, targeting what that
  style specifically must avoid. These are appended to the node's base
  negative in `_merge_negative`.

OreX entries whose names duplicate Clio are dropped (Clio is treated as the
updated source). Thumbnails are 512 px WebP (`assets/thumbs/`, ~13 MB total)
and are committed with the library. The 418 text-to-image styles — including
the hand-added Raja Ravi Varma Style — use purpose-generated previews named
after the style (`Anime_Style.webp`). The 16 Edit styles keep their original
OreX images because they require an input image. Previews are re-encoded from
their generated source images, so they carry **no embedded workflow/prompt
metadata**.

**Regeneration warning:** re-running the generator rebuilds the raw
generated library and **discards the curation** above (negative prompts,
renames, removals, section changes, the hand-added `Raja Ravi Varma Style`)
as well as the custom thumbnails and their filenames, restoring the upstream
Clio/OreX images. Only do that if you intend to redo the review, then restore
the curated data or merge the new source styles into it.

```bash
python scripts/build_style_library.py
# optional: --clio-root … --orex-root … --force
```

A missing thumbnail is not fatal — the picker draws a section-colored
typographic tile instead.

## HTTP routes

Registered by `skutils_style_selector/routes.py` when the repo is imported by
ComfyUI:

| Route | Purpose |
|---|---|
| `GET /skutils_style_selector/library` | Merged bundled + custom library (`version`, `thumb_version`, `credits`, `sections`, `styles`) |
| `GET /skutils_style_selector/thumb?name=…` | A bundled thumbnail, looked up **by style name**; the stored filename is containment-checked against the thumbs directory |
| `POST /skutils_style_selector/custom` | `{"action": "save"\|"delete", "style": {…}, "original_name": …}` — validates, writes the custom file, returns the updated library |

Name/text/section lengths are capped (120 / 20 000 / 60 characters), and
custom thumbnails must be `http(s)` URLs. Bundled styles are read-only.

`thumb_version` is a fingerprint of the bundled thumbnail files (names, sizes
and mtimes). The picker appends it to every `/thumb` URL, so replacing an
image changes its URL and invalidates the browser's image cache instead of
serving the previous thumbnail for up to a day.

## Save Compressed Weppy integration

`save_compressed_weppy/download_name.py` has a `SkutilsStyleSelector` reader,
so the right-click **Save Compressed Weppy** download is named after the
selected style(s) — `Anime_Style_kzqrv.webp`, or
`Anime_Style_Film_Noir_kzqrv.webp` in combine mode — exactly like its
existing OreX and Clio readers. See
[Save Compressed Weppy](save-compressed-weppy.md).

## Files

- `skutils_style_selector/skutils_style_selector.py` — the node: selection
  parsing, template rendering, negative merging, batching, filename slugs.
- `skutils_style_selector/library.py` — bundled library cache, custom
  library CRUD/validation, merged lookup, thumbnail containment.
- `skutils_style_selector/routes.py` — the three aiohttp endpoints.
- `skutils_style_selector/__init__.py` — node mappings + guarded route import.
- `skutils_style_selector/styles.json`, `assets/thumbs/*.webp` — bundled data.
- `web/skutils_style_selector.js` — node-body chips, picker modal, custom
  style editor.
- `scripts/build_style_library.py` — generator for the bundled library.
- `save_compressed_weppy/download_name.py` — download-name reader.

## Credits and licensing

The repo itself is [MIT](../LICENSE). The **bundled style descriptions are
third-party content**, credited in `styles.json` and reproduced here:

- Clio Style Library (`clio-style-node`) styles, whose descriptions were
  compiled and shared publicly by **u/Dear-Spend-2865** (Reddit). Clio's
  LICENSE explicitly states that those descriptions are **not** claimed under
  its MIT license.
- OreX (`comfyui-orex`) Emotion and Edit sets. OreX ships no license file.

The **Fooocus style set is deliberately excluded**: it is GPL-3.0, which
would conflict with this repo's MIT license. The two Fooocus modifier entries
without positive prose are excluded with it.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `positive` / `negative` have no text box | By design: they are optional STRING **input sockets**. Connect the output of a text node (or any STRING node) instead of typing into the node |
| Picker says *Could not load styles* | The routes failed to register. Check the ComfyUI console for `skutils-utils.skutils_style_selector`; a `server` import error means ComfyUI's `server` module was unavailable at import time (very old or unusual install) |
| Tiles are blank colored squares with initials | The entry has no thumbnail, or its file is missing from `assets/thumbs/`. Restore the file named by that style's `thumb` field, or clone/add it as a custom style. Do **not** blindly re-run the generator — it rebuilds the raw library and discards the curation |
| A selected chip has a dashed outline | The name is not in the library — a custom style was renamed/deleted, or the workflow came from a different library. Reselect it |
| Choosing two styles runs the graph twice | `batch_mode` is on. Turn it off (Combine styles) for a single prompt |
| The main prompt disappeared | Check the advanced `template`: it must contain `{prompt}`; if it doesn't, the main prompt is appended at the end instead. A custom style's own template takes precedence over the node template |
| Custom style save fails with *already exists* | Names are unique case-insensitively across bundled + custom styles. Clone a bundled style instead of reusing its name |
| Custom style save fails with *user directory unavailable* | ComfyUI's `folder_paths` exposes neither `get_user_directory()` nor `base_path`; the custom library cannot be stored |
| `file_name` is empty | No selected name resolved against the library (or `select_styles` is empty) |
| `template` shows a JSON array such as `["Ghibli Style"]` | The workflow was saved by an older build where `positive`/`negative` were widgets, so the saved values were applied to the wrong widgets. Loading the node repairs it: the selection is recovered from the shifted value, batch mode is recovered from the old saved value, and `template` resets to the default (a custom template from before the shift cannot be recovered). Re-save the workflow |
| Old UI or old thumbnails after updating the repo | Hard-refresh the browser (Ctrl+F5) so ComfyUI reloads `web/skutils_style_selector.js`; restart ComfyUI for the Python side. Thumbnail URLs embed a fingerprint of the bundled files (`thumb_version`), so replaced images bypass the browser's 24-hour image cache on the next load — a stale thumbnail that survives that points to an old frontend bundle |

## Installation

This feature ships as part of the unified `ComfyUI-skkut-utils` repo — see the
[root README](../README.md). Restart ComfyUI after installing or updating.
