# ComfyUI-skkut-utils

A collection of small utilities for [ComfyUI](https://github.com/comfyanonymous/ComfyUI), unified into a single custom-node repo. Install once, get all utils.

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

No build step. Everything except the Weppy node is zero-config and activates on startup.

## Available utils

| Utils | What it does | How to use |
|---|---|---|
| 🎨 **Auto Dark Mode** | Switches the ComfyUI theme to match the OS Light/Dark colour-scheme, in real time (browser + ComfyUI Desktop) | Nothing to do — automatic |
| ⏱ **Detailed Job Status** | Floating, draggable execution timer (MM:SS) in the UI, timed from actual execution start | Nothing to do — automatic |
| 🖼 **Save Compressed Weppy** | Saves images as compressed WebP with embedded prompt/workflow metadata | Add the **Save Compressed Weppy** node, or right-click any image → "Save Compressed Weppy" |

---

### 🎨 Auto Dark Mode

**Description.** Detects the OS colour-scheme (Windows / macOS / Linux) on server startup and applies it to ComfyUI instantly, using the same palette loader as the *Settings → Appearance → Color Palette* menu. A background poll (every 3 s) and WebSocket push keep the UI in sync when you change the OS theme while ComfyUI is open, and a `matchMedia` listener covers browser-driven changes.

**How to use.** Nothing to configure or click — it just works. Turn it off, if you ever want to, by setting a theme manually in the ComfyUI settings menu (the watchdog re-applies the OS theme, so disable the extension or set your OS preference if you want a fixed theme). Diagnostics: look for the `skkut-utils/auto-dark-mode` logger in the server log (`Detected OS theme: …`) and `[frontend]` lines for browser-side events.

---

### ⏱ Detailed Job Status

**Description.** Shows a small floating widget in the bottom-right corner displaying how long the current job has been **executing** (not queued), in `MM:SS`. It appears when a run starts, ticks every second, and stays with the final status when the job finishes: **Running** (white) → **Completed** (green), **Error** (red), or **Stopped** (orange).

**How to use.** Nothing to configure — the timer appears automatically when a job starts. Drag it anywhere with the mouse; its position is remembered per browser between sessions.

---

### 🖼 Save Compressed Weppy

**Description.** Saves images as compressed `.webp` files while embedding the ComfyUI prompt and workflow in the EXIF metadata (large base64 blobs are stripped automatically so the metadata stays within EXIF size limits). Two ways to use it:

1. **Save Compressed Weppy node** (category: `image`) — add it to your workflow and every generated image is saved to the output directory during execution. Inputs: `images`, `filename_prefix` (default `ComfyUI_Weppy`), `quality` (1–100, default 80), `lossless` (default off). The prompt/workflow are captured automatically via hidden inputs.
2. **Right-click any image preview** → **"Save Compressed Weppy"** (right next to the native "Save Image" entry) — re-encodes that image and triggers a download. In ComfyUI Desktop this opens the native save dialog.

Saved files keep their metadata: drag a `.webp` back into ComfyUI to recover the workflow that generated it.

---

## Repository layout

```
__init__.py                    # Root aggregator (WEB_DIRECTORY, node mappings)
auto_dark_mode/                # Util: Auto Dark Mode (Python backend)
detailed_jobstatus/            # Util: Detailed Job Status (web-only)
save_compressed_weppy/         # Util: Save Compressed Weppy (node + route)
web/                           # Frontend extensions, one file per util
docs/                          # Per-util documentation
```

Each utility is documented in detail in [docs/](docs/):

- [docs/auto-dark-mode.md](docs/auto-dark-mode.md) — how theme detection, injection and the WebSocket push work, plus troubleshooting
- [docs/detailed-jobstatus.md](docs/detailed-jobstatus.md) — event handling, completion detection, widget behaviour
- [docs/save-compressed-weppy.md](docs/save-compressed-weppy.md) — node inputs, context-menu flow, EXIF metadata strategy

See [Agents.md](Agents.md) for the repo conventions (layout, docs rule, how to add a util).

## License

[MIT](LICENSE)
