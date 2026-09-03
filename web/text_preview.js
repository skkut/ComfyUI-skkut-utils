import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

/**
 * ComfyUI Skutils Text Preview – show executed text AND keep it in the
 * workflow JSON
 *
 * The node declares a plain `text` input port (STRING, forceInput) with
 * no widget of its own. This extension adds the display:
 *
 *  - onNodeCreated/onConfigure: nothing shows until there is something
 *    to show.
 *  - onExecuted: the executed text is written into a real multiline
 *    STRING widget created with ComfyWidgets["STRING"]. Widget values are
 *    what ComfyUI serializes into the workflow JSON on save — so the
 *    text that was displayed is stored inside the saved workflow itself.
 *  - configure/onConfigure: the modern frontend removes programmatically
 *    added widgets while configuring a node, so the incoming
 *    widgets_values are stashed first and the text widget is rebuilt from
 *    them afterwards. Loading a saved workflow therefore shows the stored
 *    text again, with no re-run.
 *
 * (Pattern follows the widely-used "Show Text" node, minus the widgets
 * that would escape the workflow JSON.)
 */
app.registerExtension({
    name: "SkkutUtils.TextPreview",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkutilsTextPreview") return;

        /**
         * (Re)build the display widget for `text`.
         * On some frontends the input port carries a hidden converted
         * widget that must be left in place (first entry), so only the
         * widgets we created are removed before re-adding.
         */
        function populate(payload) {
            if (payload == null) return; // nothing executed -> keep what's shown
            const values = (Array.isArray(payload) ? payload : [payload]).filter(
                (v) => typeof v === "string" && v.length > 0
            );

            if (this.widgets) {
                // Older frontends may have a hidden converted-widget for
                // the input; keep it, drop everything else.
                const keepFirst = +!!this.inputs?.[0]?.widget;
                for (let i = keepFirst; i < this.widgets.length; i++) {
                    this.widgets[i].onRemove?.();
                }
                this.widgets.length = keepFirst;
            }

            for (const value of values) {
                const widget = ComfyWidgets["STRING"](
                    this,
                    "text",
                    ["STRING", { multiline: true }],
                    app
                ).widget;
                // Read-only display: the value is set from execution (or
                // restored from the saved workflow), never hand-edited.
                widget.inputEl.readOnly = true;
                widget.inputEl.style.opacity = 0.6;
                widget.value = value;
            }

            // Let the node grow to fit the text on older frontends; the
            // modern frontend sizes multiline widgets itself.
            requestAnimationFrame(() => {
                const sz = this.computeSize?.();
                if (sz && this.size) {
                    if (sz[0] < this.size[0]) sz[0] = this.size[0];
                    if (sz[1] < this.size[1]) sz[1] = this.size[1];
                    this.onResize?.(sz);
                }
                app.graph.setDirtyCanvas(true, false);
            });
        }

        // When the node is executed we receive the text that was run;
        // store it in the widget so saving the workflow captures it.
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const result = onExecuted ? onExecuted.apply(this, arguments) : undefined;
            populate.call(this, message?.text ?? message?.ui?.text);
            return result;
        };

        // Keep the raw widgets_values: the modern frontend removes our
        // widget during configure, so rebuild it from the saved value.
        const VALUES = Symbol();
        const configure = nodeType.prototype.configure;
        nodeType.prototype.configure = function () {
            this[VALUES] = arguments[0]?.widgets_values;
            return configure ? configure.apply(this, arguments) : undefined;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            const values = this[VALUES];
            if (values?.length) {
                // Widget creation can lag a frame behind configure.
                requestAnimationFrame(() => {
                    populate.call(this, values);
                });
            }
            return result;
        };
    },
});
