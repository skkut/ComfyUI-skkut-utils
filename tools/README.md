# Reorganize Styles (local tool)

A maintenance utility for the **user layer** of the Skutils Style Selector:
it edits the layout (style order, section order, pins, recategorization) in
your `user_styles.json` under ComfyUI's user directory. The bundled
`skutils_style_selector/styles.json` is read-only.

It is **not** part of the ComfyUI plugin: nothing in the repo imports it and it
is excluded from the Comfy Registry package by `.comfyignore`. It *is* tracked
on GitHub, so anyone cloning the repo can use it.

See also the feature docs: [Skutils Style Selector](../docs/skutils-style-selector.md).

## Run

```bash
python tools/reorganize_styles.py
```

The script prints a URL containing a one-run access token and opens it in your
browser. It binds only to `127.0.0.1`.

It finds the user file through `folder_paths` when available, then through a
`user/` folder next to the checkout's `custom_nodes` parent. Running from a
separate development checkout usually needs the path explicitly:

```bash
python tools/reorganize_styles.py \
  --user-styles "C:/Programs/ComfyDocs/user/default/skkut_style_selector/user_styles.json"
```

Options:

| Option | Meaning |
|---|---|
| `--port N` | Port on `127.0.0.1` (default `8765`; `0` picks a free port) |
| `--library PATH` | Bundled `styles.json` to read (default `skutils_style_selector/styles.json`); never written |
| `--user-styles PATH` | User styles file to edit; created on the first save |
| `--no-browser` | Don't open the browser automatically |

## What it does

- **Reorder styles** inside a section — drag a row by its `⠿` grip, use the
  `↑` / `↓` buttons for single steps, or `⤒` / `⤓` to send a style to the top
  or bottom. The picker shows styles in the saved order within each section.
- **Pin styles to anchor them** — click `📌` on a row. Pinning never changes
  the row's position: pin something in the middle and it stays there. A
  pinned row itself cannot be moved (its grip, `↑`, `↓`, `⤒` and `⤓` are
  disabled). Pinned styles that form the block at the very top of a section
  stay on top: `⤒` on an unpinned style lands directly **below** that block,
  skipping over any anchored styles further down. Click `📌` again to unpin
  (the row stays where it is). Sections with pins show a `📌 N` badge. Pins
  are stored per style in the user file's `layout.order`.
- **Recategorize a style** — use the dropdown on its row. It lists every
  section in the library, plus **＋ New section…** to create one. Moving a
  bundled style stores a `section` override; moving a user style updates its
  entry.
- **Search** by name, section, source, or prompt text, and filter to one
  section. Matches are highlighted (case-insensitively) in each result's
  name, source, prompt, and section header, as well as in the full-size
  preview. Reordering is disabled while a search is active (the visible
  order would be ambiguous); use the `↑` / `↓` buttons or clear the search.
  Editing a bundled style in the picker is shown here as `bundled · edited`.
- **See each style clearly** — every row shows a **300 px thumbnail** and the
  style's **full prompt text**, with no truncation. Click any thumbnail (or
  focus it and press Enter/Space) to open the **full-size preview** at the
  image's native 512 px; the preview also shows the complete prompt. Use
  `←` / `→` (or the side arrows) to browse the currently visible list, and
  `Esc`, the `×`, or the backdrop to close.

The organizer edits organisation only. Create styles and change prompts,
negatives, templates, or thumbnails in the picker's editor inside ComfyUI.

## Saving

**Save** (or Ctrl+S) writes **only** `user_styles.json`, atomically. Before
each write, the old user file is copied to a `backups/` folder next to it as
`user-styles-<timestamp>.json`; the newest 20 backups are kept. The bundled
`styles.json` is never modified — open the file before and after a save and it
is byte-for-byte identical.

Reopen the picker in ComfyUI to see the changes: it fetches the merged library
on every open and the node reads it on every execution, so **no ComfyUI
restart is needed**.

Notes:

- If only the legacy `custom_styles.json` exists, it is read as the user
  layer; the first save migrates everything into `user_styles.json` and leaves
  the legacy file untouched.
- A corrupt user file is reported and refused, never overwritten. Fix the JSON
  or restore a backup.
- Orphaned layout entries (for styles removed by a plugin update) are kept in
  the file but ignored.
- `scripts/build_style_library.py` rewrites the bundled `styles.json` from the
  source packs. Your user-layer order, pins, overrides and styles survive
  that rebuild; the bundled order they were based on may change.

## Safety

- Binds only to `127.0.0.1` (loopback); other machines cannot reach it.
- Every request needs the random token printed at startup, so other web pages
  cannot read or overwrite the library through your browser.
- The server validates that the save payload contains every merged style
  exactly once and only known sections; a malformed payload is rejected
  without writing.
- The bundled library is loaded through the same parser/merge code the plugin
  uses, but it is only ever read.
