"""Florence2 captioning and IP-Adapter generation over the ComfyUI HTTP API."""
import io
import time
import uuid

import requests
from PIL import Image, ImageOps

CHECKPOINT = "v1-5-pruned-emaonly-fp16.safetensors"
NEGATIVE = "blurry, low quality, deformed face, extra limbs, text, watermark"


def node(kind, **inputs):
    return {"class_type": kind, "inputs": inputs}


def caption_graph(image):
    return {
        "1": node("LoadImage", image=image),
        "2": node("Florence2ModelLoader", model="Florence-2-base", precision="fp32",
                  convert_to_safetensors=False),
        "3": node("Florence2Run", image=["1", 0], florence2_model=["2", 0],
                  text_input="", task="more_detailed_caption", fill_mask=True,
                  keep_model_loaded=False, max_new_tokens=128, num_beams=1,
                  do_sample=False, output_mask_select="", seed=1),
        "4": node("PreviewAny", source=["3", 2]),
    }


def generation_graph(image, prompt, *, checkpoint=CHECKPOINT, negative=NEGATIVE,
                     seed=42, steps=20, weight=0.6, width=512, height=512):
    return {
        "1": node("LoadImage", image=image),
        "5": node("CheckpointLoaderSimple", ckpt_name=checkpoint),
        "6": node("IPAdapterUnifiedLoader", model=["5", 0], preset="PLUS (high strength)"),
        "7": node("IPAdapter", model=["6", 0], ipadapter=["6", 1], image=["1", 0],
                  weight=weight, start_at=0.0, end_at=1.0, weight_type="standard"),
        "8": node("CLIPTextEncode", clip=["5", 1], text=prompt),
        "9": node("CLIPTextEncode", clip=["5", 1], text=negative),
        "10": node("EmptyLatentImage", width=width, height=height, batch_size=1),
        "11": node("KSampler", model=["7", 0], positive=["8", 0], negative=["9", 0],
                   latent_image=["10", 0], seed=seed, steps=steps, cfg=7.0,
                   sampler_name="euler", scheduler="normal", denoise=1.0),
        "12": node("VAEDecode", samples=["11", 0], vae=["5", 2]),
        "13": node("SaveImage", images=["12", 0], filename_prefix="ReferenceStudio"),
    }


def combined_graph(image="reference.png"):
    graph = caption_graph(image)
    graph.update(generation_graph(image, ["3", 2]))
    return graph


def compose_prompt(caption, direction=""):
    # Put the user's requested change first; this is caption composition, not an LLM rewrite.
    return ", ".join(part.strip() for part in (direction, caption) if part.strip())


class ComfyClient:
    def __init__(self, url="http://127.0.0.1:8188"):
        self.url = url.rstrip("/")

    def request(self, method, path, **kwargs):
        response = requests.request(method, self.url + path, timeout=30, **kwargs)
        if not response.ok:
            raise RuntimeError(f"ComfyUI {response.status_code}: {response.text[:2000]}")
        return response

    def preflight(self):
        info = self.request("GET", "/object_info").json()
        required = {v["class_type"] for v in combined_graph().values()}
        missing = sorted(required - info.keys())
        if missing:
            raise RuntimeError("Missing ComfyUI nodes: " + ", ".join(missing))
        models = info["Florence2ModelLoader"]["input"]["required"]["model"][0]
        if "Florence-2-base" not in models:
            raise RuntimeError("Install Florence-2-base in ComfyUI/models/LLM/Florence-2-base")
        checkpoints = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        if not checkpoints:
            raise RuntimeError("Install an SD 1.5 checkpoint in ComfyUI/models/checkpoints")
        adapters = self.request("GET", "/models/ipadapter").json()
        vision = self.request("GET", "/models/clip_vision").json()
        if not any("ip-adapter-plus_sd15" in name for name in adapters):
            raise RuntimeError("Missing ip-adapter-plus_sd15.safetensors")
        if not any("vit-h" in name.lower() for name in vision):
            raise RuntimeError("Missing CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors")
        return checkpoints

    def upload(self, raw):
        with Image.open(io.BytesIO(raw)) as source:
            if source.width * source.height > 25_000_000:
                raise ValueError("Image exceeds 25 megapixels")
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((2048, 2048))
            data = io.BytesIO()
            image.save(data, format="PNG")
        name = f"reference-studio-{uuid.uuid4().hex}.png"
        result = self.request("POST", "/upload/image",
                              files={"image": (name, data.getvalue(), "image/png")},
                              data={"overwrite": "false", "type": "input"}).json()
        return "/".join(filter(None, [result.get("subfolder"), result["name"]]))

    def run(self, graph, timeout=1800, submitted=None):
        result = self.request("POST", "/prompt", json={"prompt": graph}).json()
        if result.get("node_errors") or not result.get("prompt_id"):
            raise RuntimeError(f"Workflow rejected: {result}")
        prompt_id = result["prompt_id"]
        if submitted:
            submitted(prompt_id)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            history = self.request("GET", f"/history/{prompt_id}").json().get(prompt_id)
            if history:
                status = history.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI execution failed: {status.get('messages')}")
                if status.get("completed"):
                    return history
            time.sleep(1)
        raise TimeoutError(f"Timed out waiting for {prompt_id}; it may still be queued/running in ComfyUI.")

    def caption(self, image, submitted=None):
        history = self.run(caption_graph(image), submitted=submitted)
        caption = " ".join(history.get("outputs", {}).get("4", {}).get("text", [])).strip()
        if not caption:
            raise RuntimeError("Florence2 returned an empty caption")
        return caption

    def generate(self, image, prompt, submitted=None, **options):
        graph = generation_graph(image, prompt, **options)
        history = self.run(graph, submitted=submitted)
        images = history.get("outputs", {}).get("13", {}).get("images", [])
        if not images:
            raise RuntimeError("ComfyUI returned no output image")
        item = images[0]
        raw = self.request("GET", "/view", params={k: item[k] for k in
                           ("filename", "subfolder", "type")}).content
        with Image.open(io.BytesIO(raw)) as result:
            result.verify()
        return raw, graph
