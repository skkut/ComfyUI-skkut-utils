import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "SaveCompressedWeppy.ContextMenu",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function (_, options) {
            if (origGetExtraMenuOptions) {
                origGetExtraMenuOptions.apply(this, arguments);
            }
            if (this.imgs && this.imgs.length > 0) {
                let imageIndex = (this.imageIndex != null) ? this.imageIndex : (this.overIndex != null ? this.overIndex : this.imgs.length - 1);
                
                const menuItem = {
                    content: "Save Compressed Weppy",
                    callback: async () => {
                        let img = this.imgs[imageIndex];
                        if (!img || !img.src) return;
                        
                        let url = new URL(img.src);
                        let filename = url.searchParams.get("filename");
                        let type = url.searchParams.get("type");
                        let subfolder = url.searchParams.get("subfolder") || "";
                        
                        if (!filename) return;

                        const p = await app.graphToPrompt();
                        const prompt = p.output;
                        const workflow = p.workflow;

                        try {
                            const response = await fetch("/save_compressed_weppy", {
                                method: "POST",
                                headers: {
                                    "Content-Type": "application/json",
                                },
                                body: JSON.stringify({
                                    filename,
                                    type,
                                    subfolder,
                                    prompt,
                                    workflow
                                })
                            });

                            if (response.ok) {
                                const blob = await response.blob();
                                const disposition = response.headers.get("Content-Disposition");
                                let downloadName = "image.webp";
                                if (disposition) {
                                    const match = disposition.match(/filename="?([^";\n]+)"?/);
                                    if (match) downloadName = match[1];
                                }
                                const url = URL.createObjectURL(blob);
                                const a = document.createElement("a");
                                a.href = url;
                                a.download = downloadName;
                                document.body.appendChild(a);
                                a.click();
                                document.body.removeChild(a);
                                URL.revokeObjectURL(url);
                            } else {
                                console.error("HTTP error when saving WebP:", response.status);
                            }
                        } catch (e) {
                            console.error("Error saving WebP:", e);
                        }
                    }
                };

                const saveImageIndex = options.findIndex(opt => opt && (opt.content === "Save Image" || opt.content === "Save image"));
                if (saveImageIndex !== -1) {
                    options.splice(saveImageIndex + 1, 0, menuItem);
                } else {
                    options.push(menuItem);
                }
            }
        };
    }
});
