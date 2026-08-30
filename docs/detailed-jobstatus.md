# Detailed Job Status

Shows a real-time execution timer in the ComfyUI interface — a floating, draggable widget displaying how long the current job has been **executing** (not queued) in `MM:SS` format.

## Overview

| | |
|---|---|
| **Python backend** | None — web-only feature |
| **Frontend extension** | `web/jobTimer.js` |
| **Config** | None — widget position is remembered per-browser via `localStorage` |

## How it works

The extension registers listeners for ComfyUI's WebSocket execution events (`api.addEventListener`):

| Event | Behaviour |
|---|---|
| `execution_start` | Reset the widget, record `startTime`, begin ticking every second, label **Running** (white) |
| `execution_success` | Stop ticking, freeze the elapsed time, label **Completed** (green) |
| `execution_error` | Stop ticking, label **Error** (red) |
| `execution_interrupted` | Stop ticking, label **Stopped** (orange) |

Key design decisions:

- **Timing starts at execution, not queue time.** `execution_start` fires when the prompt actually begins running, so queued-but-waiting jobs do not inflate the timer.
- **Completion is detected only via `execution_success`** (and the error/interrupt variants). The `executing{node:…}` events fire many times during a run — including for cached nodes — and are deliberately ignored as unreliable completion signals.
- **Multi-run safety.** Each event is matched against the currently tracked `prompt_id` (`isCurrentJob`), so events from a stale/previous job cannot stop or mutate the timer of the active job. The widget also resets whenever a new job starts.
- **Elapsed formatting**: `MM:SS` with seconds zero-padded (e.g. `0:07`, `12:05`); minutes are not padded.

## Widget behaviour

- **Position**: floats at bottom-right by default. Drag it anywhere with the mouse; the position is saved to `localStorage` (`djs-timer-pos`) and restored on the next page load. The widget stops all event propagation so clicks never reach the canvas underneath.
- **Visibility**: hidden when idle, shown while a job runs, and stays visible after completion/error with the final status until the next job starts.

## Installation

The feature ships as part of the unified `ComfyUI-skkut-utils` repo — see the [root README](../README.md). It has no dependencies and no configuration; restart ComfyUI after installing.

## Files

- `web/jobTimer.js` — the entire feature (extension name `DetailedJobStatus.ExecutionTimer`).
- `detailed_jobstatus/__init__.py` — empty placeholder subpackage; the feature is frontend-only.
