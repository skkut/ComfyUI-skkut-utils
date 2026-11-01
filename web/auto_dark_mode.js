/**
 * ComfyUI Auto Dark Mode — frontend extension (loaded via WEB_DIRECTORY).
 *
 * For environments where WEB_DIRECTORY works (primarily the web browser
 * version), this extension registers a WebSocket listener for Python-side
 * theme-change events and calls colorPaletteService.loadColorPalette().
 *
 * For ComfyUI Desktop (where WEB_DIRECTORY may not work), the same
 * functionality is provided by a script injected via aiohttp middleware
 * in __init__.py.
 */
import { app } from "../../scripts/app.js";

const SETTING_ID = "SkkutUtils.AutoDarkMode.Enabled";

/** True unless the user turned Auto Dark Mode off in Settings → skkut-utils. */
function isEnabled() {
	try {
		return app.ui?.settings?.getSettingValue(SETTING_ID) !== false;
	} catch (_) {
		return true;
	}
}

app.registerExtension({
	name: "Comfy.AutoDarkMode",
	settings: [
		{
			id: SETTING_ID,
			name: "Auto Dark Mode",
			type: "boolean",
			defaultValue: true,
			category: ["skkut-utils", "Features", "AutoDarkMode"],
			tooltip: "Match the ComfyUI theme to your OS light/dark setting automatically.",
		},
	],
	async setup() {
		const applyTheme = (paletteId) => {
			try {
				const el = document.querySelector("#vue-app");
				if (!el?.__vue_app__) return;
				const pinia = el.__vue_app__.config.globalProperties.$pinia;
				if (!pinia) return;
				const ws = pinia._s.get("workspace");
				if (!ws?.colorPalette?.loadColorPalette) return;
				ws.colorPalette.loadColorPalette(paletteId);
			} catch (_) {}
		};

		const sync = () => {
			if (!isEnabled()) return;
			const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
			applyTheme(isDark ? "dark" : "light");
		};

		// Python WebSocket push
		if (app.api?.addEventListener) {
			app.api.addEventListener("auto-dark-mode.theme-changed", (e) => {
				if (!isEnabled()) return;
				const t = e?.detail?.theme;
				if (t === "dark" || t === "light") applyTheme(t);
			});
		}

		// Settings → skkut-utils toggle. Re-enabling syncs immediately;
		// disabling just stops any further theme applications.
		app.ui?.settings?.addEventListener?.(`${SETTING_ID}.change`, (e) => {
			if (e?.detail?.value) sync();
		});

		// Browser matchMedia
		const mq = window.matchMedia("(prefers-color-scheme: dark)");
		if (mq.addEventListener) mq.addEventListener("change", sync);
		else if (mq.addListener) mq.addListener(sync);

		// Initial sync
		setTimeout(sync, 1500);
		setTimeout(sync, 4000);
	},
});
