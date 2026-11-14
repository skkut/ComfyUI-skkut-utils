import { app } from "../../scripts/app.js";

/**
 * Skutils Resolution Calculator – any megapixel value from the dropdown
 *
 * The backend declares `megapixels` as a COMBO holding a short list of
 * prominent presets (0.5–20.0 MP). This extension keeps that dropdown and
 * adds a "Custom…" entry to
 * each node instance (browser-side only — the server's preset list is
 * untouched). Picking "Custom…" asks for a number, accepts any positive
 * value (e.g. 3.75, 24, 0.3), and inserts it into the dropdown in numeric
 * order so both renderers display it like a preset.
 *
 * How the value survives:
 *  - It is written to the widget (`widget.value`), which is what ComfyUI
 *    serialises into the workflow JSON and sends in the API prompt. The new
 *    Vue node renderer keeps widget values in its value store, so the same
 *    assignment updates the store and the on-node display.
 *  - The backend's `VALIDATE_INPUTS(megapixels)` accepts any positive
 *    number, which exempts the input from the server's combo-membership
 *    check.
 *  - When a saved workflow is loaded, the stored value is re-added to the
 *    dropdown so the node shows it as the current selection instead of an
 *    unknown value.
 *
 * Cancel restores the previously selected preset; invalid input re-prompts.
 */

const NODE_CLASS = "SkutilsResolutionCalculator";
const MEGAPIXELS_WIDGET = "megapixels";
const CUSTOM_OPTION = "Custom…";
const DEFAULT_FALLBACK = "1.0";
/** Custom values are canonicalised to at most this many decimal places. */
const MAX_DECIMALS = 4;

app.registerExtension({
    name: "SkkutUtils.ResolutionCalculator",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_CLASS) return;

        // Widgets exist by the time onNodeCreated runs; onConfigure covers
        // nodes restored from a workflow (and re-adds a saved custom value).
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
            setupMegapixels(this);
            return result;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = onConfigure?.apply(this, arguments);
            setupMegapixels(this);
            const widget = findMegapixelsWidget(this);
            if (widget) ensureOption(widget, widget.value);
            return result;
        };
    },
});

function findMegapixelsWidget(node) {
    return node.widgets?.find((widget) => widget.name === MEGAPIXELS_WIDGET) ?? null;
}

function setupMegapixels(node) {
    const widget = findMegapixelsWidget(node);
    if (!widget || widget.__skutilsCustomMegapixels) return;

    const values = getValues(widget);
    if (!values) return; // function-backed (dynamic) combos are left alone

    const state = { lastValue: widget.value };
    widget.__skutilsCustomMegapixels = state;
    trackLastValue(widget, state);
    setValues(widget, [...withoutCustomOption(values), CUSTOM_OPTION]);

    const callback = widget.callback;
    widget.callback = function (value, ...args) {
        if (value !== CUSTOM_OPTION) {
            return callback?.apply(this, [value, ...args]);
        }
        void requestCustomValue(node, widget, state);
    };
}

/**
 * Remember the last real selection, so cancelling the prompt can restore it.
 * Both renderers write through the widget's `value` accessor: the canvas
 * combo's setValue does `this.value = v`, and the Vue update handler does
 * `live.widget.value = v`. Values loaded with a workflow take the same path.
 */
function trackLastValue(widget, state) {
    let descriptor;
    for (let target = widget; target; target = Object.getPrototypeOf(target)) {
        descriptor = Object.getOwnPropertyDescriptor(target, "value");
        if (descriptor) break;
    }
    if (!descriptor?.get || !descriptor?.set) return; // plain data property
    Object.defineProperty(widget, "value", {
        configurable: true,
        enumerable: true,
        get() {
            return descriptor.get.call(this);
        },
        set(value) {
            descriptor.set.call(this, value);
            if (value !== CUSTOM_OPTION) state.lastValue = value;
        },
    });
}

async function requestCustomValue(node, widget, state) {
    let invalid = null;
    try {
        for (;;) {
            const previous = state.lastValue ?? DEFAULT_FALLBACK;
            const input = await promptForValue(messageFor(invalid), previous);
            if (input === null) {
                applyValue(node, widget, previous);
                return;
            }
            const value = parseMegapixels(input);
            if (!value) {
                invalid = String(input).trim();
                continue;
            }
            ensureOption(widget, value);
            applyValue(node, widget, value);
            return;
        }
    } catch (error) {
        console.error("[skkut-utils] custom megapixels prompt failed", error);
        applyValue(node, widget, state.lastValue ?? DEFAULT_FALLBACK);
    }
}

function messageFor(invalid) {
    if (invalid) {
        return `"${invalid}" is not a positive number. Enter a target in megapixels (e.g. 3.75).`;
    }
    return (
        "Enter a target in megapixels (1 MP = 1,000,000 px). " +
        "Any positive number works; the result never exceeds it."
    );
}

async function promptForValue(message, defaultValue) {
    const fallback = String(defaultValue ?? DEFAULT_FALLBACK);
    const dialog = app.extensionManager?.dialog;
    if (typeof dialog?.prompt === "function") {
        return await dialog.prompt({
            title: "Custom megapixels",
            message,
            defaultValue: fallback,
            placeholder: "e.g. 3.75",
        });
    }
    // Very old frontends without app.extensionManager.dialog.
    return window.prompt(message, fallback);
}

/** Canonical string form (matches the preset style, e.g. "2.0", "3.75"). */
function parseMegapixels(raw) {
    const text = String(raw ?? "").trim();
    if (!text) return null;
    const number = Number(text);
    if (!Number.isFinite(number) || number <= 0) return null;
    const factor = 10 ** MAX_DECIMALS;
    const rounded = Math.round(number * factor) / factor;
    if (!Number.isFinite(rounded) || rounded <= 0) return null;
    const formatted = String(rounded);
    return formatted.includes(".") ? formatted : `${formatted}.0`;
}

function getValues(widget) {
    const values = widget.options?.values;
    return Array.isArray(values) ? values : null;
}

function withoutCustomOption(values) {
    return values.filter((value) => value !== CUSTOM_OPTION);
}

/**
 * Replace the options object (instead of mutating the shared array) so the
 * custom value is local to this node instance and the Vue renderer, which
 * reads `options` from its widget store, sees the change.
 */
function setValues(widget, values) {
    if (typeof widget.options !== "object" || widget.options === null) return;
    widget.options = { ...widget.options, values };
}

function ensureOption(widget, value) {
    if (value == null) return;
    const text = String(value);
    if (text === "" || text === CUSTOM_OPTION) return;
    const values = getValues(widget);
    if (!values || values.includes(text)) return;

    // Insert among the numeric presets; anything non-numeric goes last.
    const presets = withoutCustomOption(values);
    const number = Number(text);
    let index = presets.length;
    if (Number.isFinite(number)) {
        const firstGreater = presets.findIndex((preset) => {
            const presetNumber = Number(preset);
            return Number.isFinite(presetNumber) && presetNumber > number;
        });
        if (firstGreater !== -1) index = firstGreater;
    }
    presets.splice(index, 0, text);
    setValues(widget, [...presets, CUSTOM_OPTION]);
}

function applyValue(node, widget, value) {
    const previous = widget.value;
    if (previous === value) return;
    widget.value = value;
    node?.onWidgetChanged?.(widget.name, value, previous, widget);
    node?.graph?.incrementVersion?.();
    node?.setDirtyCanvas?.(true, true);
}
