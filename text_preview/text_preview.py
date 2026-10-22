"""
Skutils Text Preview — node implementation.

A text display node that does what the built-in display-only text nodes
don't: the text it shows is stored in the saved workflow JSON.

Why a frontend extension is needed
----------------------------------
ComfyUI serializes *widget values* into the workflow JSON when you save.
The built-in text-preview nodes never rely on that — their display
widgets are marked ``serialize: false`` and are filled from execution
output at runtime, so nothing survives a save/reload.

This node's input is a plain STRING port (no widget of its own, exactly
like the built-in "Preview as Text" node).  web/text_preview.js is the
display half: after each run it copies the executed text into a real,
serialized multiline widget (ComfyWidgets["STRING"]), and when a saved
workflow is loaded it rebuilds that widget from the stored value.  The
widget value — what you see — is therefore what a workflow save writes
to the JSON, and what a workflow load restores.

The input is optional.  An unconnected ``text`` port (or an upstream
empty string) makes the next run clear the displayed widget instead of
failing prompt validation, so a preview left over from an earlier run
does not masquerade as the current one.
"""


class SkutilsTextPreview:
    """Show ``text`` in the node and keep it in the saved workflow.

    The port-only input is optional: when it is unconnected (or an empty
    string), a run clears the displayed text instead of failing prompt
    validation.  The displayed text lives in a serialized widget, so a
    workflow save writes it to the JSON and a load restores it without a
    re-run.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "optional": {
                "text": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": ("Text to display. Connect any STRING output; the "
                                    "text shown after a run is stored in the node and "
                                    "saved with the workflow JSON. Leave unconnected to "
                                    "clear the preview on the next run."),
                    },
                ),
            }
        }

    RETURN_TYPES = ()
    FUNCTION = "preview"
    OUTPUT_NODE = True
    CATEGORY = "utils/text"

    def preview(self, text=None):
        # The UI payload is picked up by web/text_preview.js, which stores
        # it in a serialized widget so it survives a workflow save.  An
        # empty list tells the frontend to remove the display widget when
        # nothing was received.
        return {"ui": {"text": [] if text is None else [text]}}
