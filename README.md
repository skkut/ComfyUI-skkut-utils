# ComfyUI-skkut-utils

## About

**ComfyUI-skkut-utils** is a single-repo collection of small, practical utilities for [ComfyUI](https://github.com/comfyanonymous/ComfyUI). Instead of maintaining a dozen tiny custom-node repos — each with its own clone-and-install step — every utility lives here, installs together, and needs no configuration.

What's inside:

- **Theme & appearance** — [Auto Dark Mode](docs/auto-dark-mode.md) keeps ComfyUI's colour palette in sync with your OS light/dark setting, in the browser and in ComfyUI Desktop.
- **Feedback while generating** — [Detailed Job Status](docs/detailed-jobstatus.md) adds a floating, draggable timer that shows how long a job actually ran (not queued), with final status colours.
- **Saving with metadata** — [Save Compressed Weppy](docs/save-compressed-weppy.md) exports compressed WebP with the prompt and workflow embedded, so dragging the image back into ComfyUI recovers the workflow that made it.
- **Latent setup** — [Skutils Resolution Calculator](docs/resolution-calculator.md) turns an aspect-ratio preset and a megapixel target into exact width/height values for an Empty Latent Image, with 20 presets spanning the SD1.5, SDXL, SD3/Flux and video-model ladders.
- **Resizing optional images** — [Skutils Scale Image to Total Pixels](docs/scale-to-total-pixels.md) is the built-in *Scale Image to Total Pixels* node with an **optional** image input, so an image slot you may leave empty no longer blocks the whole workflow from queueing.
- **Text in the workflow** — [Skutils Text Preview](docs/text-preview.md) shows any text right on the node *and* stores it in the saved workflow JSON, so reloading the workflow brings the text back — no re-run, no external file.

**Design principles:**

- **Install once, get everything** — one `git clone` into `ComfyUI/custom_nodes/`, restart, done. No build step, no config files.
- **Small and self-contained** — each utility is an independent subpackage with its own docs; use one, or use them all.
- **Zero-config by default** — features just work on startup; nothing is intrusive until you use it.

Compatible with ComfyUI in the browser and the ComfyUI Desktop app, on Windows, macOS and Linux. MIT-licensed.

## Installation

1. Navigate to your ComfyUI custom nodes directory:

   ```bash
   cd ComfyUI/custom_nodes/
   ```

2. Clone this repository:

   ```bash
   git clone https://github.com/skkut/ComfyUI-skkut-utils.git
   ```

   Or install from the [Comfy Registry](https://registry.comfy.org) via **ComfyUI Manager** (search for `skkut-utils`).

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
| 📐 **Skutils Resolution Calculator** | Width/height from 20 aspect-ratio presets + a megapixel dropdown (0.5–5.0 MP) — like the built-in Resolution Selector, with more options | Add the **Skutils Resolution Calculator** node and feed `width`/`height` into an Empty Latent Image |
| 🔍 **Skutils Scale Image to Total Pixels** | The built-in *Scale Image to Total Pixels* node with an **optional** image input — leave it unconnected and the node outputs nothing instead of failing prompt validation | Add the **Skutils Scale Image to Total Pixels** node wherever you resize a reference image that may not always be supplied |
| 📝 **Skutils Text Preview** | Shows text in the node and stores it in the saved workflow JSON — reloading the workflow brings the displayed text back (no re-run) | Add the **Skutils Text Preview** node, connect a `STRING` into its `text` port, run once, then save the workflow |

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
2. **Right-click any image preview** → **"Save Compressed Weppy"** (right next to the native "Save Image" entry) — re-encodes that image and triggers a download. In ComfyUI Desktop this opens the native save dialog. The download is named after the graph when a supported node supplies one (e.g. the OreX style selector's selected style → `collage_kzqrv.webp`), and `ComfyUI_Weppy_<random>` otherwise.

Saved files keep their metadata: drag a `.webp` back into ComfyUI to recover the workflow that generated it.

---

### 📐 Skutils Resolution Calculator

**Description.** Calculates `width` and `height` for your Empty Latent Image from an **aspect-ratio preset** and a **megapixel target** — the same idea as the built-in *Resolution Selector* node, but with **20 presets** (the built-in's 8, the SD1.5/SDXL/SD3-Flux/video ladders, and ultra-wide/ultra-tall tiers) and a **megapixel dropdown** from `0.5 MP` to `5.0 MP` in 0.5 steps instead of a free float.

**How to use.** Add the **Skutils Resolution Calculator** node (category `utils/resolution`), pick a preset such as `16:9 (Widescreen)` and a megapixel value, and connect the `width`/`height` outputs to an Empty Latent Image. Each preset is anchored to its canonical ~1 MP resolution (e.g. `16:9` → `1344×768`, the SDXL/Flux widescreen), so `1.0 MP` reproduces the familiar values exactly. The advanced `multiple` input is a dropdown (8/16/32/64/128, default 8) — 8 divides all the others, so it works for every model family; pick 16/32/64 for Flux or video models.

---

### 🔍 Skutils Scale Image to Total Pixels

**Description.** The built-in *Scale Image to Total Pixels* node, with one change: its **`image` input is optional**. The widgets (`upscale_method`, `megapixels`, `resolution_steps`), their ranges, their defaults and the resize arithmetic are the built-in node's, so it is a drop-in replacement — but with nothing plugged into `image` it returns `None` and the workflow still queues instead of being rejected.

**Why it exists.** ComfyUI validates a prompt's required inputs *before* it runs anything, and that validation is not lazy-aware: a node with an unconnected required input fails the whole submission even when it sits on a branch nothing will ever execute — so a switch that selects the other side does not protect it. Because the built-in node's `image` is required (and its body has no `None` guard either), wiring it to an image slot you may leave empty makes the entire workflow unqueueable. A switch after the resize cannot help, and feeding it a dummy image silently changes the result. This node removes the constraint instead of working around it.

**How to use.** Add the **Skutils Scale Image to Total Pixels** node (category `utils/resolution`) anywhere you would use the built-in one, and connect `image`. When the slot may be empty, leave it unconnected — the node then outputs `None`, which propagates like any other value, so put it at the *end* of an optional branch (autogrow image containers such as `TextEncodeQwenImage21`'s `images` accept `None`; a plain required `IMAGE` input will not). See [docs/scale-to-total-pixels.md](docs/scale-to-total-pixels.md) for the full problem statement and the worked example.

---

### 📝 Skutils Text Preview

**Description.** Displays text right on the node — and, unlike the built-in display-only text-preview nodes, **stores the displayed text in the saved workflow JSON**. The executed text is written into the node's regular widget (via a small frontend extension), so a workflow save serializes it into the `.json` and a workflow load restores it: reopen the file later and the text is still there, without re-running.

**How to use.** Add the **Skutils Text Preview** node (category `utils/text`), connect any `STRING` output into its `text` port, and run the workflow once — the text then appears in a read-only text area in the node body. From then on, **Ctrl+S** — the text is part of the saved JSON (also when the workflow is embedded in an image, e.g. via Save Compressed Weppy). Caveat: like every node's widget values, it is not included in *Save (API format)* JSON.

---

## Repository layout

```
__init__.py                    # Root aggregator (WEB_DIRECTORY, node mappings)
auto_dark_mode/                # Util: Auto Dark Mode (Python backend)
detailed_jobstatus/            # Util: Detailed Job Status (web-only)
save_compressed_weppy/         # Util: Save Compressed Weppy (node + route)
resolution_calculator/         # Util: Skutils Resolution Calculator (node)
scale_to_total_pixels/         # Util: Skutils Scale Image to Total Pixels (node)
text_preview/                  # Util: Skutils Text Preview (node + frontend)
web/                           # Frontend extensions, one file per util
docs/                          # Per-util documentation
```

Each utility is documented in detail in [docs/](docs/):

- [docs/auto-dark-mode.md](docs/auto-dark-mode.md) — how theme detection, injection and the WebSocket push work, plus troubleshooting
- [docs/detailed-jobstatus.md](docs/detailed-jobstatus.md) — event handling, completion detection, widget behaviour
- [docs/save-compressed-weppy.md](docs/save-compressed-weppy.md) — node inputs, context-menu flow, EXIF metadata strategy
- [docs/resolution-calculator.md](docs/resolution-calculator.md) — preset table, megapixel dropdown, calculation math
- [docs/scale-to-total-pixels.md](docs/scale-to-total-pixels.md) — the problem statement, why the built-in node's required input blocks optional slots, and how the `None` passthrough behaves
- [docs/text-preview.md](docs/text-preview.md) — how the displayed text is stored in the workflow JSON, what is/isn't saved

See [Agents.md](Agents.md) for the repo conventions (layout, docs rule, how to add a util).

## License

[MIT](LICENSE)
