# Reference Studio

[中文说明](README.md)

Upload a reference image → generate an English caption with Florence2 → generate an image with IP-Adapter PLUS + SD 1.5. Includes a local browser interface, editable prompts, PNG/JSON export, and standalone ComfyUI workflows.

| Reference | Generated |
| --- | --- |
| ![Reference](examples/reference.png) | ![Generated](examples/generated.png) |

## Setup

Requires Python 3.10+ and a running ComfyUI installation with:

- [ComfyUI-Florence2](https://github.com/kijai/ComfyUI-Florence2), including its Python requirements in ComfyUI's environment.
- [ComfyUI_IPAdapter_plus](https://github.com/cubiq/ComfyUI_IPAdapter_plus).
- SD 1.5 checkpoint, IP-Adapter PLUS SD15, CLIP Vision ViT-H, and Florence-2-base files at the paths in [models.json](models.json).

See the [Chinese guide](README.md) for exact tested upstream commits and model paths.

```bash
git clone https://github.com/lsy1250732908-eng/reference-image-studio.git
cd reference-image-studio
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/download_models.py --comfy-dir /path/to/ComfyUI
```

The optional downloader fetches about 4 GB and verifies SHA-256 hashes. It skips verified existing files. It does not install ComfyUI or nodes. Review each upstream model license before use. Restart ComfyUI after installation; on Apple Silicon the tested launch includes `--fp32-vae`.

```bash
python app.py --comfy-url http://127.0.0.1:8188
```

Open http://127.0.0.1:7860. The interface is Chinese: the primary button runs the full pipeline; the lower buttons caption only or generate with the editable prompt. Settings control seed, steps, image dimensions and reference strength. Output PNG and parameter/workflow JSON files are saved to `outputs/` and offered as downloads. Only one job runs at a time. Refreshing restores the active job; restarting the server clears in-memory job history.

The UI listens on loopback only and has no login system. It is intended for local use. If you configure a remote ComfyUI URL, images and prompts are sent to that server. Model loading can take several minutes. Transient status-query timeouts are retried without resubmitting the generation job. The client waits up to 30 minutes; timeout or closing the UI does not cancel the ComfyUI job.

## Prompt behavior

Florence2 supplies a descriptive caption, not a recovered original prompt. Optional creative direction is prepended to that caption without an LLM rewrite. Edit contradictory descriptions manually before generating. IP-Adapter guides content/style but does not guarantee identity, exact composition, or faithful text edits. Lower reference strength to give text more influence. Only SD 1.5 checkpoints are supported by the supplied adapter setup.

## Workflows and tests

Drag `workflows/reference-studio.json` into ComfyUI for a single connected caption-to-generation graph. `workflows/reference-studio-api.json` is the HTTP API version. The browser app uses two submissions so the caption can be displayed/edited first.

```bash
python -m unittest discover -s tests -v
# Requires the app and ComfyUI running, with real models:
python scripts/smoke_test.py examples/reference.png --output outputs/smoke
```

The full real-model pipeline took **365.27 seconds** for 512×512 / 20 steps / seed 73 / weight 0.55.

Real inference was tested on Apple M5 / 16 GB / macOS, Python 3.12.15, PyTorch 2.15.0 and ComfyUI 0.45.0. See [test-report.json](examples/test-report.json). Windows/Linux/NVIDIA inference has not been tested. CI uses mocked backend responses to test client behavior, not GPU inference. The example reference is an SD 1.5-generated fictional portrait.

## License

Original client code is MIT licensed. ComfyUI, its third-party nodes, and all model weights remain separately licensed by their respective authors. They are downloaded/installed separately and are not included here. Credits: Microsoft Florence2, kijai, Tencent IP-Adapter, cubiq, and ComfyUI contributors.
