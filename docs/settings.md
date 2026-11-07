# Settings

ComfyUI-skkut-utils adds its own **skkut-utils** section to ComfyUI's Settings dialog. Feature toggles live there instead of being mixed into the built-in **General** / **Appearance** sections.

## Where to find it

Open **Settings** (the gear icon) and select **skkut-utils** in the left sidebar. In current ComfyUI frontends custom sections are grouped under **OTHER**; in older layouts the section appears alongside the built-in ones.

The panel contains a **Features** group and a separate **Style Selector** group
(the panel draws a divider between groups):

| Control | Default | What it controls |
|---|---|---|
| **Auto Dark Mode** | On | Keeps ComfyUI's colour palette in sync with the OS light/dark setting ([details](auto-dark-mode.md)) |
| **Job Status Indicator** | On | Shows the floating execution timer while a workflow runs ([details](detailed-jobstatus.md)) |
| **Style Selector → Section order** | Library order | Reorders the section groups in the style picker's grid and filter ([details](skutils-style-selector.md#section-order)) |

Changes take effect immediately — no restart is needed. The values are stored by ComfyUI's normal settings storage, so they persist per user. The two toggles default to **On**, so updating an existing install does not change its behaviour. The section order is an ordered list that saves as you move rows; its default is the library's own section order.

## How it works

Each control is a regular ComfyUI setting registered by the frontend extension that owns the feature:

| Setting ID | Registered by | Category |
|---|---|---|
| `SkkutUtils.AutoDarkMode.Enabled` | `web/auto_dark_mode.js` | `skkut-utils` → `Features` → `AutoDarkMode` |
| `SkkutUtils.JobStatus.Enabled` | `web/jobTimer.js` | `skkut-utils` → `Features` → `JobStatus` |
| `SkkutUtils.StyleSelector.SectionOrder` | `web/skutils_style_selector.js` | `skkut-utils` → `Style Selector` |

Because all three use the same top-level category (`skkut-utils`), ComfyUI
renders them in one dedicated settings section. The first two share the
`Features` group; the section-order control has its own `Style Selector`
group, so it appears after **Features** with a heading and divider.

The section-order setting uses ComfyUI's custom setting-control form (a
function `type`) to render a reorderable list. Its value is a JSON array of
section names; anything not listed falls back to the library order.

The features read their setting at runtime and subscribe to the setting's `<id>.change` event:

- **Auto Dark Mode** — the check is applied in both `web/auto_dark_mode.js` and the injected `/auto-dark-mode/inject.js` script, so it works in the browser *and* in ComfyUI Desktop. Disabling stops `matchMedia` / WebSocket pushes and the 3-second watchdog from applying a palette. Re-enabling re-syncs to the current OS theme immediately. Turning it off does not revert the palette already applied — choose one in **Settings → Appearance → Color Palette** if you want a fixed theme.
- **Job Status Indicator** — disabling hides the floating widget and clears any in-flight timer. Re-enabling takes effect with the next `execution_start` (a job that was already running is not retroactively timed).

## Files

- `web/auto_dark_mode.js` — registers `SkkutUtils.AutoDarkMode.Enabled`, gates theme application.
- `web/jobTimer.js` — registers `SkkutUtils.JobStatus.Enabled`, gates the widget.
- `web/skutils_style_selector.js` — registers `SkkutUtils.StyleSelector.SectionOrder` and its reorderable-list control.
- `auto_dark_mode/__init__.py` — the injected Desktop-side script reads the same setting from `app.ui.settings`.

## Installation

Ships with the unified `ComfyUI-skkut-utils` repo — see the [root README](../README.md). No extra dependencies.

## Troubleshooting

- **The skkut-utils section is missing.** Restart ComfyUI after updating (Python-side code and the injected script are loaded at startup) and hard-refresh the browser. Custom sections are under **OTHER** in the sidebar.
- **A toggle does not stick.** Settings are saved through ComfyUI's settings API; a save failure is reported in the browser console and as a toast. Check that the ComfyUI user directory is writable.
- **Auto Dark Mode still applies after disabling.** Disabling prevents *future* palette changes; the last palette remains. Pick a different palette explicitly, or restart after updating so the injected script picks up the new setting check.
