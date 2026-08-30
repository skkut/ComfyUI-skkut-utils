"""
Detailed Job Status — feature subpackage of ComfyUI-skkut-utils.

Web-only feature: there is no Python backend.  The frontend extension in
web/jobTimer.js displays a floating, draggable execution timer (MM:SS) in
the ComfyUI status bar area, starting from when a job actually begins
executing (not when it was queued).  It is loaded automatically by ComfyUI
from the root WEB_DIRECTORY (`./web`).

All state and event handling lives in the browser; nothing is registered
here.
"""
