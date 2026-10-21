"""HTTP endpoints for the Skutils Style Selector's picker.

  GET  /skutils_style_selector/library  — bundled + custom styles
  GET  /skutils_style_selector/thumb    — a bundled thumbnail, by style name
  POST /skutils_style_selector/custom   — save/delete a custom style

The thumbnail route never accepts a path: it looks the style up by name and
only then resolves the stored filename, containment-checked against the
bundled thumbnails directory.
"""

from __future__ import annotations

import logging

from aiohttp import web
from server import PromptServer

from .library import (
    bundled_thumb_path,
    delete_custom,
    merged_library,
    save_custom,
)

LOGGER = logging.getLogger("skutils-utils.skutils_style_selector")

routes = PromptServer.instance.routes


@routes.get("/skutils_style_selector/library")
async def library_endpoint(request):
    return web.json_response(
        merged_library(),
        headers={"Cache-Control": "no-store"},
    )


@routes.get("/skutils_style_selector/thumb")
async def thumb_endpoint(request):
    name = request.query.get("name", "")
    path = bundled_thumb_path(name) if name else None
    if not path:
        raise web.HTTPNotFound()
    return web.FileResponse(
        path,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@routes.post("/skutils_style_selector/custom")
async def custom_endpoint(request):
    try:
        body = await request.json()
    except ValueError:
        return _error("Invalid JSON body.")
    if not isinstance(body, dict):
        return _error("Invalid JSON body.")

    action = body.get("action")
    try:
        if action == "save":
            style = body.get("style")
            if not isinstance(style, dict):
                return _error("A style object is required.")
            original_name = body.get("original_name")
            if original_name is not None and not isinstance(original_name, str):
                return _error("original_name must be a string.")
            save_custom(style, original_name)
        elif action == "delete":
            style = body.get("style") if isinstance(body.get("style"), dict) else {}
            name = body.get("name") or style.get("name")
            if not isinstance(name, str) or not name.strip():
                return _error("A style name is required.")
            if not delete_custom(name.strip()):
                return _error(f"'{name.strip()}' is not a custom style.", status=404)
        else:
            return _error("action must be 'save' or 'delete'.")
    except ValueError as error:
        return _error(str(error))
    except RuntimeError as error:
        LOGGER.exception("Could not write custom styles")
        return _error(str(error), status=500)
    except OSError as error:
        LOGGER.exception("Could not write custom styles")
        return _error(f"Could not write custom styles: {error}", status=500)

    return web.json_response(
        {"status": "ok", "library": merged_library()},
        headers={"Cache-Control": "no-store"},
    )


def _error(message, status=400):
    return web.json_response(
        {"status": "error", "message": message},
        status=status,
        headers={"Cache-Control": "no-store"},
    )
