"""Local-only web UI. Run: python app.py --comfy-url http://127.0.0.1:8188"""
import argparse
import base64
import binascii
import json
import math
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import uuid

from pipeline import CHECKPOINT, NEGATIVE, ComfyClient, compose_prompt

ROOT = Path(__file__).resolve().parent


def validate_options(data):
    options = {}
    for key, default, low, high in [("seed", 42, 0, 2**32 - 1), ("steps", 20, 1, 100),
                                  ("width", 512, 256, 1024), ("height", 512, 256, 1024)]:
        value = data.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{key} must be an integer between {low} and {high}")
        if key in ("width", "height") and value % 8:
            raise ValueError(f"{key} must be a multiple of 8")
        options[key] = value
    weight = float(data.get("weight", 0.6))
    if not math.isfinite(weight) or not 0 <= weight <= 2:
        raise ValueError("weight must be between 0 and 2")
    options.update(weight=weight, checkpoint=data.get("checkpoint", CHECKPOINT),
                   negative=data.get("negative", NEGATIVE))
    for key in ("checkpoint", "negative"):
        if not isinstance(options[key], str) or len(options[key]) > 10000:
            raise ValueError(f"Invalid {key}")
    return options


class Studio:
    def __init__(self, client, output):
        self.client, self.output = client, Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.jobs = {}
        self.lock = threading.Lock()
        self.busy = False

    def start(self, data):
        mode = data.get("mode", "auto")
        if mode not in ("auto", "caption", "generate"):
            raise ValueError("Unknown mode")
        options = validate_options(data)
        prompt, direction = data.get("prompt", ""), data.get("direction", "")
        if any(not isinstance(v, str) or len(v) > 10000 for v in (prompt, direction)):
            raise ValueError("Invalid prompt")
        if mode == "generate" and not prompt.strip():
            raise ValueError("Enter a prompt first")
        encoded = data.get("image", "")
        if not isinstance(encoded, str):
            raise ValueError("Invalid image")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid image encoding") from exc
        if not raw or len(raw) > 15 * 1024 * 1024:
            raise ValueError("Choose an image smaller than 15 MB")
        with self.lock:
            if self.busy:
                raise RuntimeError("A job is already running; wait for it to finish")
            self.busy = True
            job_id = uuid.uuid4().hex
            # Keep bounded in-memory status; downloaded artifacts remain on disk.
            if len(self.jobs) >= 100:
                del self.jobs[next(iter(self.jobs))]
            self.jobs[job_id] = {"id": job_id, "status": "queued", "phase": "Checking models"}
        threading.Thread(target=self.execute, args=(job_id, raw, mode, prompt, direction, options),
                         daemon=True).start()
        return job_id

    def update(self, job_id, **values):
        with self.lock:
            self.jobs[job_id].update(values)

    def execute(self, job_id, raw, mode, prompt, direction, options):
        started = time.monotonic()
        try:
            self.update(job_id, status="running")
            checkpoints = self.client.preflight()
            if options["checkpoint"] not in checkpoints:
                raise ValueError("Selected checkpoint is not installed")
            image = self.client.upload(raw)
            submitted = lambda value: self.update(job_id, comfy_prompt_id=value)
            caption = ""
            if mode in ("caption", "auto"):
                self.update(job_id, phase="Florence2 · Generating caption")
                caption = self.client.caption(image, submitted=submitted)
                prompt = compose_prompt(caption, direction)
                self.update(job_id, caption=caption, prompt=prompt)
            if mode != "caption":
                self.update(job_id, phase="IP-Adapter · Generating image", prompt=prompt)
                result, graph = self.client.generate(image, prompt, submitted=submitted, **options)
                (self.output / f"{job_id}.png").write_bytes(result)
                metadata = {"caption": caption, "prompt": prompt, "options": options,
                            "workflow": graph, "seconds": round(time.monotonic() - started, 2)}
                (self.output / f"{job_id}.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
                self.update(job_id, image_url=f"/outputs/{job_id}.png", metadata_url=f"/outputs/{job_id}.json")
            self.update(job_id, status="done", phase="Completed", seconds=round(time.monotonic() - started, 2))
        except Exception as exc:
            self.update(job_id, status="error", phase="Failed", error=str(exc))
        finally:
            with self.lock:
                self.busy = False


class Handler(BaseHTTPRequestHandler):
    def send(self, status, content, mime="application/json"):
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def local_request(self):
        expected = f"127.0.0.1:{self.server.server_port}"
        alternate = f"localhost:{self.server.server_port}"
        if self.headers.get("Host") not in (expected, alternate):
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in ("http://" + expected, "http://" + alternate)

    def do_GET(self):
        if not self.local_request():
            return self.send(403, {"error": "Local access only"})
        path = urlsplit(self.path).path
        if path == "/":
            return self.send(200, (ROOT / "static/index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/health":
            try:
                checkpoints = self.server.studio.client.preflight()
                return self.send(200, {"ok": True, "checkpoints": checkpoints})
            except Exception as exc:
                return self.send(503, {"error": str(exc)})
        if path.startswith("/api/jobs/"):
            with self.server.studio.lock:
                job = dict(self.server.studio.jobs.get(path.rsplit("/", 1)[-1], {}))
            return self.send(200 if job else 404, job or {"error": "Job not found"})
        if path.startswith("/outputs/"):
            filename = path.removeprefix("/outputs/")
            stem, sep, ext = filename.partition(".")
            if sep and len(stem) == 32 and all(c in "0123456789abcdef" for c in stem) and ext in ("png", "json"):
                file = self.server.studio.output / filename
                if file.is_file():
                    return self.send(200, file.read_bytes(), "image/png" if ext == "png" else "application/json")
        self.send(404, {"error": "Not found"})

    def do_POST(self):
        if not self.local_request():
            return self.send(403, {"error": "Local access only"})
        if self.path != "/api/jobs":
            return self.send(404, {"error": "Not found"})
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.send(415, {"error": "Use application/json"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 21 * 1024 * 1024:
                return self.send(413, {"error": "Request too large or empty"})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            job_id = self.server.studio.start(data)
            self.send(202, {"id": job_id})
        except (ValueError, TypeError) as exc:
            self.send(400, {"error": str(exc)})
        except RuntimeError as exc:
            self.send(409, {"error": str(exc)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.studio = Studio(ComfyClient(args.comfy_url), args.output)
    print(f"Reference Studio: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
