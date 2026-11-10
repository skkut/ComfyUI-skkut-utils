import os
import json
import random
import numpy as np
from PIL import Image
import folder_paths

TEXT_PREVIEW_NODE = "SkutilsTextPreview"


def strip_binary_from_workflow(value):
    if isinstance(value, dict):
        return {k: strip_binary_from_workflow(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [strip_binary_from_workflow(v) for v in value]
    elif isinstance(value, str):
        if value.startswith("data:") and ";base64," in value:
            return ""
        if len(value) > 10240 and " " not in value:
            return ""
    return value


def preview_source_id(prompt, unique_id):
    """Node id feeding the save node's ``enhanced_prompt`` input, if any.

    The API-format prompt keeps the link for a node's inputs, so the save
    node can tell which preview node the executed text came from.
    """
    if not isinstance(prompt, dict) or unique_id is None:
        return None
    node = prompt.get(str(unique_id))
    inputs = node.get("inputs") if isinstance(node, dict) else None
    link = inputs.get("enhanced_prompt") if isinstance(inputs, dict) else None
    if isinstance(link, (list, tuple)) and link:
        return str(link[0])
    return None


def _apply_text_preview_text(value, text, node_id):
    """Recursive worker for :func:`apply_text_preview_text`.

    Returns ``(new_value, matched)``; only preview nodes whose id equals
    ``node_id`` (or every preview node when it is ``None``) are changed.
    """
    if isinstance(value, dict):
        matched = False
        result = {}
        for key, item in value.items():
            new_item, item_matched = _apply_text_preview_text(item, text, node_id)
            result[key] = new_item
            matched = matched or item_matched
        if result.get("type") == TEXT_PREVIEW_NODE or result.get("class_type") == TEXT_PREVIEW_NODE:
            if node_id is None or str(result.get("id")) == node_id:
                # Batch runs end with one display widget per style; keep
                # only the prompt that belongs to the image being saved.
                result["widgets_values"] = [text]
                named = result.get("widgets_values_named")
                if isinstance(named, dict) and "text" in named:
                    named = dict(named)
                    named["text"] = text
                    result["widgets_values_named"] = named
                matched = True
        return result, matched
    if isinstance(value, list):
        matched = False
        result = []
        for item in value:
            new_item, item_matched = _apply_text_preview_text(item, text, node_id)
            result.append(new_item)
            matched = matched or item_matched
        return result, matched
    return value, False


def apply_text_preview_text(value, text, node_id=None):
    """Deep-copy a workflow with a SkutilsTextPreview's text replaced.

    In batch mode the preview node runs once per selected style and ComfyUI
    merges all those UI outputs into one node, so the saved workflow would
    otherwise carry one displayed prompt per style.  The save node receives
    the executed prompt for the images it is saving (list fan-out keeps it
    index-aligned with the style) and swaps it into the embedded workflow.

    ``node_id`` selects the preview node the prompt came from.  If that id
    cannot be found in the workflow (e.g. the prompt travelled through a
    passthrough or a subgraph), every preview node is updated instead.
    """
    if node_id is not None:
        patched, matched = _apply_text_preview_text(value, text, node_id)
        if matched:
            return patched
    patched, _ = _apply_text_preview_text(value, text, None)
    return patched


class SaveCompressedWeppy:
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"
        self.prefix_append = "_" + ''.join(random.choice("abcdefghijklmnopqrstupvxyz") for _ in range(5))

    @classmethod
    def INPUT_TYPES(s):
        return {"required":
                    {"images": ("IMAGE", ),
                     "filename_prefix": ("STRING", {"default": "ComfyUI_Weppy"}),
                      "quality": ("INT", {"default": 80, "min": 1, "max": 100, "step": 1}),
                      "lossless": ("BOOLEAN", {"default": False}),
                      },
                "optional": {
                    "enhanced_prompt": ("STRING", {
                        "forceInput": True,
                        "tooltip": (
                            "Optional: the executed prompt that produced these "
                            "images (e.g. the Skutils Text Preview output). When "
                            "connected, the workflow embedded in each saved image "
                            "stores this text as the text preview's content, so "
                            "batch runs save the prompt for that image instead of "
                            "every selected style's prompt."
                        ),
                    }),
                },
                "hidden": {
                    "prompt": "PROMPT",
                    "extra_pnginfo": "EXTRA_PNGINFO",
                    "unique_id": "UNIQUE_ID",
                },
                }

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "skkut-utils"

    def save_images(self, images, filename_prefix="ComfyUI_Weppy", quality=80, lossless=False,
                    prompt=None, extra_pnginfo=None, enhanced_prompt=None, unique_id=None):
        filename_prefix += self.prefix_append
        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0])
        results = list()

        prompt_metadata = None
        if prompt is not None:
            prompt_metadata = "prompt:" + json.dumps(strip_binary_from_workflow(prompt))

        workflow_metadata = None
        if extra_pnginfo is not None and "workflow" in extra_pnginfo:
            workflow = extra_pnginfo["workflow"]
            if enhanced_prompt is not None:
                if not isinstance(enhanced_prompt, str):
                    enhanced_prompt = str(enhanced_prompt)
                source_id = preview_source_id(prompt, unique_id)
                workflow = apply_text_preview_text(workflow, enhanced_prompt, source_id)
            workflow_metadata = "workflow:" + json.dumps(strip_binary_from_workflow(workflow))

        for (batch_number, image) in enumerate(images):
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

            try:
                import piexif
                if prompt_metadata is not None:
                    exif_dict["0th"][piexif.ImageIFD.Make] = prompt_metadata.encode("utf-8")
                if workflow_metadata is not None:
                    exif_dict["0th"][piexif.ImageIFD.ImageDescription] = workflow_metadata.encode("utf-8")
                exif_bytes = piexif.dump(exif_dict)
            except ImportError:
                # Fallback to Pillow native EXIF if piexif is not installed
                exif_bytes = img.getexif()
                if prompt_metadata is not None:
                    exif_bytes[0x010f] = prompt_metadata.encode("utf-8")
                if workflow_metadata is not None:
                    exif_bytes[0x010e] = workflow_metadata.encode("utf-8")

            file = f"{filename}_{counter:05}.webp"
            full_path = os.path.join(full_output_folder, file)
            
            # Save the WebP image with embedded EXIF metadata
            img.save(full_path, format="WEBP", exif=exif_bytes, quality=quality, lossless=lossless)
            
            results.append({
                "filename": file,
                "subfolder": subfolder,
                "type": self.type
            })
            counter += 1

        return { "ui": { "images": results } }
