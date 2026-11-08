# Reorganize Styles (developer tool)

A maintenance utility for editing `skutils_style_selector/styles.json` — the
bundled style library behind the Skutils Style Selector node.

It is **not** part of the ComfyUI plugin: nothing in the repo imports it and it
is excluded from the Comfy Registry package by `.comfyignore`. It *is* tracked
on GitHub, so anyone cloning the repo can use it.

## Run

```bash
python tools/reorganize_styles.py
```

The script prints a URL containing a one-run access token and opens it in your
browser. It binds only to `127.0.0.1`.

Options:

| Option | Meaning |
|---|---|
| `--port N` | Port on `127.0.0.1` (default `8765`; `0` picks a free port) |
| `--library PATH` | Edit a different `styles.json` (useful for testing) |
| `--no-browser` | Don't open the browser automatically |

## What it does

- **Reorder styles** inside a section — drag a row by its `⠿` grip, use the
  `↑` / `↓` buttons for single steps, or `⤒` / `⤓` to send a style to the top
  or bottom. Each row shows its current position number within its section,
  and the numbers update immediately after a move (and live while dragging).
  The picker shows styles in the saved order within each section.
- **Pin styles to anchor them** — click `📌` on a row. Pinning never changes
  the row's position: pin something in the middle and it stays there. A
  pinned row itself cannot be moved (its grip, `↑`, `↓`, `⤒` and `⤓` are
  disabled). Pinned styles that form the block at the very top of a section
  stay on top: `⤒` on an unpinned style lands directly **below** that block,
  skipping over any anchored styles further down. Click `📌` again to unpin
  (the row stays where it is). Sections with pins show a `📌 N` badge. Pins
  are stored as `"pinned": true` on the entry in `styles.json`; the plugin
  ignores the field.
- **Recategorize a style** — use the dropdown on its row. It lists every
  section in the library, plus **＋ New section…** to create one.
- **Search** by name, section, source, or prompt text, and filter to one
  section. Matches are highlighted (case-insensitively) in each result's
  name, source, prompt, and section header, as well as in the full-size
  preview. Reordering is disabled while a search is active (the visible
  order would be ambiguous); use the `↑` / `↓` buttons or clear the search.
- **See each style clearly** — every row shows a **300 px thumbnail** and the
  style's **full prompt text**, with no truncation. Click any thumbnail (or
  focus it and press Enter/Space) to open the **full-size preview** at the
  image's native 512 px; the preview also shows the complete prompt. Use
  `←` / `→` (or the side arrows) to browse the currently visible list, and
  `Esc`, the `×`, or the backdrop to close.

## Saving

**Save** (or Ctrl+S) writes the file atomically. Before each write, the old
file is copied to `tools/backups/styles-<timestamp>.json`; the newest 20
backups are kept (that folder is gitignored).

After saving, restart ComfyUI: `library.py` caches `styles.json` when the
backend imports, so a running instance will not see the new order until it is
restarted. Hard-refreshing the browser alone is not enough.

Note: `scripts/build_style_library.py` rewrites `styles.json` from the source
packs, so pins (like manual ordering) do not survive a rebuild.

## Safety

- Binds only to `127.0.0.1` (loopback); other machines cannot reach it.
- Every request needs the random token printed at startup, so other web pages
  cannot read or overwrite the library through your browser.
- The server validates that the save payload contains every style exactly once
  and only known sections; a malformed payload is rejected without writing.
- All fields of each style entry are preserved; the editor only changes entry
  order and the `section` / `pinned` values.
