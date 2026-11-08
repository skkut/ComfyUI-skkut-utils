#!/usr/bin/env python3
"""Developer tool: visual editor for the Skutils Style Selector library.

This is **not** part of the ComfyUI plugin. It lives in ``tools/``, is never
imported by the repo, and is excluded from the Comfy Registry package by
``.comfyignore`` (it stays available in the GitHub repository).

What it does
------------
Serves a small editor for ``skutils_style_selector/styles.json``:

  * drag a style (by its grip) to reorder it inside its section;
  * pin styles to anchor them in place — pinning never reorders, pinned rows
    cannot be moved, and a contiguous pinned block at the top of a section
    stays on top (move-to-top inserts directly below it); pinned state is
    stored as ``"pinned": true`` on the entry;
  * use each row's dropdown to move a style to another section, or create
    a new section;
  * search/filter to find styles quickly;
  * save back to ``styles.json`` (atomic write + timestamped backup).

Usage
-----
    python tools/reorganize_styles.py

Options:
    --port N          port on 127.0.0.1 (default 8765; 0 = random free port)
    --library PATH    edit a different styles.json (handy for testing)
    --no-browser      do not open the browser automatically

Only 127.0.0.1 is bound, and every request requires a per-run random token,
so other machines and random web pages cannot read or overwrite the file.
The token is part of the URL printed on startup.

After saving, restart ComfyUI so the picker reloads the library (the backend
caches styles.json at import time).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import secrets
import shutil
import sys
import tempfile
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LIBRARY = os.path.join(REPO_ROOT, "skutils_style_selector", "styles.json")
THUMBS_DIR = os.path.join(REPO_ROOT, "skutils_style_selector", "assets", "thumbs")
BACKUP_DIR = os.path.join(REPO_ROOT, "tools", "backups")

MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_SECTION_LEN = 60
MAX_SECTIONS = 500
BACKUPS_KEPT = 20

_save_lock = threading.Lock()

_IMAGE_TYPES = {
    ".webp": "image/webp",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".avif": "image/avif",
}


class SaveError(Exception):
    """A save payload that cannot be applied safely."""


# ---------------------------------------------------------------------------
# Library read / validate / write
# ---------------------------------------------------------------------------

def read_library(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("styles.json must contain a JSON object")
    if not isinstance(data.get("styles"), list):
        raise ValueError("styles.json has no `styles` list")
    return data


def _clean_sections(raw):
    if not isinstance(raw, list) or not raw:
        raise SaveError("`sections` must be a non-empty list.")
    if len(raw) > MAX_SECTIONS:
        raise SaveError(f"Too many sections (max {MAX_SECTIONS}).")
    cleaned = []
    seen = set()
    for item in raw:
        if not isinstance(item, str):
            raise SaveError("Section names must be strings.")
        name = item.strip()
        if not name:
            raise SaveError("Section names cannot be empty.")
        if len(name) > MAX_SECTION_LEN:
            raise SaveError(
                f"Section name {name!r} is longer than {MAX_SECTION_LEN} characters."
            )
        if any(ord(char) < 32 for char in name):
            raise SaveError(f"Section name {name!r} contains control characters.")
        if name in seen:
            raise SaveError(f"Duplicate section name {name!r}.")
        seen.add(name)
        cleaned.append(name)
    return cleaned


def _ordered_styles(raw_order, sections, styles):
    if not isinstance(raw_order, list):
        raise SaveError("`order` must be a list.")
    if len(raw_order) != len(styles):
        raise SaveError(
            "The editor sent a different number of styles than styles.json contains. "
            "Reload the page and try again."
        )

    by_name = {}
    for style in styles:
        if not isinstance(style, dict):
            raise SaveError("styles.json contains a non-object entry.")
        name = style.get("name")
        if not isinstance(name, str) or not name:
            raise SaveError("styles.json contains an entry without a name.")
        if name in by_name:
            raise SaveError(
                f"styles.json has duplicate style name {name!r}; fix that manually first."
            )
        by_name[name] = style

    section_set = set(sections)
    seen = set()
    ordered = []
    for item in raw_order:
        if not isinstance(item, dict):
            raise SaveError("`order` entries must be objects.")
        name = item.get("name")
        section = item.get("section")
        pinned = item.get("pinned")
        if name not in by_name:
            raise SaveError(f"Unknown style {name!r}. Reload the page and try again.")
        if name in seen:
            raise SaveError(f"Duplicate style {name!r} in the save payload.")
        if section not in section_set:
            raise SaveError(f"Unknown section {section!r}.")
        if pinned is not None and not isinstance(pinned, bool):
            raise SaveError(f"`pinned` for style {name!r} must be true or false.")
        seen.add(name)
        style = by_name[name]
        style["section"] = section
        if "pinned" in item:
            if pinned:
                style["pinned"] = True
            else:
                style.pop("pinned", None)
        ordered.append(style)

    missing = set(by_name) - seen
    if missing:
        examples = ", ".join(sorted(missing)[:5])
        raise SaveError(
            f"{len(missing)} style(s) missing from the save payload ({examples}…). "
            "Reload the page and try again."
        )
    return ordered


def _make_backup(path):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    destination = os.path.join(BACKUP_DIR, f"styles-{stamp}.json")
    shutil.copy2(path, destination)
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "styles-*.json")))
    for old in backups[:-BACKUPS_KEPT]:
        try:
            os.remove(old)
        except OSError:
            pass
    return destination


def _write_atomic(path, data):
    directory = os.path.dirname(os.path.abspath(path))
    handle, temporary = tempfile.mkstemp(prefix=".styles-", suffix=".json", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=1, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def save_order(path, payload):
    if not isinstance(payload, dict):
        raise SaveError("Request body must be a JSON object.")
    sections = _clean_sections(payload.get("sections"))

    with _save_lock:
        data = read_library(path)
        styles = data["styles"]
        ordered = _ordered_styles(payload.get("order"), sections, styles)
        data["sections"] = sections
        data["styles"] = ordered
        backup = _make_backup(path)
        _write_atomic(path, data)

    pinned = sum(1 for style in ordered if style.get("pinned"))
    return len(ordered), backup, pinned


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class EditorHandler(BaseHTTPRequestHandler):
    server_version = "SkutilsStyleEditor/1.0"

    # Keep the console clean: thumbnails would otherwise log one line each.
    def log_message(self, fmt, *args):
        pass

    # -- helpers -----------------------------------------------------------

    def _token_ok(self, supplied):
        return bool(supplied) and secrets.compare_digest(supplied, self.server.token)

    def _send(self, code, body=b"", content_type="application/octet-stream", cache="no-store"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _deny(self, code, message):
        self._send_json(code, {"error": message})

    def _require_token(self, query):
        supplied = self.headers.get("X-Editor-Token") or (query.get("token") or [""])[0]
        if not self._token_ok(supplied):
            self._deny(403, "Invalid or missing editor token.")
            return False
        return True

    # -- GET ---------------------------------------------------------------

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            token = (query.get("token") or [""])[0]
            if not self._token_ok(token):
                self._send(
                    403,
                    "Open the editor URL printed in the terminal — it contains "
                    "the access token.".encode("utf-8"),
                    "text/plain; charset=utf-8",
                )
                return
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path == "/api/library":
            if not self._require_token(query):
                return
            try:
                data = read_library(self.server.library_path)
            except Exception as error:  # noqa: BLE001 - report to the page
                self._deny(500, f"Could not read {self.server.library_path}: {error}")
                return
            self._send_json(
                200,
                {
                    "path": self.server.library_path,
                    "version": data.get("version", 1),
                    "credits": data.get("credits", {}),
                    "sections": data.get("sections", []),
                    "styles": data.get("styles", []),
                },
            )
            return

        if path.startswith("/thumbs/"):
            if not self._require_token(query):
                return
            self._serve_thumb(unquote(path[len("/thumbs/"):]))
            return

        if path == "/favicon.ico":
            self._send(204)
            return

        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _serve_thumb(self, name):
        if not name or name in (".", "..") or "/" in name or "\\" in name:
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        root = os.path.realpath(THUMBS_DIR)
        full = os.path.realpath(os.path.join(root, name))
        try:
            inside = os.path.normcase(os.path.commonpath([root, full])) == os.path.normcase(root)
        except ValueError:
            inside = False
        if not inside or not os.path.isfile(full):
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        content_type = _IMAGE_TYPES.get(os.path.splitext(full)[1].lower())
        if not content_type:
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        try:
            with open(full, "rb") as handle:
                body = handle.read()
        except OSError:
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        self._send(200, body, content_type, cache="private, max-age=300")

    # -- POST --------------------------------------------------------------

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/save":
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return

        query = parse_qs(parsed.query)
        if not self._require_token(query):
            return

        origin = self.headers.get("Origin")
        if origin and origin not in self.server.allowed_origins:
            self._deny(403, "Cross-origin requests are not allowed.")
            return

        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length <= 0:
            self._deny(400, "Empty request body.")
            return
        if length > MAX_BODY_BYTES:
            self._deny(413, "Save payload is too large.")
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            self._deny(400, f"Invalid JSON: {error}")
            return

        try:
            count, backup, pinned = save_order(self.server.library_path, payload)
        except SaveError as error:
            self._deny(400, str(error))
            return
        except Exception as error:  # noqa: BLE001 - report to the page
            self._deny(500, f"Could not save: {error}")
            return

        relative_backup = os.path.relpath(backup, REPO_ROOT).replace(os.sep, "/")
        saved_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self._send_json(
            200,
            {
                "ok": True,
                "count": count,
                "pinned": pinned,
                "saved_at": saved_at,
                "backup": relative_backup,
            },
        )


# ---------------------------------------------------------------------------
# Editor page (single file, no external assets)
# ---------------------------------------------------------------------------

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Skutils Style Editor</title>
<style>
  :root {
    --bg: #0f1116;
    --panel: #151922;
    --panel-2: #1b2130;
    --panel-3: #222a3c;
    --border: #2a3142;
    --border-strong: #39425a;
    --text: #e8ebf2;
    --muted: #8a93a6;
    --accent: #7c9cff;
    --accent-strong: #5b7fff;
    --ok: #6fcf97;
    --warn: #f2c94c;
    --err: #ff6b6b;
    color-scheme: dark;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    --thumb-size: 300px;
    background: var(--bg);
    color: var(--text);
    font: 13px/1.4 "Segoe UI", system-ui, -apple-system, sans-serif;
    min-height: 100vh;
  }
  body.lightbox-open { overflow: hidden; }
  button, select, input { font: inherit; color: inherit; }
  .topbar {
    position: sticky;
    top: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 10px 18px;
    background: linear-gradient(180deg, rgba(20, 24, 33, .98), rgba(20, 24, 33, .92));
    border-bottom: 1px solid var(--border);
    backdrop-filter: blur(8px);
  }
  .brand {
    display: flex;
    align-items: baseline;
    gap: 8px;
    white-space: nowrap;
  }
  .brand .logo {
    font-weight: 700;
    letter-spacing: .02em;
    background: linear-gradient(90deg, var(--accent), #b58cff);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }
  .brand .sub { font-weight: 600; color: var(--text); }
  .badge {
    font-size: 9px;
    letter-spacing: .12em;
    padding: 2px 6px;
    border: 1px solid var(--border-strong);
    border-radius: 999px;
    color: var(--muted);
    transform: translateY(-1px);
  }
  .path {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--muted);
    font-size: 11px;
  }
  .actions { display: flex; align-items: center; gap: 8px; }
  .status { font-size: 11px; color: var(--muted); max-width: 46ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .status.ok { color: var(--ok); }
  .status.warn { color: var(--warn); }
  .status.error { color: var(--err); }
  .btn {
    border: 1px solid var(--border-strong);
    background: var(--panel-2);
    border-radius: 7px;
    padding: 6px 12px;
    cursor: pointer;
  }
  .btn:hover:not(:disabled) { border-color: var(--accent); }
  .btn:disabled { opacity: .45; cursor: default; }
  .btn.primary {
    background: linear-gradient(180deg, var(--accent), var(--accent-strong));
    border-color: var(--accent-strong);
    color: #0b1020;
    font-weight: 700;
  }
  .toolbar {
    position: sticky;
    top: 53px;
    z-index: 15;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    padding: 9px 18px;
    background: rgba(15, 17, 22, .96);
    border-bottom: 1px solid var(--border);
  }
  .toolbar input[type="search"] {
    flex: 1;
    min-width: 180px;
    max-width: 560px;
    border: 1px solid var(--border-strong);
    background: var(--panel);
    border-radius: 7px;
    padding: 7px 10px;
    outline: none;
  }
  .toolbar input[type="search"]:focus { border-color: var(--accent); }
  .toolbar select {
    border: 1px solid var(--border-strong);
    background: var(--panel);
    border-radius: 7px;
    padding: 7px 8px;
    max-width: 260px;
  }
  .counts { color: var(--muted); font-size: 11px; white-space: nowrap; }
  main { padding: 4px 18px 40px; max-width: 1280px; margin: 0 auto; }
  .group {
    margin: 16px 0;
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    background: var(--panel);
  }
  .group-head {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 12px;
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    border-bottom: 1px solid var(--border);
  }
  .group.collapsed .group-head { border-bottom: 0; }
  .group.collapsed .rows { display: none; }
  body.filtering .group.collapsed .rows { display: block; }
  body.filtering .group.collapsed .group-head { border-bottom: 1px solid var(--border); }
  .group-head h2 { margin: 0; font-size: 13px; font-weight: 700; letter-spacing: .01em; }
  .count {
    font-size: 10px;
    color: var(--muted);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 1px 7px;
  }
  .count.pinned-count { color: var(--warn); border-color: rgba(242, 201, 76, .45); }
  .icon-btn {
    border: 1px solid transparent;
    background: transparent;
    color: var(--muted);
    border-radius: 5px;
    width: 24px;
    height: 24px;
    padding: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
  }
  .icon-btn:hover { background: var(--panel-3); color: var(--text); }
  .row {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 10px 12px;
    border-top: 1px solid var(--border);
    background: var(--panel);
  }
  .group .rows .row:first-child { border-top: 0; }
  .row:hover { background: var(--panel-2); }
  .row.dragging { opacity: .45; outline: 1px dashed var(--accent); outline-offset: -1px; }
  .row.pinned {
    background-image: linear-gradient(90deg, rgba(242, 201, 76, .09), transparent 260px);
    box-shadow: inset 3px 0 0 var(--warn);
  }
  .grip {
    flex: none;
    color: var(--muted);
    font-size: 17px;
    line-height: 1;
    padding: 4px 2px;
    cursor: grab;
    user-select: none;
  }
  .row-number {
    flex: none;
    min-width: 30px;
    padding-top: 5px;
    text-align: right;
    color: var(--muted);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    user-select: none;
  }
  body.filtering .grip { cursor: not-allowed; opacity: .35; }
  .grip.anchored { cursor: default; opacity: .3; }
  .thumb {
    flex: none;
    width: var(--thumb-size);
    height: var(--thumb-size);
    border-radius: 6px;
    overflow: hidden;
    background: #0b0d12;
    display: grid;
    place-items: center;
    color: var(--muted);
    font-size: clamp(10px, calc(var(--thumb-size) * 0.12), 40px);
    font-weight: 700;
    letter-spacing: .04em;
    cursor: zoom-in;
    transition: outline-color .12s ease;
    outline: 2px solid transparent;
    outline-offset: 1px;
  }
  .thumb:hover, .thumb:focus-visible { outline-color: var(--accent); }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .info { flex: 1; min-width: 0; padding-top: 2px; }
  .info-head { display: flex; align-items: center; gap: 10px; }
  .name {
    flex: 1;
    min-width: 0;
    font-size: 14px;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sub {
    color: var(--muted);
    font-size: 12px;
    line-height: 1.55;
    margin-top: 5px;
    white-space: normal;
    overflow: visible;
    text-overflow: clip;
    overflow-wrap: anywhere;
  }
  mark {
    background: rgba(124, 156, 255, .38);
    color: var(--text);
    border-radius: 2px;
    padding: 0 1px;
  }
  .section-select {
    flex: none;
    width: 190px;
    border: 1px solid var(--border-strong);
    background: var(--panel-2);
    border-radius: 6px;
    padding: 5px 6px;
    font-size: 12px;
  }
  .section-select:focus { outline: none; border-color: var(--accent); }
  .moves { flex: none; display: flex; gap: 3px; }
  .moves .icon-btn {
    border-color: var(--border);
    background: var(--panel-2);
    font-size: 12px;
  }
  .moves .icon-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
  .moves .pin-btn { filter: grayscale(1); opacity: .5; }
  .moves .pin-btn:hover { filter: none; opacity: 1; }
  .moves .pin-btn.active {
    filter: none;
    opacity: 1;
    background: rgba(242, 201, 76, .14);
    border-color: var(--warn);
  }
  .empty { padding: 14px; color: var(--muted); font-style: italic; }
  .fatal {
    margin: 30px auto;
    max-width: 720px;
    padding: 18px;
    border: 1px solid var(--err);
    border-radius: 10px;
    background: rgba(255, 107, 107, .08);
    color: #ffd7d7;
  }
  /* Full-size preview */
  .lightbox {
    position: fixed;
    inset: 0;
    z-index: 100;
    display: none;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(5, 7, 11, .9);
    backdrop-filter: blur(6px);
  }
  .lightbox.open { display: flex; }
  .lightbox-figure {
    margin: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    max-width: 100%;
    max-height: 100%;
  }
  .lightbox-image {
    display: block;
    width: auto;
    height: auto;
    max-width: min(90vw, 1024px);
    max-height: calc(100vh - 280px);
    object-fit: contain;
    border-radius: 10px;
    background: #0b0d12;
    box-shadow: 0 24px 80px rgba(0, 0, 0, .65);
  }
  .lightbox-placeholder {
    display: none;
    place-items: center;
    width: min(70vw, 512px);
    height: min(70vw, 512px);
    border: 1px dashed var(--border-strong);
    border-radius: 10px;
    background: #12151d;
    color: var(--muted);
    font-size: 48px;
    font-weight: 700;
  }
  .lightbox-meta {
    max-width: min(90vw, 900px);
    text-align: center;
  }
  .lightbox-name { font-size: 16px; font-weight: 700; }
  .lightbox-sub { color: var(--muted); font-size: 11px; margin-top: 2px; }
  .lightbox-prompt {
    color: var(--muted);
    font-size: 12px;
    line-height: 1.55;
    margin-top: 6px;
    max-height: none;
    overflow: visible;
    white-space: normal;
    overflow-wrap: anywhere;
  }
  .lightbox button {
    border: 1px solid var(--border-strong);
    background: rgba(21, 25, 34, .92);
    color: var(--text);
    cursor: pointer;
  }
  .lightbox button:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
  .lightbox button:disabled { opacity: .25; cursor: default; }
  .lb-close {
    position: fixed;
    top: 16px;
    right: 20px;
    width: 40px;
    height: 40px;
    border-radius: 10px;
    font-size: 22px;
    line-height: 1;
  }
  .lb-nav {
    position: fixed;
    top: 50%;
    transform: translateY(-50%);
    width: 44px;
    height: 72px;
    border-radius: 10px;
    font-size: 26px;
    line-height: 1;
  }
  .lb-prev { left: 16px; }
  .lb-next { right: 16px; }
  footer {
    max-width: 1280px;
    margin: 0 auto;
    padding: 0 18px 40px;
    color: var(--muted);
    font-size: 11px;
    line-height: 1.7;
  }
  footer code {
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 4px;
  }
  @media (max-width: 760px) {
    body { --thumb-size: 180px; }
    .path { display: none; }
    .section-select { width: 130px; }
    .topbar { flex-wrap: wrap; gap: 8px; }
  }
</style>
</head>
<body>
<header class="topbar">
  <div class="brand">
    <span class="logo">Skutils</span>
    <span class="sub">Style Editor</span>
    <span class="badge">LOCAL</span>
  </div>
  <div class="path" id="filePath" title=""></div>
  <div class="actions">
    <span class="status" id="status"></span>
    <button type="button" class="btn" id="reloadBtn" title="Reload styles.json from disk">Reload</button>
    <button type="button" class="btn primary" id="saveBtn" disabled title="Save as styles.json (Ctrl+S)">Save</button>
  </div>
</header>
<div class="toolbar">
  <input type="search" id="search" placeholder="Search name, section, source, or prompt text…" spellcheck="false" autocomplete="off">
  <select id="sectionFilter" title="Show one section"></select>
  <span class="counts" id="counts"></span>
</div>
<main id="sections"></main>
<footer>
  Drag a row by its <strong>⠿</strong> grip to reorder it within its section, use <strong>↑</strong> /
  <strong>↓</strong> for single steps, or <strong>⤒</strong> / <strong>⤓</strong> to jump to the top or
  bottom. Use the dropdown on a row to move it to another section; choosing
  <strong>＋ New section…</strong> creates one.
  Click any thumbnail for a full-size preview (<strong>←</strong> / <strong>→</strong> to browse,
  <strong>Esc</strong> to close). Saving updates <code>skutils_style_selector/styles.json</code> and keeps
  a timestamped backup in <code>tools/backups/</code>. Restart ComfyUI afterwards so the picker
  reloads the library.
</footer>
<div class="lightbox" id="lightbox" aria-hidden="true">
  <button type="button" class="lb-close" id="lbClose" title="Close (Esc)" aria-label="Close">×</button>
  <button type="button" class="lb-nav lb-prev" id="lbPrev" title="Previous (←)" aria-label="Previous">‹</button>
  <figure class="lightbox-figure">
    <img class="lightbox-image" id="lbImage" alt="">
    <div class="lightbox-placeholder" id="lbPlaceholder"></div>
    <figcaption class="lightbox-meta">
      <div class="lightbox-name" id="lbName"></div>
      <div class="lightbox-sub" id="lbSub"></div>
      <div class="lightbox-prompt" id="lbPrompt"></div>
    </figcaption>
  </figure>
  <button type="button" class="lb-nav lb-next" id="lbNext" title="Next (→)" aria-label="Next">›</button>
</div>
<script>
(function () {
  "use strict";

  var TOKEN = new URLSearchParams(location.search).get("token") || "";
  var API_HEADERS = { "X-Editor-Token": TOKEN };

  var sectionsEl = document.getElementById("sections");
  var searchEl = document.getElementById("search");
  var filterEl = document.getElementById("sectionFilter");
  var countsEl = document.getElementById("counts");
  var statusEl = document.getElementById("status");
  var saveBtn = document.getElementById("saveBtn");
  var reloadBtn = document.getElementById("reloadBtn");
  var filePathEl = document.getElementById("filePath");
  var lightbox = document.getElementById("lightbox");
  var lbImage = document.getElementById("lbImage");
  var lbPlaceholder = document.getElementById("lbPlaceholder");
  var lbName = document.getElementById("lbName");
  var lbSub = document.getElementById("lbSub");
  var lbPrompt = document.getElementById("lbPrompt");
  var lbPrev = document.getElementById("lbPrev");
  var lbNext = document.getElementById("lbNext");
  var lbClose = document.getElementById("lbClose");

  var sectionOrder = [];
  var groups = new Map();
  var collapsed = new Set();
  var byUid = new Map();
  var uidSeq = 1;
  var total = 0;
  var dirty = false;
  var saving = false;
  var drag = null;
  var searchTimer = null;
  var lbList = [];
  var lbIndex = -1;

  // -- small helpers -----------------------------------------------------

  function setStatus(text, kind) {
    statusEl.textContent = text || "";
    statusEl.className = "status" + (kind ? " " + kind : "");
  }

  function setDirty(value) {
    dirty = value;
    saveBtn.disabled = saving || !dirty;
    if (dirty) setStatus("Unsaved changes", "warn");
  }

  async function readError(response) {
    try {
      var data = await response.json();
      return data.error || (response.status + " " + response.statusText);
    } catch (_) {
      return response.status + " " + response.statusText;
    }
  }

  function makeButton(label, title) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "icon-btn";
    button.textContent = label;
    if (title) button.title = title;
    return button;
  }

  function thumbUrl(style) {
    if (!style.thumb) return "";
    return "/thumbs/" + encodeURIComponent(style.thumb) + "?token=" + encodeURIComponent(TOKEN);
  }

  function initials(name) {
    var words = String(name || "?").split(/\s+/).filter(Boolean).slice(0, 2);
    return words.map(function (word) { return word.charAt(0); }).join("").toUpperCase() || "?";
  }

  function styleMatches(style, query) {
    return style._name.indexOf(query) !== -1 ||
      style._section.indexOf(query) !== -1 ||
      style._source.indexOf(query) !== -1 ||
      style._prompt.indexOf(query) !== -1;
  }

  function appendHighlighted(parent, text, query) {
    var value = String(text || "");
    var needle = String(query || "").toLowerCase();
    if (!needle) {
      parent.appendChild(document.createTextNode(value));
      return;
    }
    var haystack = value.toLowerCase();
    var index = 0;
    while (index <= haystack.length) {
      var found = haystack.indexOf(needle, index);
      if (found === -1) break;
      if (found > index) {
        parent.appendChild(document.createTextNode(value.slice(index, found)));
      }
      var mark = document.createElement("mark");
      mark.textContent = value.slice(found, found + needle.length);
      parent.appendChild(mark);
      index = found + needle.length;
    }
    if (index < value.length) {
      parent.appendChild(document.createTextNode(value.slice(index)));
    }
  }

  function topPinnedCount(list) {
    var count = 0;
    while (count < list.length && list[count].pinned) count += 1;
    return count;
  }

  function totalPinned(list) {
    return list.filter(function (style) { return style.pinned; }).length;
  }

  // -- loading -----------------------------------------------------------

  async function load() {
    setStatus("Loading…");
    var response = await fetch("/api/library", { headers: API_HEADERS, cache: "no-store" });
    if (!response.ok) throw new Error(await readError(response));
    var data = await response.json();

    sectionOrder = Array.isArray(data.sections) ? data.sections.slice() : [];
    groups = new Map();
    byUid.clear();
    collapsed.clear();
    uidSeq = 1;

    sectionOrder.forEach(function (section) { groups.set(section, []); });

    (data.styles || []).forEach(function (style) {
      style.pinned = style.pinned === true;
      style._uid = uidSeq++;
      style._name = String(style.name || "").toLowerCase();
      style._section = String(style.section || "").toLowerCase();
      style._source = String(style.source || "").toLowerCase();
      style._prompt = String(style.prompt || "").toLowerCase();
      byUid.set(style._uid, style);
      if (!groups.has(style.section)) {
        groups.set(style.section, []);
        sectionOrder.push(style.section);
      }
      groups.get(style.section).push(style);
    });

    total = (data.styles || []).length;
    filePathEl.textContent = data.path || "";
    filePathEl.title = data.path || "";
    document.title = "Skutils Style Editor — " + total + " styles";

    setDirty(false);
    refreshFilter();
    render();
    setStatus("Loaded " + total + " styles", "ok");
  }

  // -- rendering ---------------------------------------------------------

  function fillSectionSelect(select, value) {
    if (select.dataset.filled === "1") {
      select.value = value;
      return;
    }
    var fragment = document.createDocumentFragment();
    sectionOrder.forEach(function (section) {
      var option = document.createElement("option");
      option.value = section;
      option.textContent = section;
      fragment.appendChild(option);
    });
    var newOption = document.createElement("option");
    newOption.value = "__new__";
    newOption.textContent = "＋ New section…";
    fragment.appendChild(newOption);
    select.replaceChildren(fragment);
    select.dataset.filled = "1";
    select.value = value;
  }

  function buildRow(style, position, query) {
    var row = document.createElement("div");
    row.className = "row" + (style.pinned ? " pinned" : "");
    row.dataset.uid = String(style._uid);

    var grip = document.createElement("span");
    grip.className = "grip" + (style.pinned ? " anchored" : "");
    grip.draggable = !style.pinned;
    grip.title = style.pinned
      ? "Pinned styles are anchored in place"
      : "Drag to reorder within this section";
    grip.textContent = "⠿";

    var number = document.createElement("span");
    number.className = "row-number";
    number.textContent = position;
    number.title = "Position in section";

    var thumb = document.createElement("div");
    thumb.className = "thumb";
    thumb.title = "Click to view full size";
    thumb.tabIndex = 0;
    thumb.setAttribute("role", "button");
    thumb.addEventListener("click", function (event) {
      event.stopPropagation();
      openLightbox(style);
    });
    thumb.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openLightbox(style);
      }
    });
    var url = thumbUrl(style);
    if (url) {
      var image = document.createElement("img");
      image.loading = "lazy";
      image.decoding = "async";
      image.alt = "";
      image.src = url;
      image.addEventListener("error", function () {
        image.remove();
        thumb.textContent = initials(style.name);
      });
      thumb.appendChild(image);
    } else {
      thumb.textContent = initials(style.name);
    }

    var info = document.createElement("div");
    info.className = "info";
    var name = document.createElement("div");
    name.className = "name";
    appendHighlighted(name, style.name, query);
    var sub = document.createElement("div");
    sub.className = "sub";
    if (style.source) {
      appendHighlighted(sub, style.source, query);
      sub.appendChild(document.createTextNode(" · "));
    }
    appendHighlighted(sub, style.prompt, query);

    var select = document.createElement("select");
    select.className = "section-select";
    select.title = "Move this style to another section";
    var current = document.createElement("option");
    current.value = style.section;
    current.textContent = style.section;
    select.appendChild(current);
    select.addEventListener("pointerdown", function () {
      fillSectionSelect(select, style.section);
    });
    select.addEventListener("focus", function () {
      fillSectionSelect(select, style.section);
    });
    select.addEventListener("change", function () {
      var target = select.value;
      select.value = style.section;
      handleRecategorize(style, target);
    });

    var moves = document.createElement("div");
    moves.className = "moves";
    var pin = makeButton("📌", style.pinned ? "Unpin this style" : "Pin this style in place");
    pin.classList.add("pin-btn");
    pin.classList.toggle("active", !!style.pinned);
    pin.setAttribute("aria-pressed", style.pinned ? "true" : "false");
    pin.setAttribute("aria-label", style.pinned ? "Unpin style" : "Pin style in place");
    pin.addEventListener("click", function () { togglePin(style); });

    var anchoredTitle = "Pinned styles are anchored in place";
    var toTop = makeButton(
      "⤒",
      style.pinned ? anchoredTitle : "Move below the pinned styles at the top"
    );
    var up = makeButton("↑", style.pinned ? anchoredTitle : "Move up");
    var down = makeButton("↓", style.pinned ? anchoredTitle : "Move down");
    var toBottom = makeButton(
      "⤓",
      style.pinned ? anchoredTitle : "Move to the bottom of the section"
    );

    var list = groups.get(style.section) || [];
    var index = list.indexOf(style);
    var topPins = topPinnedCount(list);
    if (style.pinned) {
      toTop.disabled = true;
      up.disabled = true;
      down.disabled = true;
      toBottom.disabled = true;
    } else {
      toTop.disabled = index === topPins;
      up.disabled = index <= topPins;
      down.disabled = index >= list.length - 1;
      toBottom.disabled = index >= list.length - 1;
    }

    toTop.addEventListener("click", function () { moveToTop(style); });
    up.addEventListener("click", function () { moveBy(style, -1); });
    down.addEventListener("click", function () { moveBy(style, 1); });
    toBottom.addEventListener("click", function () { moveToBottom(style); });
    moves.appendChild(pin);
    moves.appendChild(toTop);
    moves.appendChild(up);
    moves.appendChild(down);
    moves.appendChild(toBottom);

    var head = document.createElement("div");
    head.className = "info-head";
    head.appendChild(name);
    head.appendChild(select);
    head.appendChild(moves);
    info.appendChild(head);
    info.appendChild(sub);

    row.appendChild(grip);
    row.appendChild(number);
    row.appendChild(thumb);
    row.appendChild(info);
    return row;
  }

  function buildGroup(section, visible, fullCount, searching, query) {
    var group = document.createElement("section");
    group.className = "group";
    group.dataset.section = section;

    var head = document.createElement("header");
    head.className = "group-head";

    var caret = makeButton(collapsed.has(section) ? "▸" : "▾", "Collapse / expand section");
    caret.classList.add("caret");
    caret.addEventListener("click", function () {
      if (collapsed.has(section)) collapsed.delete(section);
      else collapsed.add(section);
      group.classList.toggle("collapsed", collapsed.has(section));
      caret.textContent = collapsed.has(section) ? "▸" : "▾";
    });

    var title = document.createElement("h2");
    appendHighlighted(title, section, query);

    var count = document.createElement("span");
    count.className = "count";
    count.textContent = visible.length === fullCount
      ? String(fullCount)
      : visible.length + " / " + fullCount;

    head.appendChild(caret);
    head.appendChild(title);
    head.appendChild(count);

    var pinnedTotal = totalPinned(groups.get(section) || []);
    if (pinnedTotal) {
      var pinnedChip = document.createElement("span");
      pinnedChip.className = "count pinned-count";
      pinnedChip.textContent = "📌 " + pinnedTotal;
      pinnedChip.title = pinnedTotal + " pinned (anchored) style" +
        (pinnedTotal === 1 ? "" : "s") + " in this section";
      head.appendChild(pinnedChip);
    }
    group.appendChild(head);

    if (collapsed.has(section) && !searching) group.classList.add("collapsed");

    var rows = document.createElement("div");
    rows.className = "rows";
    rows.dataset.section = section;
    if (visible.length === 0) {
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "No styles in this section.";
      rows.appendChild(empty);
    } else {
      var full = groups.get(section) || [];
      visible.forEach(function (style) {
        rows.appendChild(buildRow(style, full.indexOf(style) + 1, query));
      });
    }
    group.appendChild(rows);
    return group;
  }

  function render() {
    closeLightbox();
    var query = searchEl.value.trim().toLowerCase();
    var only = filterEl.value;
    document.body.classList.toggle("filtering", !!query);

    var fragment = document.createDocumentFragment();
    var shown = 0;

    sectionOrder.forEach(function (section) {
      if (only && section !== only) return;
      var full = groups.get(section) || [];
      var visible = query ? full.filter(function (style) {
        return styleMatches(style, query);
      }) : full;
      if (query && visible.length === 0) return;
      fragment.appendChild(buildGroup(section, visible, full.length, !!query, query));
      shown += visible.length;
    });

    sectionsEl.replaceChildren(fragment);
    countsEl.textContent = (query || only)
      ? "Showing " + shown + " of " + total + " styles"
      : total + " styles · " + sectionOrder.length + " sections";
  }

  function refreshGroup(section) {
    var element = Array.prototype.slice.call(sectionsEl.querySelectorAll(".group"))
      .find(function (group) { return group.dataset.section === section; });
    if (!element) {
      render();
      return;
    }
    var full = groups.get(section) || [];
    var query = searchEl.value.trim().toLowerCase();
    var visible = query ? full.filter(function (style) {
      return styleMatches(style, query);
    }) : full;
    element.replaceWith(buildGroup(section, visible, full.length, !!query, query));
  }

  function refreshFilter() {
    var current = filterEl.value;
    var fragment = document.createDocumentFragment();
    var all = document.createElement("option");
    all.value = "";
    all.textContent = "All sections";
    fragment.appendChild(all);
    sectionOrder.forEach(function (section) {
      var option = document.createElement("option");
      option.value = section;
      option.textContent = section + " (" + (groups.get(section) || []).length + ")";
      fragment.appendChild(option);
    });
    filterEl.replaceChildren(fragment);
    filterEl.value = sectionOrder.indexOf(current) !== -1 ? current : "";
  }

  // -- full-size preview -------------------------------------------------

  function visibleRows() {
    return Array.prototype.slice.call(sectionsEl.querySelectorAll(".rows .row"));
  }

  function openLightbox(style) {
    var order = visibleRows().map(function (row) { return Number(row.dataset.uid); });
    var index = order.indexOf(style._uid);
    if (index === -1) {
      order = [style._uid];
      index = 0;
    }
    lbList = order;
    lbIndex = index;
    showLightboxItem();
    lightbox.classList.add("open");
    lightbox.setAttribute("aria-hidden", "false");
    document.body.classList.add("lightbox-open");
    lbClose.focus();
  }

  function showLightboxItem() {
    var style = byUid.get(lbList[lbIndex]);
    if (!style) return;
    var query = searchEl.value.trim().toLowerCase();
    lbName.replaceChildren();
    appendHighlighted(lbName, style.name, query);
    lbSub.textContent = style.section +
      (style.pinned ? " · pinned" : "") +
      (style.source ? " · " + style.source : "") +
      " · " + (lbIndex + 1) + " / " + lbList.length;
    lbPrompt.replaceChildren();
    appendHighlighted(lbPrompt, style.prompt, query);

    var url = thumbUrl(style);
    if (url) {
      lbPlaceholder.style.display = "none";
      lbImage.style.display = "block";
      lbImage.src = url;
      lbImage.alt = style.name;
    } else {
      lbImage.removeAttribute("src");
      lbImage.style.display = "none";
      lbPlaceholder.style.display = "grid";
      lbPlaceholder.textContent = initials(style.name);
    }

    lbPrev.disabled = lbIndex <= 0;
    lbNext.disabled = lbIndex >= lbList.length - 1;
  }

  function closeLightbox() {
    if (!lightbox.classList.contains("open")) return;
    lightbox.classList.remove("open");
    lightbox.setAttribute("aria-hidden", "true");
    document.body.classList.remove("lightbox-open");
    lbImage.removeAttribute("src");
    lbList = [];
    lbIndex = -1;
  }

  function stepLightbox(delta) {
    var next = lbIndex + delta;
    if (next < 0 || next >= lbList.length) return;
    lbIndex = next;
    showLightboxItem();
  }

  // -- editing -----------------------------------------------------------

  function togglePin(style) {
    // Pinning only anchors the style — it never changes its position.
    style.pinned = !style.pinned;
    refreshGroup(style.section);
    setDirty(true);
  }

  function moveBy(style, delta) {
    if (style.pinned) return;
    var list = groups.get(style.section) || [];
    var index = list.indexOf(style);
    var next = index + delta;
    // Never move into the anchored block at the top of the section.
    var floor = topPinnedCount(list);
    if (index < 0 || next < floor || next >= list.length) return;
    var temporary = list[index];
    list[index] = list[next];
    list[next] = temporary;
    refreshGroup(style.section);
    setDirty(true);
  }

  function moveToTop(style) {
    if (style.pinned) return;
    var list = groups.get(style.section) || [];
    var index = list.indexOf(style);
    if (index < 0) return;
    // Land directly below the anchored block at the top; anchors in the
    // middle of the section keep their relative order.
    var target = topPinnedCount(list);
    if (index === target) return;
    list.splice(index, 1);
    list.splice(target, 0, style);
    refreshGroup(style.section);
    setDirty(true);
  }

  function moveToBottom(style) {
    if (style.pinned) return;
    var list = groups.get(style.section) || [];
    var index = list.indexOf(style);
    if (index < 0 || index >= list.length - 1) return;
    list.splice(index, 1);
    list.push(style);
    refreshGroup(style.section);
    setDirty(true);
  }

  function handleRecategorize(style, target) {
    if (target === style.section) return;

    if (target === "__new__") {
      var raw = window.prompt("New section name:", "");
      if (raw === null) return;
      var name = raw.trim();
      if (!name) return;
      if (name.length > 60) {
        window.alert("Section names are limited to 60 characters.");
        return;
      }
      if (!groups.has(name)) {
        groups.set(name, []);
        sectionOrder.push(name);
      }
      target = name;
    }

    if (!groups.has(target)) {
      groups.set(target, []);
      sectionOrder.push(target);
    }

    var source = groups.get(style.section) || [];
    var index = source.indexOf(style);
    if (index !== -1) source.splice(index, 1);
    style.section = target;
    style._section = target.toLowerCase();
    groups.get(target).push(style);

    refreshFilter();
    render();
    setDirty(true);
  }

  // -- drag to reorder (within one section) ------------------------------

  function onDragStart(event) {
    var grip = event.target.closest(".grip");
    if (!grip) {
      event.preventDefault();
      return;
    }
    if (searchEl.value.trim()) {
      event.preventDefault();
      setStatus("Clear the search to reorder styles.", "warn");
      return;
    }
    var row = grip.closest(".row");
    if (!row || !row.parentElement) {
      event.preventDefault();
      return;
    }
    var style = byUid.get(Number(row.dataset.uid));
    if (!style || style.pinned) {
      event.preventDefault();
      setStatus("Pinned styles are anchored in place.", "warn");
      return;
    }
    drag = {
      uid: style._uid,
      section: row.parentElement.dataset.section,
      el: row
    };
    row.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    try { event.dataTransfer.setData("text/plain", row.dataset.uid); } catch (_) {}
    try { event.dataTransfer.setDragImage(row, 24, 24); } catch (_) {}
  }

  function renumberRows(rows) {
    Array.prototype.slice.call(rows.querySelectorAll(".row")).forEach(function (row, index) {
      var number = row.querySelector(".row-number");
      if (number) number.textContent = index + 1;
    });
  }

  function onDragOver(event) {
    if (!drag) return;
    var rows = event.target.closest(".rows");
    if (!rows || rows.dataset.section !== drag.section) return;

    var list = groups.get(drag.section) || [];
    var topPins = topPinnedCount(list);

    var target = event.target.closest(".row");
    if (!target) {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      rows.appendChild(drag.el);
      renumberRows(rows);
      return;
    }
    if (target === drag.el || target.parentElement !== rows) return;

    var targetStyle = byUid.get(Number(target.dataset.uid));
    if (!targetStyle) return;
    var targetIndex = list.indexOf(targetStyle);
    var rect = target.getBoundingClientRect();
    var before = event.clientY < rect.top + rect.height / 2;
    var destination = before ? targetIndex : targetIndex + 1;

    // The pinned block at the top of the section must stay on top.
    if (destination < topPins) return;

    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    rows.insertBefore(drag.el, before ? target : target.nextSibling);
    renumberRows(rows);
  }

  function onDrop(event) {
    if (!drag) return;
    var rows = event.target.closest(".rows");
    if (!rows || rows.dataset.section !== drag.section) return;
    event.preventDefault();
    commitDrag();
  }

  function onDragEnd() {
    commitDrag();
  }

  function commitDrag() {
    if (!drag) return;
    var row = drag.el;
    var section = drag.section;
    var rows = row.parentElement;
    drag = null;
    row.classList.remove("dragging");

    if (!rows || !rows.classList.contains("rows") || rows.dataset.section !== section) return;

    var ordered = Array.prototype.slice.call(rows.querySelectorAll(".row"))
      .map(function (element) { return byUid.get(Number(element.dataset.uid)); })
      .filter(Boolean);
    var previous = groups.get(section) || [];

    var changed = ordered.length !== previous.length;
    if (!changed) {
      for (var i = 0; i < ordered.length; i += 1) {
        if (ordered[i] !== previous[i]) {
          changed = true;
          break;
        }
      }
    }
    if (!changed) return;

    groups.set(section, ordered);
    refreshGroup(section);
    refreshFilter();
    setDirty(true);
  }

  // -- save / reload -----------------------------------------------------

  async function save() {
    if (saving || !dirty) return;

    var order = [];
    sectionOrder.forEach(function (section) {
      (groups.get(section) || []).forEach(function (style) {
        order.push({
          name: style.name,
          section: section,
          pinned: !!style.pinned
        });
      });
    });

    saving = true;
    saveBtn.disabled = true;
    setStatus("Saving…");

    try {
      var response = await fetch("/api/save", {
        method: "POST",
        headers: Object.assign({ "Content-Type": "application/json" }, API_HEADERS),
        body: JSON.stringify({ sections: sectionOrder, order: order })
      });
      if (!response.ok) throw new Error(await readError(response));
      var data = await response.json();
      saving = false;
      setDirty(false);
      saveBtn.disabled = true;
      var pinned = data.pinned ? " · " + data.pinned + " pinned" : "";
      var backup = data.backup ? " · backup: " + data.backup : "";
      setStatus("Saved " + data.count + " styles at " + data.saved_at + pinned + backup, "ok");
    } catch (error) {
      saving = false;
      saveBtn.disabled = !dirty;
      setStatus("Save failed: " + error.message, "error");
    }
  }

  async function reload() {
    if (dirty && !window.confirm("Discard unsaved changes and reload styles.json?")) return;
    try {
      await load();
    } catch (error) {
      setStatus("Load failed: " + error.message, "error");
    }
  }

  // -- wiring ------------------------------------------------------------

  saveBtn.addEventListener("click", save);
  reloadBtn.addEventListener("click", reload);

  lbClose.addEventListener("click", closeLightbox);
  lbPrev.addEventListener("click", function () { stepLightbox(-1); });
  lbNext.addEventListener("click", function () { stepLightbox(1); });
  lightbox.addEventListener("click", function (event) {
    if (event.target === lightbox) closeLightbox();
  });

  document.addEventListener("keydown", function (event) {
    if (lightbox.classList.contains("open")) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeLightbox();
        return;
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        stepLightbox(-1);
        return;
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        stepLightbox(1);
        return;
      }
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      save();
    }
  });

  window.addEventListener("beforeunload", function (event) {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });

  sectionsEl.addEventListener("dragstart", onDragStart);
  sectionsEl.addEventListener("dragover", onDragOver);
  sectionsEl.addEventListener("drop", onDrop);
  sectionsEl.addEventListener("dragend", onDragEnd);

  searchEl.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(render, 120);
  });
  filterEl.addEventListener("change", render);

  load().catch(function (error) {
    sectionsEl.replaceChildren();
    var box = document.createElement("div");
    box.className = "fatal";
    box.textContent = "Could not load the style library: " + error.message;
    sectionsEl.appendChild(box);
    setStatus("Load failed", "error");
  });
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Local-only visual editor for the Skutils Style Selector library.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port on 127.0.0.1 (default: 8765; use 0 for a random free port).",
    )
    parser.add_argument(
        "--library",
        default=DEFAULT_LIBRARY,
        help="styles.json to edit (default: skutils_style_selector/styles.json).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the editor in the default browser.",
    )
    args = parser.parse_args(argv)

    library_path = os.path.abspath(args.library)
    if not os.path.isfile(library_path):
        parser.error(f"styles.json not found: {library_path}")
    try:
        read_library(library_path)
    except Exception as error:  # noqa: BLE001 - fail fast with a clear message
        parser.error(f"Could not read {library_path}: {error}")

    token = secrets.token_urlsafe(32)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), EditorHandler)
    except OSError as error:
        parser.error(f"Could not bind 127.0.0.1:{args.port}: {error}. Try --port 0.")

    server.token = token
    server.library_path = library_path
    port = server.server_address[1]
    server.allowed_origins = {
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
    }

    url = f"http://127.0.0.1:{port}/?token={token}"
    print(
        "Skutils Style Editor — developer utility (not part of the plugin package)",
        flush=True,
    )
    print(f"  Library: {library_path}", flush=True)
    print(f"  Editor:  {url}", flush=True)
    print("  Saves update styles.json atomically; a timestamped backup is kept in", flush=True)
    print("  tools/backups/. Restart ComfyUI after saving to reload the picker.", flush=True)
    print("  Press Ctrl+C to stop.", flush=True)

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 - browser launch is best-effort
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
