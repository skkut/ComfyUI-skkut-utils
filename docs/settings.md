# Settings

ComfyUI-skkut-utils adds its own **skkut-utils** section to ComfyUI's Settings dialog. Feature toggles live there instead of being mixed into the built-in **General** / **Appearance** sections.

## Where to find it

Open **Settings** (the gear icon) and select **skkut-utils** in the left sidebar. In current ComfyUI frontends custom sections are grouped under **OTHER**; in older layouts the section appears alongside the built-in ones.

The panel currently contains one **Features** group:

| Toggle | Default | What it controls |
|---|---|---|
| **Auto Dark Mode** | On | Keeps ComfyUI's colour palette in sync with the OS light/dark setting ([details](auto-dark-mode.md)) |
| **Job Status Indicator** | On | Shows the floating execution timer while a workflow runs ([details](detailed-jobstatus.md)) |

Changes take effect immediately — no restart is needed. The values are stored by ComfyUI's normal settings storage, so they persist per user. Both default to **On**, so updating an existing install does not change its behaviour.

## How it works

Each toggle is a regular ComfyUI setting registered by the frontend extension that owns the feature:

| Setting ID | Registered by | Category |
|---|---|---|
| `SkkutUtils.AutoDarkMode.Enabled` | `web/auto_dark_mode.js` | `skkut-utils` → `Features` → `AutoDarkMode` |
| `SkkutUtils.JobStatus.Enabled` | `web/jobTimer.js` | `skkut-utils` → `Features` → `JobStatus` |

Because both use the same top-level category (`skkut-utils`) and sub-group (`Features`), ComfyUI renders them together in one dedicated settings section.

The features read their setting at runtime and subscribe to the setting's `<id>.change` event:

- **Auto Dark Mode** — the check is applied in both `web/auto_dark_mode.js` and the injected `/auto-dark-mode/inject.js` script, so it works in the browser *and* in ComfyUI Desktop. Disabling stops `matchMedia` / WebSocket pushes and the 3-second watchdog from applying a palette. Re-enabling re-syncs to the current OS theme immediately. Turning it off does not revert the palette already applied — choose one in **Settings → Appearance → Color Palette** if you want a fixed theme.
- **Job Status Indicator** — disabling hides the floating widget and clears any in-flight timer. Re-enabling takes effect with the next `execution_start` (a job that was already running is not retroactively timed).

## Files

- `web/auto_dark_mode.js` — registers `SkkutUtils.AutoDarkMode.Enabled`, gates theme application.
- `web/jobTimer.js` — registers `SkkutUtils.JobStatus.Enabled`, gates the widget.
- `auto_dark_mode/__init__.py` — the injected Desktop-side script reads the same setting from `app.ui.settings`.

## Installation

Ships with the unified `ComfyUI-skkut-utils` repo — see the [root README](../README.md). No extra dependencies.

## Troubleshooting

- **The skkut-utils section is missing.** Restart ComfyUI after updating (Python-side code and the injected script are loaded at startup) and hard-refresh the browser. Custom sections are under **OTHER** in the sidebar.
- **A toggle does not stick.** Settings are saved through ComfyUI's settings API; a save failure is reported in the browser console and as a toast. Check that the ComfyUI user directory is writable.
- **Auto Dark Mode still applies after disabling.** Disabling prevents *future* palette changes; the last palette remains. Pick a different palette explicitly, or restart after updating so the injected script picks up the new setting check.
