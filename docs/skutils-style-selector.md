# Skutils Style Selector

A visual style picker for prompt building: choose one or more styles from a
bundled library of **1,416 styles**, wire the subject in once, and the node
emits the finished **positive** and **negative** prompts plus a
**filename-ready style name**. It combines what the Clio Style Library and
OreX selectors each do well — a large categorized picker, multi-select,
positive *and* negative prompts, and per-style batch runs — and adds a
**user layer** for your own styles, edits and ordering that survives plugin
updates.

## Overview

| | |
|---|---|
| **Python backend** | `skutils_style_selector/` — node, library, HTTP routes |
| **Frontend extension** | `web/skutils_style_selector.js` (picker, node body, editor) |
| **Bundled data** | `skutils_style_selector/styles.json` + `assets/thumbs/*.webp` (read-only) |
| **User data** | `user_styles.json` under ComfyUI's user directory — new styles, overrides of bundled styles, layout |
| **Dependencies** | none beyond ComfyUI itself |

Node name: **Skutils Style Selector** · Category: `skkut-utils` (Nodes → Extensions → skkut-utils)

The bundled library ships **with the repo** — no runtime dependency on Clio
or OreX, and no files are read from other packs. Updating those packs does not
change this node.

Your own changes are never written into `styles.json`. They live in a **user
styles file** under ComfyUI's user directory, which the plugin merges over the
bundled library every time the library is read. A plugin update replaces the
bundled layer only, so your styles and edits survive it.

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
selected styles appear as compact thumbnail cards (150×150 images, with their
selection order) above a **Choose styles…** button. The picker grid displays
each style at 256×256 for close comparison; the selected strip at the top of
the picker uses the same compact 150×150 size. Each node card has a small
**×** button next to the style name to remove that style without opening the
picker.

1. Click **Choose styles…** (or **Edit styles (N)**) on the node.
2. Search by name, section, or prose text; filter by section with the
   dropdown. The 21 sections are: Anime, Cartoon, Comics, Drawing, Painting,
   Digital Painting, Printmaking, Craft & Collage, Photography, Design,
   Cover Art, 3D Render, Sculpture & Toys, Stop-Motion & Puppetry,
   Video Games, Illustration, Character & Creature Design, Emotion, Edit,
   Watercolour, Special Effects.
3. Click tiles to select them. Selection order is preserved — it is the batch
   order and the order prose is joined in combine mode.
4. Reorder selected styles in the strip at the top (drag a chip, or use the
   `‹` / `›` buttons); remove one with `×`.
5. **Apply** — or the round **×** at the top-right of the selected-styles
   strip — writes the ordered selection back into the node and closes the
   picker. **Esc** or a click on the overlay closes without applying;
   **Clear** empties the selection.

Selecting a workflow's saved styles or reopening it restores the selection
from `select_styles` — the picker is only a UI over that widget.

### Section order

The picker groups its tiles by section, and the section order is configurable:

1. Open **Settings → skkut-utils → Style Selector**. The control sits in its
   own group, below the **Features** toggles.
2. Under **Section order**, drag a row (or use its `↑` / `↓` buttons) to move
   that section. The list contains every section in the current library.
3. Changes save automatically; **Reset to default** restores the library order.

The picker grid, the section filter dropdown, and the style editor's section
suggestions all follow this order. Within a section, styles keep the library
order: the bundled order until the [organizer tool](#reorganizing-the-library)
saves an explicit order, after which organizer-listed styles come first in
that order and newly added styles follow in bundled order. Sections that are
not in the saved list — for example a section added by a later repo update —
are appended after the listed ones, so they never disappear. This setting
only changes where sections appear: the **selection order** in the strip still
controls prompt joining and batch order.

The order is stored per user in ComfyUI's normal settings storage (key
`SkkutUtils.StyleSelector.SectionOrder`, a JSON array of section names), so it
is not part of a workflow.

### Modes

- **Combine styles** *(default)* — all selected styles become one prompt. If
  every style is a wrap-style entry, the global `template` is applied **once**
  around all the prose. If any selected style carries its own template (the
  OreX-derived sets), each style is rendered separately with the main prompt
  in the first chunk only, then joined with `", "`.
- **Batch: one run per style** — one positive/negative pair is emitted per
  style, in selection order. The downstream graph runs once per style. This
  is OreX's batch mode. Each run also produces its own enhanced prompt, so
  wire that prompt into **Save Compressed Weppy**'s `enhanced_prompt` input
  (e.g. via [Skutils Text Preview](text-preview.md)) to store the matching
  prompt in each saved image instead of every style's prompt.

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
unchanged; **user styles may add their own**.

Other rules:

- Unknown style names are skipped. If nothing resolves, the node passes the
  base positive/negative through and returns an empty `file_name`.
- A template that does not mention `{prompt}` still gets the main prompt
  appended (separated by `", "`), so the subject cannot be silently
  dropped. OreX behaves the same way.
- Placeholders are substituted in **one pass**, so `{prompt}` inside style
  prose is never expanded recursively.
- Empty results stay `""` (`OUTPUT_IS_LIST` still applies).

## User styles and overrides

Everything you change is stored in a **user styles file**; the bundled
`styles.json` is never written. Three kinds of change live there:

| Change | Stored as |
|---|---|
| A new style | a full entry in `styles` |
| Edits to a bundled style | only the changed fields in `overrides` |
| Order, pins, recategorization | `layout`, written by the [organizer tool](#reorganizing-the-library) |

Because the plugin merges this file over the bundled library at read time, a
plugin update cannot discard it: the update replaces the bundled layer, and
the user layer keeps overriding it.

### Editing a bundled style

Click the pencil on any tile. The editor now opens directly on the bundled
style (there is no clone step). The **name is fixed** for bundled styles,
because workflows refer to styles by name; every other field can be changed:

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Fixed for bundled styles; editable for user styles |
| `section` | no | Defaults to `Custom`; existing sections are offered as suggestions |
| `prompt` | yes | Style prose. `{prompt}` is replaced by the main prompt if you include it |
| `negative` | no | Added to the base negative in every mode |
| `template` | no | Leave empty to use the node's global wrap template. If set, it must contain `{prompt}` (or the main prompt is appended) |
| `thumbnail` | no | `http://` or `https://` URL only (v1 does not upload images); overrides the bundled image |

Saving compares each field with the bundled entry and stores only the
differences. A plugin update that improves a field you did not change still
flows through; a field you did change keeps your value. Saving values equal to
the bundled entry removes the override. **Revert to bundled** (shown while the
style has an override) deletes the override and restores the bundled values.

### Creating a user style

Open the picker → **＋ New style**. The fields are the same as above, with the
name editable. User styles can be renamed, edited and deleted; the picker
updates the node's selection when a selected style is renamed or removed.

Names are unique case-insensitively across the merged library. A user style
whose name matches a bundled style replaces that bundled style; this is what
keeps a renamed/imported style from appearing twice after an update. (The
picker's editor does not create such collisions — it validates new names — but
a hand-edited file may contain one.)

### The user styles file

```
<ComfyUI user directory>/default/skkut_style_selector/user_styles.json
```

For a typical install: `ComfyUI/user/default/skkut_style_selector/user_styles.json`
(ComfyUI Desktop: `<base>/user/default/skkut_style_selector/user_styles.json`).

```json
{
  "version": 1,
  "styles": [
    {"name": "My Style", "section": "Custom", "prompt": "…",
     "negative": "", "template": null, "thumbnail": ""}
  ],
  "overrides": {
    "Anime Style": {"prompt": "…", "section": "Anime"}
  },
  "layout": {
    "sections": ["Anime", "Cartoon", "…"],
    "order": [{"name": "Anime Style", "pinned": true}, {"name": "My Style"}]
  }
}
```

- `overrides` keys are bundled style names; only changed fields are present.
  `template: null` means "no style template"; omit the key to inherit the
  bundled value.
- `layout.sections` is the section order the library is built with. The
  picker's **Settings → skkut-utils → Style Selector → Section order**, if
  customized, still applies on top of it.
- `layout.order` lists styles in display order. Styles not listed — for
  example ones added by a later plugin update — follow in bundled order.
  Listed styles use their explicit `pinned` state; unlisted styles keep their
  bundled state.
- Orphaned entries are harmless: an override or layout entry for a bundled
  style that an update removed is kept in the file but ignored until a style
  with that name exists again.

Writes are atomic (temporary file + `os.replace`). A **missing** file is an
empty user layer. A **corrupt** file is reported and treated as empty for
reading, but writes refuse to overwrite it, so a broken file is never silently
clobbered.

No restart is needed after a change: the node reads the merged library on
every execution, and the picker fetches it every time it opens.

#### Legacy custom styles

Older versions stored custom styles in `custom_styles.json` in the same
directory. If `user_styles.json` does not exist, the legacy file is read as the
user layer. The first save from the picker or the organizer writes
`user_styles.json` containing everything from the legacy file; the legacy file
is left untouched.

## Reorganizing the library

`tools/reorganize_styles.py` is a local editor for the user layer's `layout`
and section assignments. It is not part of the plugin package; it reads the
bundled `styles.json` (read-only) plus your user file and shows the merged
result.

```bash
python tools/reorganize_styles.py
# auto-detects the user directory; otherwise:
python tools/reorganize_styles.py --user-styles "C:/ComfyUI/user/default/skkut_style_selector/user_styles.json"
```

Options: `--port N` (default 8765, `0` = random), `--library PATH` (the
bundled file to read; default `skutils_style_selector/styles.json`, never
written), `--user-styles PATH`, `--no-browser`.

It serves a page on `127.0.0.1` only, with a per-run token in the printed URL.
Drag styles by their grip, pin them, move them between sections (a bundled
style's recategorization becomes a `section` override), and save. Saving
writes **only** `user_styles.json` — `styles.json` is byte-for-byte
untouched — with a timestamped backup in a `backups/` folder next to the user
file. The organizer cannot edit prompts or create styles; use the picker's
editor for those.

Reopen the picker in ComfyUI to see the new order; no restart is needed. For
development, when running from a separate checkout (so the auto-detected
`user/` folder is not the one ComfyUI uses), pass `--user-styles` explicitly.

## Bundled library

Originally generated by `scripts/build_style_library.py` (dev-only; excluded
from the published package) from installed Clio/OreX packs, then curated,
then merged with the curated Classified set by
`scripts/merge_classified_styles.py`:

| Source | Styles |
|---|---|
| Clio Style Library | 410 |
| OreX `emotions` | 7 |
| OreX `Klein_Edit` | 16 |
| Classified set (u/Dear-Spend-2865) | 982 |
| Hand-added | 1 |
| **Total** | **1,416** |

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
updated source). A later merge imported 982 styles from the curated Classified
set, which also added the Watercolour and Special Effects sections, for
**1,416 styles across 21 sections**. Thumbnails are 512 px WebP
(`assets/thumbs/`, committed with the library), and every bundled style has
one. The 1,400 text-to-image styles — including the hand-added Raja Ravi Varma
Style and the imported set — use purpose-generated previews named after the
style (`Anime_Style.webp`); the 16 Edit styles keep their original images.
Previews are re-encoded from their generated source images, so they carry
**no embedded workflow/prompt metadata**.

**Regeneration warning:** re-running `build_style_library.py` rebuilds the raw
generated library and **discards the curation** above (negative prompts,
renames, removals, section changes, the hand-added `Raja Ravi Varma Style`)
as well as any later import, custom thumbnails and filenames, restoring the
upstream Clio/OreX images. Only do that if you intend to redo the review, then
restore the curated data or merge the new source styles into it. Re-running
`merge_classified_styles.py` writes `styles2.json` for comparison and does not
modify the live library.

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
| `GET /skutils_style_selector/library` | Merged bundled + user library (`version`, `thumb_version`, `credits`, `sections`, `styles`) |
| `GET /skutils_style_selector/thumb?name=…` | A bundled thumbnail, looked up **by style name**; the stored filename is containment-checked against the thumbs directory |
| `POST /skutils_style_selector/custom` | `{"action": "save"\|"delete", …}` — save a user style (`style`, `original_name`), save an override of a bundled style (`style`, `override_name`), delete a user style or revert an override (`name`); returns the updated library |

Nothing in these routes writes `styles.json`; every change goes to
`user_styles.json` (or the legacy file until the first save migrates it).
Name/text/section lengths are capped (120 / 20 000 / 60 characters), and
user thumbnails must be `http(s)` URLs. Bundled styles cannot be renamed.

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
- `skutils_style_selector/library.py` — bundled library cache, user-layer
  parsing/validation/merge, override diffs, layout application, thumbnail
  containment.
- `skutils_style_selector/routes.py` — the three aiohttp endpoints.
- `skutils_style_selector/__init__.py` — node mappings + guarded route import.
- `skutils_style_selector/styles.json`, `assets/thumbs/*.webp` — bundled data.
- `web/skutils_style_selector.js` — node-body chips, picker modal, style
  editor (user styles and bundled overrides).
- `scripts/build_style_library.py` — generator for the bundled library.
- `scripts/merge_classified_styles.py` — comparison merge for the Classified
  set (`styles2.json`; never edits the live library).
- `tools/reorganize_styles.py` — local organizer for the user layer's layout
  and sections.
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
| Tiles are blank colored squares with initials | The entry has no thumbnail, or its file is missing from `assets/thumbs/`. Restore the bundled file, or open the style in the editor and set a thumbnail URL. Do **not** blindly re-run the generator — it rebuilds the raw library and discards the curation |
| A selected chip has a dashed outline | The name is not in the library — a user style was renamed/deleted, or the workflow came from a different library. Reselect it |
| Choosing two styles runs the graph twice | `batch_mode` is on. Turn it off (Combine styles) for a single prompt |
| The main prompt disappeared | Check the advanced `template`: it must contain `{prompt}`; if it doesn't, the main prompt is appended at the end instead. A style's own template takes precedence over the node template |
| The Name field is disabled when editing a bundled style | By design: workflows refer to styles by name, so a bundled name is fixed. Edit the other fields (stored as an override), or create a new user style with a different name |
| My edits/order vanished after a plugin update | They should not — they are in `user_styles.json`, which plugin updates never touch. Check that the file exists under ComfyUI's user directory and is valid JSON. A corrupt file is reported in the ComfyUI console and treated as empty for reading (writes refuse to overwrite it); fix it or restore a backup from the `backups/` folder next to it |
| Style save fails with *already exists* | Names are unique case-insensitively across bundled + user styles. Bundled styles are edited in place (their name is fixed); pick a different name for a new style |
| Save fails with *user directory unavailable* | ComfyUI's `folder_paths` exposes neither `get_user_directory()` nor `base_path`, so the user styles file cannot be located. Check the ComfyUI installation |
| Organizer changes do not appear in the picker | Reopen the picker — it fetches the library on every open. No restart is needed. If **Settings → skkut-utils → Style Selector → Section order** is customized, it overrides the saved section order (within-section order and pins still apply) |
| Organizer says it cannot find the user directory | Running from a separate checkout, the auto-detection cannot see ComfyUI's `user/` folder. Pass `--user-styles "<ComfyUI>/user/default/skkut_style_selector/user_styles.json"` |
| `file_name` is empty | No selected name resolved against the library (or `select_styles` is empty) |
| `template` shows a JSON array such as `["Ghibli Style"]` | The workflow was saved by an older build where `positive`/`negative` were widgets, so the saved values were applied to the wrong widgets. Loading the node repairs it: the selection is recovered from the shifted value, batch mode is recovered from the old saved value, and `template` resets to the default (a custom template from before the shift cannot be recovered). Re-save the workflow |
| Old UI or old thumbnails after updating the repo | Hard-refresh the browser (Ctrl+F5) so ComfyUI reloads `web/skutils_style_selector.js`; restart ComfyUI for the Python side. Thumbnail URLs embed a fingerprint of the bundled files (`thumb_version`), so replaced images bypass the browser's 24-hour image cache on the next load — a stale thumbnail that survives that points to an old frontend bundle |

## Installation

This feature ships as part of the unified `ComfyUI-skkut-utils` repo — see the
[root README](../README.md). Restart ComfyUI after installing or updating.
