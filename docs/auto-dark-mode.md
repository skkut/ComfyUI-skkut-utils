# Auto Dark Mode

Detects the operating system's colour-scheme (Light / Dark) and automatically switches the ComfyUI appearance to match — in real time, in both the web browser and ComfyUI Desktop.

## Overview

| | |
|---|---|
| **Python backend** | `auto_dark_mode/__init__.py` |
| **Frontend extension** | `web/auto_dark_mode.js` |
| **Injected script** | `/auto-dark-mode/inject.js` (served by the backend) |
| **Config** | None — zero-config, runs at server startup |

## How it works

The feature has three cooperating parts:

### 1. OS theme detection (Python)

On server startup, `_get_os_theme()` reads the actual OS colour-scheme:

| OS | Mechanism |
|---|---|
| Windows | Registry: `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme` |
| macOS | `defaults read -g AppleInterfaceStyle` |
| Linux | `gsettings get org.gnome.desktop.interface color-scheme` (GNOME), falling back to `kreadconfig5` (KDE) |

Detection failures default to `dark`. The detected theme is embedded into the injected JavaScript so it is authoritative from the first page load (Electron's `matchMedia` can disagree with the real OS setting on ComfyUI Desktop).

### 2. Applying the theme (injected JavaScript)

A script is injected into the root HTML page (`/`) via an aiohttp middleware. It calls `colorPaletteService.loadColorPalette("dark" | "light")` through the Pinia workspace store — the same function used by the **Settings → Appearance → Color Palette** menu — which applies CSS variables, LiteGraph properties and a canvas redraw correctly.

It also:

- persists the choice through `extensionManager.setting.set("Comfy.ColorPalette", ...)` so ComfyUI's own init doesn't override it;
- runs a 3-second watchdog that silently re-applies the theme if ComfyUI overrides it;
- listens to browser `matchMedia('(prefers-color-scheme: dark)')` changes as a fallback source of truth.

### 3. Real-time updates (Python → browser)

A background thread polls the OS theme every 3 seconds. On change, it pushes an `auto-dark-mode.theme-changed` event (payload `{"theme": "dark"|"light"}`) to all connected WebSocket clients via `PromptServer.send_sync`, using `call_soon_threadsafe` so the push is safe from the background thread. Both the injected script and `web/auto_dark_mode.js` listen for this event.

The frontend extension file `web/auto_dark_mode.js` provides the same listener for browser environments where the injected script is not needed (it is loaded by ComfyUI from `WEB_DIRECTORY`).

## HTTP routes

| Route | Purpose |
|---|---|
| `GET /auto-dark-mode/inject.js` | Serves the injected script with the startup-detected theme embedded |
| `GET/POST /auto-dark-mode/log` | Frontend diagnostics endpoint; forwards JS `log`/`error` messages to the server log |

## Event

| Event | Payload | Direction |
|---|---|---|
| `auto-dark-mode.theme-changed` | `{ "theme": "dark" \| "light" }` | Python → browser |

## Installation

The feature ships as part of the unified `ComfyUI-skkut-utils` repo — see the [root README](../README.md). No extra dependencies, no configuration. Restart ComfyUI after installing.

## Troubleshooting

- **Server log**: startup detection and theme changes are logged with the `skkut-utils/auto-dark-mode` logger (e.g. `Detected OS theme: dark`).
- **Frontend log**: runtime messages are posted to `/auto-dark-mode/log` and appear in the server log with a `[frontend]` prefix. Set `?level=error` diagnostics by opening the browser console (ComfyUI Desktop: **Ctrl+Shift+I** / **Cmd+Option+I**) — errors are also reported there.
- **Theme flicker on startup**: initial sync retries at 2 s and 10 s after load to recover from ComfyUI's own theme initialization overriding the applied palette.
