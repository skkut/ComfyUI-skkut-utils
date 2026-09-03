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
"""


class SkutilsTextPreview:
    """Show ``text`` in the node and keep it in the saved workflow.

    Same port-only input shape as the built-in "Preview as Text" node,
    but the text that was displayed lives in a serialized widget: save
    the workflow and the text is in the JSON; load it and the text is
    back, with no re-run needed.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "forceInput": True,
                        "tooltip": ("Text to display. Connect any STRING output; the "
                                    "text shown after a run is stored in the node and "
                                    "saved with the workflow JSON."),
                    },
                ),
            }
        }

    RETURN_TYPES = ()
    FUNCTION = "preview"
    OUTPUT_NODE = True
    CATEGORY = "utils/text"

    def preview(self, text):
        # The UI payload is picked up by web/text_preview.js, which stores
        # it in a serialized widget so it survives a workflow save.
        return {"ui": {"text": [text]}}
