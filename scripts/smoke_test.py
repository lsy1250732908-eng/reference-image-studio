"""Real end-to-end test against a running Studio + ComfyUI. No mocked models."""
import argparse
import base64
import io
import json
from pathlib import Path
import time

from PIL import Image, ImageStat
import requests

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("image", type=Path)
parser.add_argument("--url", default="http://127.0.0.1:7860")
parser.add_argument("--output", type=Path, default=Path("examples"))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
health = requests.get(args.url + "/api/health", timeout=60)
health.raise_for_status()
response = requests.post(args.url + "/api/jobs", json={
    "mode": "auto", "image": base64.b64encode(args.image.read_bytes()).decode(),
    "direction": "watercolor illustration, soft natural light", "seed": 73, "steps": 20,
    "weight": 0.55, "width": 512, "height": 512,
}, timeout=30)
response.raise_for_status()
job_id = response.json()["id"]
print("Job:", job_id, flush=True)
deadline = time.monotonic() + 1800
previous = ""
while time.monotonic() < deadline:
    response = requests.get(args.url + "/api/jobs/" + job_id, timeout=30)
    response.raise_for_status()
    job = response.json()
    if job["phase"] != previous:
        print(job["phase"], flush=True)
        previous = job["phase"]
    if job["status"] == "error":
        raise RuntimeError(job["error"])
    if job["status"] == "done":
        break
    time.sleep(2)
else:
    raise TimeoutError("End-to-end test exceeded 30 minutes")
assert job.get("caption"), "Florence2 caption is empty"
assert job["caption"] in job["prompt"], "Caption missing from final prompt"
image_response = requests.get(args.url + job["image_url"], timeout=30)
image_response.raise_for_status()
with Image.open(io.BytesIO(image_response.content)) as image:
    image = image.convert("RGB")
    assert image.size == (512, 512), image.size
    assert max(ImageStat.Stat(image).stddev) > 5, "Output is near-constant"
    image.save(args.output / "generated.png")  # Public example has no embedded private metadata.
with Image.open(args.image) as reference:
    reference.convert("RGB").save(args.output / "reference.png")
meta_response = requests.get(args.url + job["metadata_url"], timeout=30)
meta_response.raise_for_status()
metadata = meta_response.json()
assert metadata["workflow"]["8"]["inputs"]["text"] == job["prompt"]
assert metadata["workflow"]["7"]["inputs"]["image"] == ["1", 0]
report = {"status": "passed", "test": "real HTTP upload → Florence2 → prompt → IP-Adapter → PNG",
          "caption": job["caption"], "prompt": job["prompt"], "seconds": job["seconds"],
          "image_size": [512, 512], "options": metadata["options"]}
(args.output / "test-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
