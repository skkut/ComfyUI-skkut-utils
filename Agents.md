# Agents.md

Instructions for Claude Code (and other agents) working in this repository.

## Repo purpose

`ComfyUI-skkut-utils` is a **single unified ComfyUI custom node repo** that
collects small utilities that previously lived in separate repos
(`ComfyUI-Auto-DarkMode`, `ComfyUI-detailed-jobstatus`,
`ComfyUI-SaveCompressed-Weppy`). New utilities belong here, not in new repos.

## Repository layout

```
__init__.py                        # Root aggregator — the ONLY file ComfyUI imports
pyproject.toml                     # Comfy Registry package metadata ([tool.comfy])
auto_dark_mode/__init__.py         # Feature: OS theme detection + theme switching (Python backend)
detailed_jobstatus/__init__.py     # Feature: execution timer (web-only placeholder subpackage)
save_compressed_weppy/             # Feature: WebP saving (node + HTTP route)
    __init__.py                    #   registers node mapping + /save_compressed_weppy route
    save_compressed_weppy.py       #   node implementation
resolution_calculator/             # Feature: Skutils Resolution Calculator (node)
    __init__.py                    #   registers node mapping
    resolution_calculator.py       #   node implementation
web/                               # Single WEB_DIRECTORY: one JS file per feature
    auto_dark_mode.js
    jobTimer.js
    save_compressed_weppy.js
docs/                              # One markdown file per feature (see rule below)
Agents.md
README.md
requirements.txt
```

- Each feature is a **self-contained subpackage** at the repo root, named
  `snake_case`. The root `__init__.py` imports every feature subpackage so
  its import-time side effects (route registration, threads) run.
- All frontend extensions live in `web/`, one file per feature. The root
  `__init__.py` sets `WEB_DIRECTORY = "./web"` — this is the only
  WEB_DIRECTORY in the repo; feature subpackages must NOT declare their own.
- The root `__init__.py` owns `NODE_CLASS_MAPPINGS` /
  `NODE_DISPLAY_NAME_MAPPINGS` (aggregated from features), `WEB_DIRECTORY`
  and `__all__`.

## Documentation rule (mandatory)

**Every feature gets its own documentation file in `docs/`, named after the
feature in kebab-case** (`docs/<feature-name>.md`). When you add or
materially change a feature, create or update its doc file.

Doc content should cover: overview, how it works (architecture / data
flow), configuration, the files that implement it, and troubleshooting.
Link back to the root README for install instructions.

## Adding a new feature (checklist)

1. Create `new_feature/__init__.py` (Python backend, if any) and
   `web/new_feature.js` (frontend extension, if any).
2. Wire it up in the root `__init__.py` (`from . import new_feature` and,
   if it registers nodes, import its mappings).
3. Write `docs/new-feature.md` per the documentation rule above.
4. Update the feature list in the root `__init__.py` docstring and the root
   `README.md` (feature table + link to the new doc).
5. If the feature needs a Python package not already in `requirements.txt`,
   add it there (keep optional deps commented as optional).

## Conventions

- **Stable route/event names.** HTTP routes and WebSocket event names that
  pair Python with the frontend (e.g. `/auto-dark-mode/inject.js`,
  `auto-dark-mode.theme-changed`, `/save_compressed_weppy`) must be kept in
  sync between the backend and `web/`. Renaming one side breaks the other.
- **Do not rely on paths from the old separate repos** — everything has
  been consolidated here (e.g. `js/` dirs are now `web/`).
- **Dependencies**: only `piexif` (optional — code has a Pillow fallback).
  All other libraries (`aiohttp`, `PIL`, `numpy`, `folder_paths`, `server`)
  are ComfyUI's own or come with ComfyUI's environment.
- Frontend extensions use `import { app } from "../../scripts/app.js"`
  (browser) / `import { api } from "../../scripts/api.js"` — keep this
  relative path style for files in `web/`.
- Keep the repo installable by git-cloning into `ComfyUI/custom_nodes/`
  and restarting ComfyUI — no build step.
- Python code runs inside ComfyUI's process: import `server.PromptServer`,
  `folder_paths` etc. lazily or guarded (`try/except`) where a feature is
  optional.
