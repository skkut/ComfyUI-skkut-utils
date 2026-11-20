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
 *
 * Subgraphs: when the megapixels widget is promoted to a subgraph node, the
 * frontend gives the host node a store-backed "promoted" widget and never
 * forwards edits to the interior node's widget callback (SubgraphNode
 * `_setWidget` + `promotedWidgetStoreProjection`). That host widget is what
 * the user interacts with, so this extension also decorates every promoted
 * host widget whose interior source is this node's megapixels widget: it adds
 * "Custom…" to the host option list, re-adds saved custom values, wraps the
 * host widget's callback with the same prompt, and intercepts direct writes
 * of the "Custom…" sentinel to the widget-value store. That last part matters
 * for surfaces that bypass the widget callback — the right-side Parameters
 * panel writes the value to the store first (`promotedInputWidget` creates a
 * plain projection whose callback only stores the value), so without the
 * interception picking "Custom…" there would store the literal label and
 * never open the prompt. Nested subgraphs (a promoted input of a promoted
 * input) are resolved through the link chain.
 *
 * A "Custom…" value can also be left behind by an older version or a failed
 * prompt. It is not a valid megapixels value (it fails server validation), and
 * in the canvas renderer re-selecting it would be a no-op because
 * `ComboWidget.setValue` ignores a selection equal to the current value. Both
 * the interior and promoted widgets therefore restore the last real value
 * (or the `1.0` default) whenever the sentinel is found or selected.
 */

const NODE_CLASS = "SkutilsResolutionCalculator";
const MEGAPIXELS_WIDGET = "megapixels";
const CUSTOM_OPTION = "Custom…";
const DEFAULT_FALLBACK = "1.0";
/** Custom values are canonicalised to at most this many decimal places. */
const MAX_DECIMALS = 4;
/** Guard against malformed/cyclic promotion chains. */
const MAX_PROMOTION_DEPTH = 100;

/**
 * Megapixels widgets that can receive a direct "Custom…" store write, keyed
 * by ComfyUI widget id. Covers promoted host widgets (right-side panel) and
 * ordinary interior widgets (Vue node grid).
 */
const megapixelsTargets = new Map();

/** The patched `useWidgetValueStore()` instance, once found. */
let patchedWidgetStore = null;

/**
 * True while a workflow graph is being configured/loaded. The frontend applies
 * saved widget values through the same store path as user edits, so a saved
 * "Custom…" sentinel would otherwise open a prompt on file open. During a load
 * such values are repaired silently instead.
 */
let configuringGraph = false;

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

    nodeCreated(node) {
        if (isSubgraphNode(node)) {
            watchSubgraphNode(node);
            scheduleRescan();
        } else if (isResolutionNode(node)) {
            // A calculator instance may have been created after a host
            // subgraph node had already resolved its promoted widget.
            scheduleRescan();
        }
    },

    loadedGraphNode(node) {
        if (isSubgraphNode(node)) decorateSubgraphNode(node);
    },

    beforeLoadGraph() {
        configuringGraph = true;
    },

    beforeConfigureGraph() {
        configuringGraph = true;
    },

    afterConfigureGraph() {
        configuringGraph = false;
        scheduleRescan();
    },

    afterLoadGraph() {
        configuringGraph = false;
        scheduleRescan();
    },

    onGraphLoadError() {
        configuringGraph = false;
        scheduleRescan();
    },

    setup() {
        ensureWidgetStorePatch();
        scheduleRescan();
    },
});

function findMegapixelsWidget(node) {
    return node.widgets?.find((widget) => widget.name === MEGAPIXELS_WIDGET) ?? null;
}

function setupMegapixels(node) {
    const widget = findMegapixelsWidget(node);
    if (!widget) return;

    const values = getValues(widget);
    if (!values) return; // function-backed (dynamic) combos are left alone

    let state = widget.__skutilsCustomMegapixels;
    if (!state) {
        state = { lastValue: realValue(widget.value), wrapper: null, prompting: false };
        widget.__skutilsCustomMegapixels = state;
        trackLastValue(widget, state);
        installCallbackWrapper(node, widget, state);
    }

    setValues(widget, [...withoutCustomOption(values), CUSTOM_OPTION]);
    normalizeSentinel(node, widget, state);
    registerMegapixelsTarget(node, widget, state);
}

/* ------------------------------------------------------------------------- *
 * Promoted widgets on subgraph nodes
 * ------------------------------------------------------------------------- */

function isSubgraphNode(node) {
    if (typeof node?.isSubgraphNode === "function") return node.isSubgraphNode();
    return Boolean(node?.subgraph?.inputNode);
}

function isResolutionNode(node) {
    const type = node?.comfyClass ?? node?.type ?? node?._state?.type;
    return type === NODE_CLASS;
}

let rescanQueued = false;

/**
 * Debounced sweep of the graphs for subgraph nodes with a promoted megapixels
 * input. Runs after promotion/binding/load changes so every host widget gets
 * decorated even when the frontend rebuilt it without telling us directly.
 */
function scheduleRescan() {
    if (rescanQueued) return;
    rescanQueued = true;
    setTimeout(() => {
        rescanQueued = false;
        scanForPromotedMegapixels(app.graph);
        const activeGraph = app.canvas?.graph;
        if (activeGraph && activeGraph !== app.graph) {
            scanForPromotedMegapixels(activeGraph);
        }
    }, 0);
}

function scanForPromotedMegapixels(graph) {
    const seen = new Set();

    const visitNode = (node) => {
        if (!isSubgraphNode(node)) return;
        decorateSubgraphNode(node);
        const subgraph = node.subgraph;
        if (!subgraph || seen.has(subgraph)) return;
        seen.add(subgraph);
        for (const child of subgraph.nodes ?? []) visitNode(child);
    };

    const visitGraph = (current) => {
        if (!current || seen.has(current)) return;
        seen.add(current);
        for (const node of current.nodes ?? []) visitNode(node);
    };

    visitGraph(graph);
}

/** Watch a subgraph node for promotions/rebindings that replace host widgets. */
function watchSubgraphNode(node) {
    if (node.__skutilsResolutionWatch) return;
    node.__skutilsResolutionWatch = true;

    const controller = new AbortController();
    const onSubgraphEvent = (event) => {
        // `widget-promoted` carries the instance whose bindings changed; a
        // shared subgraph definition notifies every instance, so decorate the
        // node that owns this listener as well.
        decorateSubgraphNode(event?.detail?.subgraphNode ?? node);
        if (event?.detail?.subgraphNode !== node) decorateSubgraphNode(node);
    };

    const events = node.subgraph?.events;
    for (const name of ["widget-promoted", "input-added"]) {
        try {
            events?.addEventListener?.(name, onSubgraphEvent, {
                signal: controller.signal,
            });
        } catch {
            // Frontends without abortable custom events: the handler is
            // idempotent, so a stray listener is harmless.
            events?.addEventListener?.(name, onSubgraphEvent);
        }
    }

    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
        controller.abort();
        return onRemoved?.apply(this, arguments);
    };
}

/**
 * Decorate every promoted input of `hostNode` whose interior source is this
 * node's megapixels widget.
 */
function decorateSubgraphNode(hostNode) {
    if (!isSubgraphNode(hostNode)) return;
    try {
        for (const input of hostNode.inputs ?? []) {
            if (!input?.widgetId) continue;
            const hostWidget = getHostWidget(hostNode, input);
            if (!hostWidget) continue;
            const source = resolvePromotedSource(hostNode, input);
            if (!isMegapixelsSource(source)) continue;
            decorateHostWidget(hostNode, hostWidget);
        }
    } catch (error) {
        // Never let decoration break the frontend's promotion flow.
        console.warn("[skkut-utils] failed to decorate promoted megapixels widget", error);
    }
}

function getHostWidget(hostNode, input) {
    return hostNode.getWidgetFromSlot?.(input) ?? input?._widget ?? null;
}

/**
 * Walk the promotion chain of `input` to the concrete interior widget.
 * Returns `{ node, widget }` or null when the input is not promoted to a
 * real widget (e.g. connected by a link instead).
 */
function resolvePromotedSource(hostNode, input, depth = 0) {
    if (depth >= MAX_PROMOTION_DEPTH) return null;
    const slot = input?._subgraphSlot;
    const subgraph = hostNode?.subgraph;
    if (!slot || !subgraph) return null;

    for (const linkId of slot.linkIds ?? []) {
        const link = subgraph.getLink?.(linkId);
        if (!link) continue;
        const resolved = resolveLink(link, subgraph);
        if (!resolved) continue;
        const { inputNode, targetInput } = resolved;

        if (isSubgraphNode(inputNode)) {
            const nested = resolvePromotedSource(inputNode, targetInput, depth + 1);
            if (nested) return nested;
            continue;
        }

        const widget =
            inputNode.getWidgetFromSlot?.(targetInput) ??
            findWidgetByInput(inputNode, targetInput);
        if (widget) return { node: inputNode, widget };
    }
    return null;
}

function resolveLink(link, subgraph) {
    try {
        if (typeof link.resolve === "function") {
            const { inputNode, input } = link.resolve(subgraph);
            if (inputNode && input) return { inputNode, targetInput: input };
        }
    } catch {
        // Fall through to the raw link fields below.
    }
    const inputNode = subgraph.getNodeById?.(link.target_id);
    const targetInput = inputNode?.inputs?.[link.target_slot];
    return inputNode && targetInput ? { inputNode, targetInput } : null;
}

function findWidgetByInput(node, input) {
    const name = input?.widget?.name;
    if (!name) return null;
    return node?.widgets?.find((widget) => widget.name === name) ?? null;
}

function isMegapixelsSource(source) {
    if (!source?.widget || source.widget.name !== MEGAPIXELS_WIDGET) return false;
    return (
        isResolutionNode(source.node) ||
        Boolean(source.widget.__skutilsCustomMegapixels)
    );
}

/**
 * Make a promoted host widget behave like the interior megapixels widget:
 * keep "Custom…" and the current value in its option list, and intercept the
 * "Custom…" selection with the prompt.
 */
function decorateHostWidget(hostNode, widget) {
    let state = widget.__skutilsPromotedMegapixels;
    if (!state) {
        state = { lastValue: realValue(widget.value), wrapper: null, prompting: false };
        widget.__skutilsPromotedMegapixels = state;
        trackLastValue(widget, state);
        installCallbackWrapper(hostNode, widget, state);
    } else if (widget.callback !== state.wrapper) {
        // The frontend (or another extension) replaced the host widget's
        // callback while rebinding; re-install the interception, chaining to
        // the new callback.
        installCallbackWrapper(hostNode, widget, state);
    }

    const current = realValue(widget.value);
    if (current !== undefined) state.lastValue = current;
    refreshHostOptions(widget);
    normalizeSentinel(hostNode, widget, state);
    registerMegapixelsTarget(hostNode, widget, state);
}

/**
 * Chain the widget's callback so a "Custom…" selection opens the prompt.
 * Selections of real values are forwarded unchanged. The store-level
 * interception below may have opened the prompt already; `state.prompting`
 * keeps a single selection from opening it twice.
 */
function installCallbackWrapper(node, widget, state) {
    const callback = widget.callback;
    const wrapper = function (value, ...args) {
        if (value !== CUSTOM_OPTION) {
            return callback?.apply(this, [value, ...args]);
        }
        beginCustomSelection(node, widget, state);
    };
    state.wrapper = wrapper;
    widget.callback = wrapper;
}

/** A selectable megapixels value, or undefined for null/empty/Custom… */
function realValue(value) {
    if (value == null) return undefined;
    const text = String(value);
    return text === "" || text === CUSTOM_OPTION ? undefined : text;
}

/**
 * The value to fall back to when a widget holds the "Custom…" sentinel but no
 * real value is known. `1.0` is the backend default, so prefer it when it is
 * one of the presets; otherwise use the first numeric preset.
 */
function realFallback(widget) {
    const values = getValues(widget);
    const presets = values ? withoutCustomOption(values).map(String) : [];
    if (presets.includes(DEFAULT_FALLBACK)) return DEFAULT_FALLBACK;
    const numeric = presets.find((value) => Number.isFinite(Number(value)));
    return numeric ?? presets[0] ?? DEFAULT_FALLBACK;
}

/**
 * "Custom…" is a UI sentinel, never a valid widget value: it fails server
 * validation and, in the canvas renderer, makes re-selecting Custom… a no-op
 * (`ComboWidget.setValue` ignores a selection equal to the current value).
 * Replace it with the last real value as soon as we see it.
 */
function normalizeSentinel(node, widget, state) {
    if (widget.value !== CUSTOM_OPTION) return;
    const restore = realValue(state.lastValue) ?? realFallback(widget);
    state.lastValue = restore;
    if (configuringGraph) {
        // Mid-configure: write the store directly, without onWidgetChanged /
        // version side effects meant for interactive edits.
        widget.value = restore;
        return;
    }
    applyValue(node, widget, restore);
}

/**
 * Open the custom-value prompt once per selection. Any sentinel already
 * written by the frontend is restored first, so a prompt that fails to open
 * (or a workflow queued while it is open) never leaves "Custom…" behind.
 */
function beginCustomSelection(node, widget, state) {
    if (state.prompting) return;

    const restore = realValue(state.lastValue) ?? realFallback(widget);
    state.lastValue = restore;
    if (widget.value === CUSTOM_OPTION) widget.value = restore;

    // Saved sentinels are applied during graph configuration through the same
    // path as user edits; repair them without interrupting the workflow load.
    if (configuringGraph) return;

    state.prompting = true;
    void requestCustomValue(node, widget, state).finally(() => {
        state.prompting = false;
    });
}

/* ------------------------------------------------------------------------- *
 * Widget-value store interception
 * ------------------------------------------------------------------------- */

/**
 * Remember a widget so direct writes of "Custom…" to the widget-value store
 * can be intercepted. Needed because the right-side Parameters panel builds
 * its own widget projection (`promotedInputWidget`) whose callback only writes
 * the store — it never runs the decorated widget's callback.
 */
function registerMegapixelsTarget(node, widget, state) {
    let id;
    try {
        id = widget?.widgetId;
    } catch {
        return;
    }
    if (!id) return;

    megapixelsTargets.set(id, { node, widget, state });
    ensureWidgetStorePatch();
}

function ensureWidgetStorePatch() {
    if (patchedWidgetStore) return patchedWidgetStore;

    const store = findWidgetValueStore();
    if (!store) return null;

    const originalSetValue = store.setValue;
    if (typeof originalSetValue !== "function") return null;

    try {
        store.setValue = function (id, value) {
            const target = megapixelsTargets.get(id);
            if (target) {
                if (value === CUSTOM_OPTION) {
                    return interceptCustomOptionWrite(
                        this,
                        originalSetValue,
                        id,
                        target
                    );
                }
                const text = realValue(value);
                if (text !== undefined) target.state.lastValue = text;
            }
            return originalSetValue.call(this, id, value);
        };
    } catch (error) {
        console.warn(
            "[skkut-utils] could not intercept promoted widget values",
            error
        );
        return null;
    }

    patchedWidgetStore = store;
    return store;
}

function interceptCustomOptionWrite(store, originalSetValue, id, target) {
    const { node, widget, state } = target;

    // The panel writes the sentinel three times for one selection (store,
    // widget value setter, then the projection's callback); only the first
    // should open the prompt.
    if (state.prompting) return true;

    // The projection the panel handed us may have been rebuilt or demoted;
    // do not act on a stale target.
    let liveId;
    try {
        liveId = widget?.widgetId;
    } catch {
        liveId = undefined;
    }
    if (widget && liveId !== undefined && liveId !== id) {
        megapixelsTargets.delete(id);
        return originalSetValue.call(store, id, CUSTOM_OPTION);
    }

    const restore = realValue(state.lastValue) ?? realFallback(widget);
    state.lastValue = restore;
    originalSetValue.call(store, id, restore);
    beginCustomSelection(node, widget, state);
    return true;
}

/**
 * Locate the frontend's widget-value Pinia store. It is not exported to
 * extensions, so reach it through the mounted Vue app (best effort; when this
 * fails the canvas and Vue-node-grid paths still work because they call the
 * decorated widget's callback directly).
 */
function findWidgetValueStore() {
    try {
        const pinia = findPinia();
        const store = pinia?._s?.get?.("widgetValue");
        return store && typeof store.setValue === "function" ? store : null;
    } catch {
        return null;
    }
}

function findPinia() {
    const roots = [
        document.getElementById("vue-app"),
        document.getElementById("app"),
    ];
    for (const root of roots) {
        const pinia = root?.__vue_app__?.config?.globalProperties?.$pinia;
        if (pinia) return pinia;
    }

    const first = document.body?.firstElementChild;
    const firstPinia = first?.__vue_app__?.config?.globalProperties?.$pinia;
    if (firstPinia) return firstPinia;

    // Last resort: bounded walk for whichever element owns the Vue app.
    const queue = document.body ? [document.body] : [];
    for (let seen = 0; queue.length && seen < 4000; seen++) {
        const element = queue.shift();
        const pinia =
            element?.__vue_app__?.config?.globalProperties?.$pinia;
        if (pinia) return pinia;
        for (const child of element.children) queue.push(child);
    }
    return null;
}

/** Keep the host option list in sync with the current value + Custom… */
function refreshHostOptions(widget) {
    const values = getValues(widget);
    if (!values) return;

    const next = withoutCustomOption(values);
    const current = realValue(widget.value);
    if (current !== undefined) insertOption(next, current);
    next.push(CUSTOM_OPTION);

    if (
        values.length !== next.length ||
        values.some((value, index) => value !== next[index])
    ) {
        setValues(widget, next);
    }
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
            const text = realValue(value);
            if (text !== undefined) state.lastValue = text;
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
    insertOption(presets, text);
    setValues(widget, [...presets, CUSTOM_OPTION]);
}

/** Insert `text` into `values` in numeric order; non-numeric values go last. */
function insertOption(values, text) {
    if (values.includes(text)) return;
    const number = Number(text);
    let index = values.length;
    if (Number.isFinite(number)) {
        const firstGreater = values.findIndex((preset) => {
            const presetNumber = Number(preset);
            return Number.isFinite(presetNumber) && presetNumber > number;
        });
        if (firstGreater !== -1) index = firstGreater;
    }
    values.splice(index, 0, text);
}

function applyValue(node, widget, value) {
    const previous = widget.value;
    if (previous === value) return;
    widget.value = value;
    node?.onWidgetChanged?.(widget.name, value, previous, widget);
    node?.graph?.incrementVersion?.();
    node?.setDirtyCanvas?.(true, true);
}
