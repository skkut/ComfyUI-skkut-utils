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

app.registerExtension({
	name: "Comfy.AutoDarkMode",
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
			const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
			applyTheme(isDark ? "dark" : "light");
		};

		// Python WebSocket push
		if (app.api?.addEventListener) {
			app.api.addEventListener("auto-dark-mode.theme-changed", (e) => {
				const t = e?.detail?.theme;
				if (t === "dark" || t === "light") applyTheme(t);
			});
		}

		// Browser matchMedia
		const mq = window.matchMedia("(prefers-color-scheme: dark)");
		if (mq.addEventListener) mq.addEventListener("change", sync);
		else if (mq.addListener) mq.addListener(sync);

		// Initial sync
		setTimeout(sync, 1500);
		setTimeout(sync, 4000);
	},
});
