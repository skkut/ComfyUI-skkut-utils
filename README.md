# ComfyUI-skkut-utils

A collection of small utilities for [ComfyUI](https://github.com/comfyanonymous/ComfyUI), unified into a single custom-node repo.

## Features

| Feature | What it does | Docs |
|---|---|---|
| 🎨 **Auto Dark Mode** | Detects the OS Light/Dark colour-scheme and switches the ComfyUI theme to match in real time (browser + ComfyUI Desktop) | [docs/auto-dark-mode.md](docs/auto-dark-mode.md) |
| ⏱ **Detailed Job Status** | Floating, draggable execution timer (MM:SS) in the UI, timing from actual execution start | [docs/detailed-jobstatus.md](docs/detailed-jobstatus.md) |
| 🖼 **Save Compressed Weppy** | Save images as compressed WebP with embedded prompt/workflow metadata — a custom node plus a right-click "Save Compressed Weppy" entry | [docs/save-compressed-weppy.md](docs/save-compressed-weppy.md) |

## Installation

1. Navigate to your ComfyUI custom nodes directory:

   ```bash
   cd ComfyUI/custom_nodes/
   ```

2. Clone this repository:

   ```bash
   git clone https://github.com/skkut/ComfyUI-skkut-utils.git
   ```

3. (Optional) Install the optional dependency for the Weppy EXIF writer:

   ```bash
   pip install -r requirements.txt
   ```

4. Restart ComfyUI.

All features are zero-config — they activate on startup. No build step.

## Repository layout

```
__init__.py                    # Root aggregator (WEB_DIRECTORY, node mappings)
auto_dark_mode/                # Feature: Auto Dark Mode (Python backend)
detailed_jobstatus/            # Feature: Detailed Job Status (web-only)
save_compressed_weppy/         # Feature: Save Compressed Weppy (node + route)
web/                           # Frontend extensions, one file per feature
docs/                          # Per-feature documentation
```

Each feature is documented individually in [docs/](docs/). See [Agents.md](Agents.md) for the repo conventions (layout, docs rule, how to add a feature).

## License

[MIT](LICENSE)
