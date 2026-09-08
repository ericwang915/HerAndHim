# ComfyUI identity workflows

API-format ComfyUI graphs that keep the companion's face consistent locally,
without sending the reference portrait to any cloud service. Selected with
`skills.comfyui.identityWorkflow` (or `HERANDHIM_COMFYUI_IDENTITY_WORKFLOW`):

| Value | Graph | Custom nodes required | Models expected |
|-------|-------|-----------------------|-----------------|
| `flux-pulid` | `flux_pulid.json` | [ComfyUI-PuLID-Flux](https://github.com/balazik/ComfyUI-PuLID-Flux) (`PulidFluxModelLoader`, `ApplyPulidFlux`, …) | `unet/flux1-dev.safetensors`, `clip/t5xxl_fp8_e4m3fn.safetensors`, `clip/clip_l.safetensors`, `vae/ae.safetensors`, `pulid/pulid_flux_v0.9.1.safetensors`, EVA-CLIP + InsightFace (auto-downloaded by the node pack) |
| `sdxl-instantid` | `sdxl_instantid.json` | [ComfyUI_InstantID](https://github.com/cubiq/ComfyUI_InstantID) (`InstantIDModelLoader`, `ApplyInstantID`, …) | your SDXL checkpoint (`skills.comfyui.checkpoint`), `instantid/ip-adapter.bin`, `controlnet/instantid/diffusion_pytorch_model.safetensors`, InsightFace `antelopev2` |
| any file path | your own exported API-format graph | whatever it uses | whatever it uses |

Placeholders substituted at run time: `%prompt%`, `%negative%`, `%model%`,
`%width%`, `%height%`, `%seed%`, and `%reference%` (the uploaded face
reference's server-side filename).

Skip-if-missing: before submitting, HerAndHim asks the server (`/object_info`)
whether every `class_type` in the graph exists. If any identity node is
missing, it logs a warning and falls back to the plain text-to-image workflow
— generation never fails just because the node pack isn't installed. Missing
*model files* are reported by ComfyUI itself when the job is submitted.

If your model filenames differ from the pinned ones above, copy the bundled
graph, edit the loader inputs, and point `identityWorkflow` at your copy.
