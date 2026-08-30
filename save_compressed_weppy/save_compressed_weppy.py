import os
import json
import random
import numpy as np
from PIL import Image
import folder_paths

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
                "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
                }

    RETURN_TYPES = ()
    FUNCTION = "save_images"
    OUTPUT_NODE = True
    CATEGORY = "image"

    def save_images(self, images, filename_prefix="ComfyUI_Weppy", quality=80, lossless=False, prompt=None, extra_pnginfo=None):
        filename_prefix += self.prefix_append
        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(filename_prefix, self.output_dir, images[0].shape[1], images[0].shape[0])
        results = list()
        
        for (batch_number, image) in enumerate(images):
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
            
            try:
                import piexif
                if prompt is not None:
                    exif_dict["0th"][piexif.ImageIFD.Make] = ("prompt:" + json.dumps(strip_binary_from_workflow(prompt))).encode("utf-8")
                if extra_pnginfo is not None and "workflow" in extra_pnginfo:
                    exif_dict["0th"][piexif.ImageIFD.ImageDescription] = ("workflow:" + json.dumps(strip_binary_from_workflow(extra_pnginfo["workflow"]))).encode("utf-8")
                exif_bytes = piexif.dump(exif_dict)
            except ImportError:
                # Fallback to Pillow native EXIF if piexif is not installed
                exif_bytes = img.getexif()
                if prompt is not None:
                    exif_bytes[0x010f] = ("prompt:" + json.dumps(strip_binary_from_workflow(prompt))).encode("utf-8")
                if extra_pnginfo is not None and "workflow" in extra_pnginfo:
                    exif_bytes[0x010e] = ("workflow:" + json.dumps(strip_binary_from_workflow(extra_pnginfo["workflow"]))).encode("utf-8")

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
