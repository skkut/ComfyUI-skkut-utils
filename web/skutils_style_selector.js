import { app } from "../../scripts/app.js";

/*
 * Skutils Style Selector — visual picker.
 *
 * The node's `select_styles` widget stays the single source of truth (a JSON
 * array of names), which is what the workflow JSON serializes.  This file
 * hides that raw widget and replaces it with:
 *
 *   - a compact chip list + "Choose styles" button on the node body;
 *   - a full-screen picker (search, section filter, ordered multi-select);
 *   - an editor for custom styles, stored by the Python side under
 *     ComfyUI's user directory.
 */

const NODE_CLASS = "SkutilsStyleSelector";
const LIBRARY_URL = "/skutils_style_selector/library";
const THUMB_URL = "/skutils_style_selector/thumb";
// The server fingerprints the bundled thumbnails (`thumb_version` in the
// library payload) and we append that to every thumbnail URL, so replacing an
// image busts the browser's 24-hour image cache without a hard refresh.
// `entry.thumb` covers the gap before the library payload has arrived.
const THUMB_VERSION_FALLBACK = "1";
const DEFAULT_TEMPLATE = "Style: {name}: {style}. Subject: {prompt}";
const CUSTOM_URL = "/skutils_style_selector/custom";
const CSS_ID = "skutils-style-selector-css";

let library = null;          // last successfully fetched library payload
let libraryPromise = null;   // in-flight fetch
let modal = null;            // lazily built picker DOM

const current = {
    node: null,
    selected: [],
    entries: new Map(),
    searchText: new Map(),
};

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
        if (value == null || value === false) continue;
        if (key === "class") node.className = value;
        else if (key === "text") node.textContent = value;
        else if (key === "html") node.innerHTML = value;
        else if (key.startsWith("on") && typeof value === "function") {
            node.addEventListener(key.slice(2), value);
        } else if (value === true) {
            node.setAttribute(key, "");
        } else {
            node.setAttribute(key, String(value));
        }
    }
    for (const child of children) {
        if (child == null) continue;
        node.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return node;
}

function initials(name) {
    const words = String(name).split(/[\s\-_/]+/).filter(Boolean);
    if (!words.length) return "?";
    const letters = words.slice(0, 2).map((word) => word[0].toUpperCase());
    return letters.join("");
}

function hue(text) {
    let value = 0;
    for (const char of String(text)) {
        value = (value * 31 + char.charCodeAt(0)) % 360;
    }
    return value;
}

function entryByName(name) {
    return current.entries.get(name) || null;
}

function thumbUrl(entry) {
    if (!entry) return null;
    if (entry.source === "custom") return entry.thumbnail || null;
    if (!entry.thumb) return null;
    const version = library?.thumb_version || entry.thumb || THUMB_VERSION_FALLBACK;
    return `${THUMB_URL}?name=${encodeURIComponent(entry.name)}&v=${encodeURIComponent(version)}`;
}

function fallbackThumb(entry, name, className) {
    return el("div", {
        class: className,
        style: `background: hsl(${hue(entry?.section || name)} 42% 32%);`,
        text: initials(entry?.name || name),
    });
}

// Fill a thumbnail box so it is never empty: the initials placeholder is
// rendered first and the image overlays it once loaded.  A missing URL or a
// failed load (e.g. the backend has not been restarted yet) simply leaves the
// placeholder visible instead of a blank box or broken-image icon.
function appendThumb(container, entry, name, fallbackClass) {
    container.append(fallbackThumb(entry, name, fallbackClass));
    const url = thumbUrl(entry);
    if (!url) return;
    const img = el("img", { src: url, alt: "", loading: "lazy", decoding: "async", draggable: "false" });
    img.addEventListener("error", () => img.remove(), { once: true });
    container.append(img);
}

function tooltip(entry) {
    const prose = String(entry.prompt || "").replaceAll("{prompt}", "…");
    const parts = [entry.name];
    if (entry.section) parts.push(entry.section);
    if (prose) parts.push(prose);
    if (entry.negative) parts.push(`Negative: ${entry.negative}`);
    return parts.join("\n\n").slice(0, 1200);
}

function readSelection(node) {
    const widget = node?.__skutilsStyle?.selectWidget;
    const raw = widget?.value ?? "[]";
    try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
            return parsed
                .map((item) => (typeof item === "string" ? item : item?.name))
                .filter((item) => typeof item === "string" && item.trim())
                .map((item) => item.trim());
        }
    } catch {
        // fall through to the comma-separated form
    }
    const text = String(raw ?? "").trim();
    return text ? text.split(",").map((part) => part.trim()).filter(Boolean) : [];
}

function writeSelection(node, names) {
    const widget = node?.__skutilsStyle?.selectWidget;
    if (!widget) return;
    widget.value = JSON.stringify(names);
    widget.callback?.(widget.value);
    node.setDirtyCanvas?.(true, true);
    renderNodeBody(node);
}

// ---------------------------------------------------------------------------
// Node body
// ---------------------------------------------------------------------------

function renderNodeBody(node) {
    const state = node.__skutilsStyle;
    if (!state) return;

    const names = readSelection(node);
    state.chips.replaceChildren();

    if (!names.length) {
        state.chips.append(el("span", { class: "skutils-node-empty", text: "No style selected" }));
    } else {
        names.forEach((name, index) => {
            const entry = entryByName(name);
            // Before the library has loaded, an unknown name is not "missing"
            // yet — wait for the fetch so cards do not flash a warning outline.
            const missing = Boolean(library) && !entry;
            const chip = el("div", {
                class: `skutils-node-chip${missing ? " missing" : ""}`,
                title: entry ? tooltip(entry) : `${name} (not found in the library)`,
            });
            const thumb = el("div", { class: "skutils-node-thumb" });
            appendThumb(thumb, entry, name, "skutils-node-fallback");
            thumb.append(el("span", { class: "skutils-node-order", text: String(index + 1) }));
            chip.append(thumb, el("span", { class: "skutils-node-name", text: name }));
            state.chips.append(chip);
        });
    }

    state.button.textContent = names.length
        ? `Edit styles (${names.length})`
        : "Choose styles…";
}

function refreshNodeBody(node) {
    // The picker normally builds the entry index, but a workflow can restore a
    // selection and render the node body before the picker was ever opened.
    // Index here too, so thumbnails resolve without the picker.
    if (library && !current.entries.size) indexLibrary();
    renderNodeBody(node);
    // A workflow load can set a selection before the library was ever fetched;
    // render the names immediately, then re-render once entries are known.
    if (readSelection(node).length && !library) {
        ensureLibrary()
            .then(() => {
                indexLibrary();
                renderNodeBody(node);
            })
            .catch(() => {});
    }
}

function hideRawWidget(widget) {
    widget.computeSize = () => [0, -4];
    widget.draw = () => {};
    if (widget.inputEl) widget.inputEl.style.display = "none";
    if (widget.element) widget.element.style.display = "none";
}

// Older test workflows saved this node while `positive` and `negative` were
// still widgets, so `widgets_values` has six entries:
//   [positive, negative, select_styles, batch_mode, template, separator]
// They are optional input sockets now, leaving three widgets.  The frontend's
// generic migration does not reorder that shape, so re-map it here before the
// saved values are read back.
function migrateLegacyValues(node, info) {
    const values = info?.widgets_values;
    if (!Array.isArray(values) || values.length !== 6) return;
    if (
        typeof values[0] !== "string" || typeof values[1] !== "string" ||
        typeof values[2] !== "string" || typeof values[3] !== "boolean"
    ) {
        return;
    }

    const widget = (name) => node.widgets?.find((entry) => entry.name === name);
    const selectWidget = widget("select_styles");
    const batchWidget = widget("batch_mode");
    const templateWidget = widget("template");

    if (selectWidget) selectWidget.value = values[2];
    if (batchWidget) batchWidget.value = values[3];
    if (templateWidget && typeof values[4] === "string") templateWidget.value = values[4];

    // Save the node in the current three-value shape next time.
    node.widgets_values = [
        selectWidget?.value ?? values[2],
        batchWidget?.value ?? values[3],
        templateWidget?.value ?? values[4],
    ];
}

function looksLikeSelectionArray(value) {
    if (typeof value !== "string") return false;
    try {
        return Array.isArray(JSON.parse(value));
    } catch {
        return false;
    }
}

// A node that was already loaded (and re-saved) while the values were shifted
// keeps the corruption in widgets_values_named:
//   select_styles="[]", batch_mode="", template='["Ghibli Style"]', separator=false
// `batch_mode` is always a boolean when correct, so a non-boolean value is the
// reliable marker.  The old select_styles JSON sits in `template`, and the old
// batch_mode boolean is still in the raw saved values.  A custom template was
// overwritten by the shift and is unrecoverable, so it falls back to the default.
function repairShiftedValues(node, info) {
    const widget = (name) => node.widgets?.find((entry) => entry.name === name);
    const selectWidget = widget("select_styles");
    const batchWidget = widget("batch_mode");
    const templateWidget = widget("template");
    if (!batchWidget || typeof batchWidget.value === "boolean") return false;

    const saved = info?.widgets_values;
    const named = info?.widgets_values_named;
    let oldBatch = false;
    if (typeof named?.style_separator === "boolean") {
        oldBatch = named.style_separator;
    } else if (Array.isArray(saved) && saved.length === 4 && typeof saved[3] === "boolean") {
        oldBatch = saved[3];
    }

    if (selectWidget && looksLikeSelectionArray(templateWidget?.value)) {
        selectWidget.value = templateWidget.value;
    }
    batchWidget.value = oldBatch;
    if (templateWidget) templateWidget.value = DEFAULT_TEMPLATE;

    node.widgets_values = [
        selectWidget?.value ?? "[]",
        batchWidget.value,
        templateWidget?.value ?? DEFAULT_TEMPLATE,
    ];
    return true;
}

function setupNode(node) {
    if (node.__skutilsStyle) return;
    if (typeof node.addDOMWidget !== "function") return;

    // Inject the styles before the body renders.  ensureModal() does this too,
    // but the node body must already be styled on a cold load, before the
    // picker is ever opened — otherwise a restored thumbnail shows at its
    // natural 512px size.
    ensureCss();

    const selectWidget = node.widgets?.find((widget) => widget.name === "select_styles");
    if (!selectWidget) return;

    node.__skutilsStyle = { selectWidget, chips: null, button: null };

    hideRawWidget(selectWidget);

    const chips = el("div", { class: "skutils-node-chips" });
    const button = el("button", {
        class: "skutils-node-button",
        type: "button",
        text: "Choose styles…",
        onclick: () => openPicker(node),
    });
    const container = el(
        "div",
        { class: "skutils-node" },
        chips,
        el("div", { class: "skutils-node-actions" }, button),
    );

    node.__skutilsStyle.chips = chips;
    node.__skutilsStyle.button = button;

    const domWidget = node.addDOMWidget("style_selector_ui", "custom", container, {
        serialize: false,
        hideOnZoom: false,
        getValue: () => selectWidget.value,
        setValue: (value) => {
            selectWidget.value = value;
        },
    });
    domWidget.serialize = false;
    if (domWidget.options) domWidget.options.serialize = false;

    const originalConfigure = node.onConfigure;
    node.onConfigure = function (info) {
        const result = originalConfigure?.apply(this, arguments);
        migrateLegacyValues(node, info);
        repairShiftedValues(node, info);
        // The widget values are applied during configure; render after.
        setTimeout(() => refreshNodeBody(node), 0);
        return result;
    };

    const originalRemoved = node.onRemoved;
    node.onRemoved = function () {
        if (current.node === node) closePicker();
        return originalRemoved?.apply(this, arguments);
    };

    refreshNodeBody(node);
    node.setSize([Math.max(node.size?.[0] ?? 0, 340), Math.max(node.size?.[1] ?? 0, 230)]);
}

// ---------------------------------------------------------------------------
// Library fetch
// ---------------------------------------------------------------------------

async function fetchLibrary() {
    const response = await fetch(LIBRARY_URL, { cache: "no-store" });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    if (!data || !Array.isArray(data.styles)) {
        throw new Error("Unexpected library response");
    }
    return data;
}

async function ensureLibrary() {
    if (library) return library;
    if (!libraryPromise) {
        libraryPromise = fetchLibrary()
            .then((data) => {
                library = data;
                return data;
            })
            .finally(() => {
                libraryPromise = null;
            });
    }
    return libraryPromise;
}

async function postCustom(body) {
    const response = await fetch(CUSTOM_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    let data = null;
    try {
        data = await response.json();
    } catch {
        // keep null; the status check below covers it
    }
    if (!response.ok || data?.status === "error") {
        throw new Error(data?.message || `HTTP ${response.status}`);
    }
    return data;
}

// ---------------------------------------------------------------------------
// Modal construction
// ---------------------------------------------------------------------------

function ensureCss() {
    if (document.getElementById(CSS_ID)) return;
    const style = document.createElement("style");
    style.id = CSS_ID;
    style.textContent = `
.skutils-node { display: flex; flex-direction: column; gap: 4px; width: 100%; box-sizing: border-box; padding: 0; font-size: 11px; }
.skutils-node-chips { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 8px; max-height: 300px; overflow-y: auto; }
/* Same 124x112 thumbnail as the picker strip: 124px content + 4px padding a side. */
.skutils-node-chip { position: relative; display: flex; flex-direction: column; align-items: stretch; gap: 3px; box-sizing: border-box; width: 132px; padding: 4px; border-radius: 8px; background: rgba(127,127,127,.18); max-width: 100%; }
.skutils-node-thumb { position: relative; width: 100%; height: 112px; flex: 0 0 auto; border-radius: 5px; overflow: hidden; background: #111; }
.skutils-node-thumb img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
.skutils-node-fallback { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 26px; font-weight: 700; letter-spacing: 1px; }
.skutils-node-order { position: absolute; top: 3px; left: 3px; display: inline-flex; align-items: center; justify-content: center; min-width: 18px; height: 18px; padding: 0 4px; border-radius: 9px; background: var(--p-primary-color, #3b82f6); color: #fff; font-size: 10px; font-weight: 700; box-shadow: 0 1px 4px rgba(0,0,0,.5); }
.skutils-node-name { width: 100%; text-align: center; font-size: 10px; line-height: 1.2; min-height: 2.4em; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.skutils-node-chip.missing { outline: 1px dashed rgba(224,168,0,.7); }
.skutils-node-empty { opacity: .6; }
.skutils-node-actions { display: flex; align-items: center; }
.skutils-node-button { padding: 2px 8px; border-radius: 4px; border: 1px solid var(--border-color, #444); background: var(--comfy-input-bg, #222); color: var(--fg-color, #eee); cursor: pointer; font-size: 10px; line-height: 1.4; }
.skutils-node-button:hover { border-color: var(--p-primary-color, #3b82f6); }

.skutils-overlay { position: fixed; inset: 0; z-index: 10000; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,.6); }
.skutils-dialog { position: relative; width: min(1120px, 94vw); height: min(840px, 92vh); display: flex; flex-direction: column; overflow: hidden; border-radius: 12px; border: 1px solid var(--border-color, #3a3a3a); background: var(--comfy-menu-bg, #202020); color: var(--fg-color, #eee); box-shadow: 0 24px 80px rgba(0,0,0,.55); }
.skutils-header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 12px 14px; border-bottom: 1px solid var(--border-color, #3a3a3a); }
.skutils-title { margin: 0; font-size: 16px; font-weight: 600; white-space: nowrap; }
.skutils-title small { font-weight: 400; opacity: .6; font-size: 12px; margin-left: 6px; }
.skutils-search { flex: 1 1 220px; min-width: 160px; padding: 6px 10px; border-radius: 6px; border: 1px solid var(--border-color, #444); background: var(--comfy-input-bg, #171717); color: var(--fg-color, #eee); font-size: 13px; }
.skutils-select { flex: 0 1 190px; padding: 6px 8px; border-radius: 6px; border: 1px solid var(--border-color, #444); background: var(--comfy-input-bg, #171717); color: var(--fg-color, #eee); font-size: 13px; }
.skutils-btn { padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border-color, #444); background: var(--comfy-input-bg, #222); color: var(--fg-color, #eee); cursor: pointer; font-size: 13px; white-space: nowrap; }
.skutils-btn:hover:not(:disabled) { border-color: var(--p-primary-color, #3b82f6); }
.skutils-btn:disabled { opacity: .5; cursor: default; }
.skutils-btn.primary { background: var(--p-primary-color, #3b82f6); border-color: transparent; color: #fff; }
.skutils-btn.danger { border-color: rgba(220,80,80,.6); color: #ff9b9b; }
.skutils-strip { display: flex; align-items: center; gap: 10px; min-height: 64px; padding: 10px 14px; overflow-x: auto; border-bottom: 1px solid var(--border-color, #3a3a3a); }
.skutils-strip-empty { align-self: center; font-size: 12px; opacity: .6; }
.skutils-chip { display: flex; flex-direction: column; align-items: stretch; gap: 5px; flex: 0 0 auto; width: 124px; padding: 6px; border-radius: 10px; border: 1px solid var(--border-color, #3a3a3a); background: var(--comfy-input-bg, #1b1b1b); font-size: 12px; cursor: grab; }
.skutils-chip.dragging { opacity: .45; }
.skutils-chip.missing { border-color: rgba(224,168,0,.8); }
.skutils-chip-thumb { position: relative; width: 100%; height: 112px; flex: 0 0 auto; border-radius: 6px; overflow: hidden; background: #111; display: flex; align-items: center; justify-content: center; }
.skutils-chip-thumb img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
.skutils-chip-fallback { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 28px; font-weight: 700; letter-spacing: 1px; }
.skutils-chip-order { position: absolute; top: 4px; left: 4px; display: inline-flex; align-items: center; justify-content: center; min-width: 20px; height: 20px; border-radius: 10px; background: var(--p-primary-color, #3b82f6); color: #fff; font-size: 11px; font-weight: 700; padding: 0 5px; box-shadow: 0 1px 4px rgba(0,0,0,.5); }
.skutils-chip-body { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.skutils-chip-name { font-size: 12px; line-height: 1.25; text-align: center; min-height: 2.5em; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.skutils-chip-actions { display: flex; align-items: center; justify-content: center; gap: 3px; }
.skutils-chip-btn { width: 24px; height: 20px; border: none; border-radius: 4px; background: rgba(127,127,127,.16); color: inherit; cursor: pointer; padding: 0; font-size: 13px; line-height: 1; opacity: .75; }
.skutils-chip-btn:hover:not(:disabled) { opacity: 1; }
.skutils-chip-btn:disabled { opacity: .2; cursor: default; }
/* Fixed tracks + explicit image height: aspect-ratio/minmax sizing cycles
   collapse inside ComfyUI's global CSS, and a wrapping name would otherwise
   shrink the flex image box.  Every thumbnail is therefore exactly 136px high. */
.skutils-grid { flex: 1; display: grid; grid-template-columns: repeat(auto-fill, 150px); grid-auto-rows: max-content; justify-content: center; gap: 10px; align-content: start; padding: 12px 14px; overflow-y: auto; }
.skutils-grid-empty { grid-column: 1 / -1; padding: 30px; text-align: center; opacity: .6; font-size: 13px; }
.skutils-tile { position: relative; display: flex; flex-direction: column; gap: 4px; box-sizing: border-box; padding: 6px; border-radius: 8px; border: 1px solid var(--border-color, #3a3a3a); background: var(--comfy-input-bg, #1b1b1b); color: inherit; cursor: pointer; text-align: left; overflow: hidden; font: inherit; }
.skutils-tile:hover { border-color: var(--p-primary-color, #3b82f6); }
.skutils-tile.selected { border-color: var(--p-primary-color, #3b82f6); box-shadow: 0 0 0 2px rgba(59,130,246,.35); }
.skutils-tile-img { position: relative; width: 100%; height: 136px; flex: 0 0 auto; border-radius: 5px; overflow: hidden; background: #111; display: flex; align-items: center; justify-content: center; }
.skutils-tile-img img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
.skutils-fallback { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 26px; font-weight: 700; letter-spacing: 1px; }
.skutils-tile-name { font-size: 12px; line-height: 1.25; min-height: 2.5em; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.skutils-tile-section { font-size: 10px; line-height: 1.2; min-height: 1.2em; opacity: .6; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.skutils-tile-order { position: absolute; top: 6px; left: 6px; display: none; align-items: center; justify-content: center; min-width: 22px; height: 22px; padding: 0 6px; border-radius: 11px; background: var(--p-primary-color, #3b82f6); color: #fff; font-size: 11px; font-weight: 700; }
.skutils-tile-edit { position: absolute; top: 6px; right: 6px; width: 24px; height: 24px; border-radius: 6px; border: none; background: rgba(0,0,0,.68); color: #fff; cursor: pointer; opacity: 0; transition: opacity .15s; }
.skutils-tile:hover .skutils-tile-edit, .skutils-tile-edit:focus { opacity: 1; }
.skutils-footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 14px; border-top: 1px solid var(--border-color, #3a3a3a); }
.skutils-footer-left { display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
.skutils-footer-hint { opacity: .6; }
.skutils-footer-actions { display: flex; gap: 8px; }
.skutils-status { font-size: 12px; opacity: .75; }
.skutils-editor { position: absolute; inset: 0; z-index: 2; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,.5); }
.skutils-editor-panel { width: min(700px, 94%); max-height: 90%; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; padding: 16px; border-radius: 10px; border: 1px solid var(--border-color, #3a3a3a); background: var(--comfy-menu-bg, #202020); box-shadow: 0 20px 60px rgba(0,0,0,.5); }
.skutils-editor-title { margin: 0; font-size: 15px; font-weight: 600; }
.skutils-field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.skutils-field span { opacity: .8; }
.skutils-field input, .skutils-field textarea { padding: 6px 8px; border-radius: 6px; border: 1px solid var(--border-color, #444); background: var(--comfy-input-bg, #171717); color: var(--fg-color, #eee); font-size: 13px; font-family: inherit; }
.skutils-field textarea { resize: vertical; min-height: 84px; }
.skutils-field input[type="url"] { font-family: monospace; font-size: 12px; }
.skutils-editor-error { min-height: 16px; font-size: 12px; color: #ff8a8a; }
.skutils-editor-actions { display: flex; align-items: center; gap: 8px; }
.skutils-editor-actions .spacer { flex: 1; }
`;
    document.head.append(style);
}

function ensureModal() {
    if (modal) return modal;

    ensureCss();

    const search = el("input", {
        class: "skutils-search",
        type: "search",
        placeholder: "Search styles…",
        "aria-label": "Search styles",
    });
    const sectionSelect = el("select", { class: "skutils-select", "aria-label": "Filter by section" });
    const status = el("span", { class: "skutils-status" });
    const strip = el("div", { class: "skutils-strip" });
    const grid = el("div", { class: "skutils-grid" });
    const count = el("span", {});
    const hint = el("span", { class: "skutils-footer-hint" });
    const clearButton = el("button", { class: "skutils-btn", type: "button", text: "Clear" });
    const applyButton = el("button", { class: "skutils-btn primary", type: "button", text: "Apply" });
    const closeButton = el("button", { class: "skutils-btn", type: "button", text: "×", title: "Close (Esc)" });
    const newButton = el("button", { class: "skutils-btn", type: "button", text: "＋ New style" });

    const header = el(
        "div",
        { class: "skutils-header" },
        el(
            "h2",
            {
                class: "skutils-title",
                title: "Style descriptions: u/Dear-Spend-2865 / Clio Style Library; OreX style sets.",
            },
            "Skutils Style Selector",
            el("small", { text: "434 styles" }),
        ),
        search,
        sectionSelect,
        status,
        newButton,
        closeButton,
    );

    const footer = el(
        "div",
        { class: "skutils-footer" },
        el("div", { class: "skutils-footer-left" }, count, hint),
        el("div", { class: "skutils-footer-actions" }, clearButton, applyButton),
    );

    const dialog = el(
        "div",
        { class: "skutils-dialog", role: "dialog", "aria-label": "Choose styles" },
        header,
        strip,
        grid,
        footer,
        buildEditor(),
    );

    const overlay = el(
        "div",
        {
            class: "skutils-overlay",
            style: "display: none;",
            onmousedown: (event) => {
                if (event.target === overlay) closePicker();
            },
        },
        dialog,
    );

    document.body.append(overlay);

    modal = {
        overlay,
        dialog,
        search,
        sectionSelect,
        status,
        strip,
        grid,
        count,
        hint,
        clearButton,
        applyButton,
        closeButton,
        newButton,
        tiles: new Map(),
        visible: 0,
        editor: null,
    };

    search.addEventListener("input", () => {
        applyFilters();
        updateFooter();
    });
    sectionSelect.addEventListener("change", () => {
        applyFilters();
        updateFooter();
    });
    newButton.addEventListener("click", () => openEditor(null));
    closeButton.addEventListener("click", () => closePicker());
    clearButton.addEventListener("click", () => {
        current.selected = [];
        renderStrip();
        syncTiles();
        updateFooter();
    });
    applyButton.addEventListener("click", () => applySelection());

    document.addEventListener("keydown", onModalKeyDown, true);

    return modal;
}

// ---------------------------------------------------------------------------
// Editor
// ---------------------------------------------------------------------------

function buildEditor() {
    const title = el("h3", { class: "skutils-editor-title", text: "New custom style" });
    const nameInput = el("input", { type: "text", maxlength: "120", placeholder: "My style" });
    const sectionInput = el("input", { type: "text", maxlength: "60", placeholder: "Custom", list: "skutils-style-sections" });
    const datalist = el("datalist", { id: "skutils-style-sections" });
    const promptInput = el("textarea", { placeholder: "Style description, e.g. “A soft watercolor illustration of {prompt}…”" });
    const negativeInput = el("textarea", { placeholder: "Optional negative additions for this style" });
    const templateInput = el("textarea", { placeholder: "Optional. Leave empty to use the node's wrap template." });
    const thumbnailInput = el("input", { type: "url", placeholder: "https://… (optional)" });
    const error = el("div", { class: "skutils-editor-error" });
    const saveButton = el("button", { class: "skutils-btn primary", type: "button", text: "Save" });
    const deleteButton = el("button", { class: "skutils-btn danger", type: "button", text: "Delete", style: "display: none;" });
    const cancelButton = el("button", { class: "skutils-btn", type: "button", text: "Cancel" });

    const overlay = el(
        "div",
        {
            class: "skutils-editor",
            style: "display: none;",
            onmousedown: (event) => {
                if (event.target === overlay) closeEditor();
            },
        },
        el(
            "div",
            { class: "skutils-editor-panel" },
            title,
            el("label", { class: "skutils-field" }, el("span", { text: "Name" }), nameInput),
            el("label", { class: "skutils-field" }, el("span", { text: "Section" }), sectionInput, datalist),
            el("label", { class: "skutils-field" }, el("span", { text: "Prompt" }), promptInput),
            el("label", { class: "skutils-field" }, el("span", { text: "Negative additions (optional)" }), negativeInput),
            el("label", { class: "skutils-field" }, el("span", { text: "Template (advanced, optional)" }), templateInput),
            el("label", { class: "skutils-field" }, el("span", { text: "Thumbnail URL (optional)" }), thumbnailInput),
            error,
            el(
                "div",
                { class: "skutils-editor-actions" },
                saveButton,
                cancelButton,
                el("span", { class: "spacer" }),
                deleteButton,
            ),
        ),
    );

    saveButton.addEventListener("click", saveEditor);
    deleteButton.addEventListener("click", deleteEditor);
    cancelButton.addEventListener("click", closeEditor);

    return overlay;
}

let editorState = null;

function openEditor(entry) {
    if (!modal) return;
    const isNew = !entry;
    const isCustom = !isNew && entry.source === "custom";
    const clone = !isNew && !isCustom;

    const source = entry || {
        name: "",
        section: "Custom",
        prompt: "",
        negative: "",
        template: null,
        thumbnail: "",
    };

    editorState = {
        originalName: isCustom ? entry.name : null,
    };
    const editor = getEditorRefs();
    editor.title.textContent = isNew
        ? "New custom style"
        : isCustom
            ? `Edit “${entry.name}”`
            : `Clone “${entry.name}”`;
    editor.nameInput.value = clone ? `${entry.name} (custom)` : source.name || "";
    editor.sectionInput.value = source.section || "Custom";
    editor.promptInput.value = source.prompt || "";
    editor.negativeInput.value = source.negative || "";
    editor.templateInput.value = source.template || "";
    editor.thumbnailInput.value = isCustom ? entry.thumbnail || "" : "";
    editor.error.textContent = "";
    editor.deleteButton.style.display = isCustom ? "" : "none";
    editor.overlay.style.display = "flex";
    setTimeout(() => editor.nameInput.focus(), 0);
}

let editorRefs = null;

function getEditorRefs() {
    if (editorRefs) return editorRefs;
    const overlay = modal.dialog.querySelector(".skutils-editor");
    editorRefs = {
        overlay,
        title: overlay.querySelector(".skutils-editor-title"),
        nameInput: overlay.querySelectorAll("input")[0],
        sectionInput: overlay.querySelectorAll("input")[1],
        datalist: overlay.querySelector("datalist"),
        promptInput: overlay.querySelectorAll("textarea")[0],
        negativeInput: overlay.querySelectorAll("textarea")[1],
        templateInput: overlay.querySelectorAll("textarea")[2],
        thumbnailInput: overlay.querySelector('input[type="url"]'),
        error: overlay.querySelector(".skutils-editor-error"),
        saveButton: overlay.querySelector(".skutils-btn.primary"),
        deleteButton: overlay.querySelector(".skutils-btn.danger"),
    };
    return editorRefs;
}

function closeEditor() {
    if (!modal) return;
    const editor = getEditorRefs();
    if (editor) editor.overlay.style.display = "none";
    editorState = null;
}

async function saveEditor() {
    const editor = getEditorRefs();
    const style = {
        name: editor.nameInput.value.trim(),
        section: editor.sectionInput.value.trim() || "Custom",
        prompt: editor.promptInput.value,
        negative: editor.negativeInput.value,
        template: editor.templateInput.value.trim() ? editor.templateInput.value : null,
        thumbnail: editor.thumbnailInput.value.trim(),
    };
    if (!style.name) {
        editor.error.textContent = "A style needs a name.";
        return;
    }
    if (!style.prompt.trim()) {
        editor.error.textContent = "A style needs a prompt.";
        return;
    }

    const originalName = editorState?.originalName ?? null;
    editor.saveButton.disabled = true;
    editor.error.textContent = "";
    try {
        const result = await postCustom({
            action: "save",
            style,
            original_name: originalName,
        });
        library = result.library;
        if (originalName && originalName !== style.name) {
            current.selected = current.selected.map((name) =>
                name === originalName ? style.name : name,
            );
        }
        closeEditor();
        rebuildFromLibrary();
    } catch (error) {
        editor.error.textContent = error.message;
    } finally {
        editor.saveButton.disabled = false;
    }
}

async function deleteEditor() {
    const editor = getEditorRefs();
    const name = editorState?.originalName;
    if (!name) return;
    if (!window.confirm(`Delete the custom style “${name}”?`)) return;

    editor.deleteButton.disabled = true;
    editor.error.textContent = "";
    try {
        const result = await postCustom({ action: "delete", name });
        library = result.library;
        current.selected = current.selected.filter((selected) => selected !== name);
        closeEditor();
        rebuildFromLibrary();
    } catch (error) {
        editor.error.textContent = error.message;
    } finally {
        editor.deleteButton.disabled = false;
    }
}

// ---------------------------------------------------------------------------
// Picker lifecycle
// ---------------------------------------------------------------------------

function onModalKeyDown(event) {
    if (event.key !== "Escape" || !modal || modal.overlay.style.display === "none") return;
    const editor = getEditorRefs();
    if (editor && editor.overlay.style.display !== "none") {
        event.stopPropagation();
        closeEditor();
    } else {
        event.stopPropagation();
        closePicker();
    }
}

async function openPicker(node) {
    const owner = ensureModal();
    current.node = node;
    current.selected = readSelection(node);
    owner.overlay.style.display = "flex";
    owner.status.textContent = "Loading styles…";
    closeEditor();

    // Paint the saved selection immediately.  On a cold start the library is
    // not known yet, so each card shows its initials placeholder until the
    // fetch completes and renderStrip() runs again with real thumbnails.
    renderStrip();

    let notice = "";
    try {
        library = await fetchLibrary();
    } catch (error) {
        if (!library) {
            owner.status.textContent = `Could not load styles: ${error.message}`;
            return;
        }
        notice = `Using cached styles (${error.message})`;
    }

    rebuildFromLibrary();
    if (notice) owner.status.textContent = notice;
    owner.search.focus();
}

function closePicker() {
    if (!modal) return;
    modal.overlay.style.display = "none";
    closeEditor();
    current.node = null;
}

function applySelection() {
    const node = current.node;
    if (node) writeSelection(node, current.selected.slice());
    closePicker();
}

// Build the name -> entry lookup used by both the node body and the picker.
function indexLibrary() {
    current.entries = new Map();
    current.searchText = new Map();
    for (const entry of library.styles) {
        current.entries.set(entry.name, entry);
        current.searchText.set(
            entry.name,
            `${entry.name} ${entry.section || ""} ${entry.prompt || ""} ${entry.negative || ""}`
                .toLowerCase(),
        );
    }
}

function rebuildFromLibrary() {
    indexLibrary();

    modal.overlay.querySelector(".skutils-title small").textContent =
        `${library.styles.length} styles`;

    fillSections();
    buildGrid();
    renderStrip();
    applyFilters();
    updateFooter();
    modal.status.textContent = "";
}

function fillSections() {
    const counts = new Map();
    for (const entry of library.styles) {
        counts.set(entry.section, (counts.get(entry.section) || 0) + 1);
    }

    const previous = modal.sectionSelect.value;
    modal.sectionSelect.replaceChildren(
        el("option", { value: "", text: `All sections (${library.styles.length})` }),
    );
    for (const section of library.sections) {
        if (!counts.get(section)) continue;
        modal.sectionSelect.append(
            el("option", { value: section, text: `${section} (${counts.get(section)})` }),
        );
    }
    if ([...modal.sectionSelect.options].some((option) => option.value === previous)) {
        modal.sectionSelect.value = previous;
    }

    const datalist = getEditorRefs().datalist;
    datalist.replaceChildren(
        ...library.sections.map((section) => el("option", { value: section })),
    );
}

function buildGrid() {
    modal.tiles.clear();
    modal.grid.replaceChildren();

    const fragment = document.createDocumentFragment();
    for (const entry of library.styles) {
        // A div (not a button) so the per-tile edit button is not nested
        // inside another interactive element.
        const tile = el("div", {
            class: "skutils-tile",
            role: "button",
            tabindex: "0",
            title: tooltip(entry),
            onclick: () => toggleSelection(entry.name),
            onkeydown: (event) => {
                if (event.key !== "Enter" && event.key !== " ") return;
                event.preventDefault();
                toggleSelection(entry.name);
            },
        });

        const imageBox = el("div", { class: "skutils-tile-img" });
        appendThumb(imageBox, entry, entry.name, "skutils-fallback");

        tile.append(
            imageBox,
            el("div", { class: "skutils-tile-name", text: entry.name }),
            el("div", { class: "skutils-tile-section", text: entry.section || "" }),
            el("div", { class: "skutils-tile-order" }),
            el("button", {
                class: "skutils-tile-edit",
                type: "button",
                text: "✎",
                title: entry.source === "custom" ? "Edit this style" : "Clone to a custom style",
                onclick: (event) => {
                    event.stopPropagation();
                    openEditor(entry);
                },
            }),
        );

        modal.tiles.set(entry.name, tile);
        fragment.append(tile);
    }

    modal.grid.append(fragment);
}

function applyFilters() {
    const query = modal.search.value.trim().toLowerCase();
    const section = modal.sectionSelect.value;
    let visible = 0;

    for (const [name, tile] of modal.tiles) {
        const entry = current.entries.get(name);
        const matchesSection = !section || entry?.section === section;
        const matchesQuery = !query || (current.searchText.get(name) || name.toLowerCase()).includes(query);
        const show = matchesSection && matchesQuery;
        tile.style.display = show ? "" : "none";
        if (show) visible += 1;
    }

    let empty = modal.grid.querySelector(".skutils-grid-empty");
    if (!visible) {
        if (!empty) {
            empty = el("div", {
                class: "skutils-grid-empty",
                text: "No styles match the current search.",
            });
            modal.grid.append(empty);
        }
    } else if (empty) {
        empty.remove();
    }

    modal.visible = visible;
}

function toggleSelection(name) {
    const index = current.selected.indexOf(name);
    if (index >= 0) current.selected.splice(index, 1);
    else current.selected.push(name);
    renderStrip();
    syncTiles();
    updateFooter();
}

function moveSelection(from, to) {
    if (!Number.isInteger(from) || from < 0 || from >= current.selected.length) return;
    if (from === to) return;
    const [name] = current.selected.splice(from, 1);
    current.selected.splice(Math.min(to, current.selected.length), 0, name);
    renderStrip();
    syncTiles();
    updateFooter();
}

function syncTiles() {
    for (const [name, tile] of modal.tiles) {
        const index = current.selected.indexOf(name);
        tile.classList.toggle("selected", index >= 0);
        const badge = tile.querySelector(".skutils-tile-order");
        badge.style.display = index >= 0 ? "flex" : "none";
        badge.textContent = index >= 0 ? String(index + 1) : "";
    }
}

function renderStrip() {
    modal.strip.replaceChildren();

    if (!current.selected.length) {
        modal.strip.append(
            el("span", { class: "skutils-strip-empty", text: "No styles selected — click tiles below." }),
        );
        return;
    }

    current.selected.forEach((name, index) => {
        const entry = entryByName(name);
        const missing = Boolean(library) && !entry;
        const chip = el("div", {
            class: `skutils-chip${missing ? " missing" : ""}`,
            draggable: "true",
            title: entry ? tooltip(entry) : `${name} (not found in the library)`,
        });

        const thumb = el("div", { class: "skutils-chip-thumb" });
        appendThumb(thumb, entry, name, "skutils-chip-fallback");
        thumb.append(el("span", { class: "skutils-chip-order", text: String(index + 1) }));

        const actions = el(
            "div",
            { class: "skutils-chip-actions" },
            el("button", {
                class: "skutils-chip-btn",
                type: "button",
                text: "‹",
                title: "Move left",
                disabled: index === 0,
                onclick: (event) => {
                    event.stopPropagation();
                    moveSelection(index, index - 1);
                },
            }),
            el("button", {
                class: "skutils-chip-btn",
                type: "button",
                text: "›",
                title: "Move right",
                disabled: index === current.selected.length - 1,
                onclick: (event) => {
                    event.stopPropagation();
                    moveSelection(index, index + 1);
                },
            }),
            el("button", {
                class: "skutils-chip-btn",
                type: "button",
                text: "×",
                title: "Remove",
                onclick: (event) => {
                    event.stopPropagation();
                    current.selected.splice(index, 1);
                    renderStrip();
                    syncTiles();
                    updateFooter();
                },
            }),
        );

        chip.append(
            thumb,
            el(
                "div",
                { class: "skutils-chip-body" },
                el("span", { class: "skutils-chip-name", text: name }),
                actions,
            ),
        );

        chip.addEventListener("dragstart", (event) => {
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", String(index));
            chip.classList.add("dragging");
        });
        chip.addEventListener("dragend", () => chip.classList.remove("dragging"));
        chip.addEventListener("dragover", (event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
        });
        chip.addEventListener("drop", (event) => {
            event.preventDefault();
            const from = Number.parseInt(event.dataTransfer.getData("text/plain"), 10);
            moveSelection(from, index);
        });

        modal.strip.append(chip);
    });
}

function updateFooter() {
    const count = current.selected.length;
    modal.count.textContent = `${count} selected`;
    modal.applyButton.disabled = false;
    modal.clearButton.disabled = count === 0;

    const batchWidget = current.node?.widgets?.find((widget) => widget.name === "batch_mode");
    modal.hint.textContent = batchWidget?.value
        ? `Batch mode: the graph runs once per style, in order (${modal.visible} shown).`
        : `Combine mode: styles are merged into one prompt (${modal.visible} shown).`;
}

// ---------------------------------------------------------------------------
// Extension
// ---------------------------------------------------------------------------

app.registerExtension({
    name: "Skutils.StyleSelector",
    async nodeCreated(node) {
        if (node.comfyClass !== NODE_CLASS && node.type !== NODE_CLASS) return;
        setupNode(node);
    },
});
