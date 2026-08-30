"""
ComfyUI Auto Dark Mode — feature subpackage of ComfyUI-skkut-utils.

Detects the OS colour-scheme and automatically switches ComfyUI's theme
to match in real time.  Works in both the web browser and ComfyUI Desktop.

How it works:
  1. Python detects the OS theme (Windows / macOS / Linux).
  2. A small JavaScript snippet is injected into the HTML page via aiohttp
     middleware.  This snippet calls colorPaletteService.loadColorPalette()
     — the exact same function used by the Settings → Appearance → Color
     Palette menu — to apply "dark" or "light" instantly.
  3. A background thread polls for OS theme changes every 3 s and pushes
     theme-change events to the frontend via WebSocket.
  4. The injected JS also listens for browser matchMedia events.

Frontend counterpart: web/auto_dark_mode.js (loaded via the root
WEB_DIRECTORY) plus the middleware-injected script served from
/auto-dark-mode/inject.js.
"""

import logging
import sys
import asyncio
import threading

_logger = logging.getLogger("skkut-utils.auto-dark-mode")

# =========================================================================
# OS theme detection
# =========================================================================

def _get_os_theme():
    """Return 'dark' or 'light' based on the OS colour-scheme preference."""
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "light" if value == 1 else "dark"

        elif sys.platform == "darwin":
            import subprocess
            r = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True,
            )
            return "dark" if r.stdout.strip() == "Dark" else "light"

        else:  # Linux
            import subprocess
            r = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, text=True,
            )
            if "dark" in r.stdout.lower():
                return "dark"
            r2 = subprocess.run(
                ["kreadconfig5", "--group", "General", "--key", "ColorScheme"],
                capture_output=True, text=True,
            )
            return "dark" if "dark" in r2.stdout.lower() else "light"
    except Exception:
        return "dark"


# =========================================================================
# WebSocket push (thread-safe)
# =========================================================================

def _push_theme(theme):
    """Push a theme-change event to all connected WebSocket clients."""
    try:
        from server import PromptServer
        srv = PromptServer.instance
        if srv is None:
            return
        try:
            loop = srv.loop
        except Exception:
            loop = None

        if loop is not None:
            try:
                on_loop = asyncio.get_running_loop() is loop
            except RuntimeError:
                on_loop = False
            if not on_loop:
                loop.call_soon_threadsafe(
                    lambda: srv.send_sync("auto-dark-mode.theme-changed",
                                          {"theme": theme})
                )
            else:
                srv.send_sync("auto-dark-mode.theme-changed", {"theme": theme})
        else:
            srv.send_sync("auto-dark-mode.theme-changed", {"theme": theme})
    except Exception:
        pass


# =========================================================================
# Background polling
# =========================================================================

_detected = _get_os_theme()
_logger.info("[skkut-utils/auto-dark-mode] Detected OS theme: %s", _detected)

_stop = threading.Event()

def _poll():
    last = _detected
    while not _stop.wait(timeout=3):
        try:
            cur = _get_os_theme()
            if cur != last:
                _logger.info("[skkut-utils/auto-dark-mode] OS theme changed: %s -> %s", last, cur)
                last = cur
                _push_theme(cur)
        except Exception:
            pass

_t = threading.Thread(target=_poll, daemon=True, name="auto-dark-mode-poll")
_t.start()

# =========================================================================
# Injected JavaScript
# =========================================================================

_INJECTED_JS = r"""
(function() {
    'use strict';
    // Guard against double-execution (ComfyUI Desktop makes two requests to /)
    if (window.__auto_dark_mode_loaded) return;
    window.__auto_dark_mode_loaded = true;
    var LOG = '/auto-dark-mode/log';
    function serverLog(l, m) {
        new Image().src = LOG + '?level=' + encodeURIComponent(l) +
            '&msg=' + encodeURIComponent(m) + '&t=' + Date.now();
    }
    serverLog('info', 'auto-dark-mode script loaded');

    var _lastApplied = null;
    var _lastLogTime = 0;

    function applyTheme(paletteId, silent) {
        try {
            var el = document.querySelector('#vue-app');
            if (!el || !el.__vue_app__) return false;
            var pinia = el.__vue_app__.config.globalProperties.$pinia;
            if (!pinia) return false;
            var ws = pinia._s.get('workspace');
            if (!ws || !ws.colorPalette || !ws.colorPalette.loadColorPalette) return false;

            // Skip if already set to this theme
            if (_lastApplied === paletteId && ws.colorPalette.activePaletteId === paletteId) {
                return true;
            }
            _lastApplied = paletteId;
            ws.colorPalette.loadColorPalette(paletteId);

            // Persist the setting so ComfyUI's own init doesn't override it
            try {
                var app = window.app;
                if (app && app.extensionManager && app.extensionManager.setting && app.extensionManager.setting.set) {
                    app.extensionManager.setting.set('Comfy.ColorPalette', paletteId);
                }
            } catch(_) {}

            // Only log if not silent and at least 5s since last log
            var now = Date.now();
            if (!silent && (now - _lastLogTime > 5000)) {
                _lastLogTime = now;
                serverLog('info', 'theme applied: ' + paletteId);
            }
            return true;
        } catch(e) {
            serverLog('error', 'applyTheme: ' + (e && e.message ? e.message : e));
            return false;
        }
    }

    // Watch for ComfyUI overriding our theme and silently fix it
    setInterval(function() {
        if (_currentTheme === 'dark' || _currentTheme === 'light') {
            applyTheme(_currentTheme, true);  // silent — don't log
        }
    }, 3000);

    // Python-detected OS theme (embedded at server startup).  This is the
    // authoritative value on startup because Electron's matchMedia can
    // disagree with the real OS setting.  Updated by WebSocket pushes.
    var _currentTheme = "/*OS_THEME_PLACEHOLDER*/";

    function sync() {
        // Use the Python-provided theme if available, otherwise matchMedia.
        if (_currentTheme !== 'dark' && _currentTheme !== 'light') {
            _currentTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        applyTheme(_currentTheme);
    }

    function init() {
        // matchMedia listener
        var mq = window.matchMedia('(prefers-color-scheme: dark)');
        if (mq.addEventListener) mq.addEventListener('change', sync);
        else if (mq.addListener) mq.addListener(sync);

        // WebSocket listener (Python -> frontend push)
        (function reg() {
            if (window.app && window.app.api && window.app.api.addEventListener) {
                window.app.api.addEventListener('auto-dark-mode.theme-changed', function(e) {
                    var t = e && e.detail && e.detail.theme;
                    if (t === 'dark' || t === 'light') {
                        _currentTheme = t;
                        applyTheme(t);
                    }
                });
                serverLog('info', 'ws listener registered');
            } else { setTimeout(reg, 500); }
        })();

        // Initial sync — ComfyUI's own init may override the theme,
        // so we retry once after a delay.
        setTimeout(sync, 2000);
        setTimeout(sync, 10000);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
"""

# =========================================================================
# HTTP routes + HTML injection middleware
# =========================================================================

try:
    from aiohttp import web
    from server import PromptServer

    _server = PromptServer.instance
    _app = getattr(_server, "app", None)

    # Serve the injected JS — embed the Python-detected OS theme so the
    # frontend uses it as the initial value (Electron's prefers-color-scheme
    # can disagree with the actual OS setting).
    _INJECTED_JS_WITH_THEME = _INJECTED_JS.replace(
        "/*OS_THEME_PLACEHOLDER*/",
        _detected,
    )
    async def _inject_js(_req):
        return web.Response(
            text=_INJECTED_JS_WITH_THEME,
            content_type="application/javascript",
        )
    _server.routes.get("/auto-dark-mode/inject.js")(_inject_js)

    # Log endpoint for JS diagnostics
    async def _log(request):
        try:
            if request.method == "POST":
                b = await request.json()
                msg, level = b.get("message", ""), b.get("level", "info")
            else:
                msg = request.query.get("msg", "")
                level = request.query.get("level", "info")
            getattr(_logger, level, _logger.info)("[skkut-utils/auto-dark-mode] [frontend] %s", msg)
        except Exception:
            pass
        return web.json_response({"ok": True})
    _server.routes.get("/auto-dark-mode/log")(_log)
    _server.routes.post("/auto-dark-mode/log")(_log)

    # Middleware: inject <script> into the root HTML page.
    if _app is not None:
        @web.middleware
        async def _mw(request, handler):
            resp = await handler(request)
            is_html = (request.path == "/" or request.path.endswith(".html"))
            if resp.status == 200 and is_html:
                try:
                    if hasattr(resp, '_path'):
                        with open(resp._path, 'r', encoding='utf-8') as f:
                            body = f.read()
                    else:
                        body = await resp.text()
                    tag = '<script src="/auto-dark-mode/inject.js"></script>'
                    if tag not in body:
                        body = body.replace("</head>", tag + "</head>", 1)
                    return web.Response(text=body, content_type="text/html",
                                         status=resp.status)
                except Exception:
                    return resp
            return resp
        _app.middlewares.insert(0, _mw)

    _logger.info("[skkut-utils/auto-dark-mode] Routes and middleware registered.")
except Exception as _e:
    _logger.warning("[skkut-utils/auto-dark-mode] Route setup failed: %s", _e)
