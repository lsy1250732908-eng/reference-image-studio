import base64
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from app import Studio, validate_options
from pipeline import ComfyClient, caption_graph, combined_graph, compose_prompt, generation_graph


def sample_image():
    data = io.BytesIO()
    Image.new("RGB", (32, 32), (50, 120, 80)).save(data, "PNG")
    return data.getvalue()


class PipelineTests(unittest.TestCase):
    def test_combined_graph_routes_same_reference_and_caption(self):
        graph = combined_graph("test.png")
        self.assertEqual(graph["3"]["inputs"]["image"], graph["7"]["inputs"]["image"])
        self.assertEqual(graph["8"]["inputs"]["text"], ["3", 2])
        self.assertEqual(graph["11"]["inputs"]["model"], ["7", 0])

    def test_user_direction_has_priority(self):
        self.assertEqual(compose_prompt(" a blue coat ", "red coat"), "red coat, a blue coat")
        self.assertEqual(compose_prompt("cat", "  "), "cat")

    def test_generation_options_reach_sampler(self):
        graph = generation_graph("ref.png", "edited", seed=9, steps=12, weight=0.3)
        self.assertEqual(graph["8"]["inputs"]["text"], "edited")
        self.assertEqual(graph["11"]["inputs"]["seed"], 9)
        self.assertEqual(graph["7"]["inputs"]["weight"], 0.3)

    def test_invalid_options(self):
        for data in [{"width": 513}, {"seed": -1}, {"steps": 1.5}, {"weight": float("nan")},
                     {"weight": 9}, {"negative": []}, {"height": True}]:
            with self.subTest(data=data), self.assertRaises((ValueError, TypeError)):
                validate_options(data)

    def test_upload_normalizes_image_and_preserves_subfolder(self):
        client = ComfyClient()
        client.request = Mock(return_value=Mock(json=lambda: {"name": "a.png", "subfolder": "refs"}))
        self.assertEqual(client.upload(sample_image()), "refs/a.png")
        uploaded = client.request.call_args.kwargs["files"]["image"][1]
        with Image.open(io.BytesIO(uploaded)) as im:
            self.assertEqual(im.mode, "RGB")

    def test_execution_failure_is_reported(self):
        client = ComfyClient()
        client.request = Mock(side_effect=[Mock(json=lambda: {"prompt_id": "p"}),
                              Mock(json=lambda: {"p": {"status": {"status_str": "error",
                                                        "messages": ["out of memory"]}}})])
        with self.assertRaisesRegex(RuntimeError, "out of memory"):
            client.run(caption_graph("ref.png"))

    def test_timeout_does_not_claim_cancellation(self):
        client = ComfyClient()
        client.request = Mock(return_value=Mock(json=lambda: {"prompt_id": "p"}))
        with self.assertRaisesRegex(TimeoutError, "may still be queued/running"):
            client.run(caption_graph("ref.png"), timeout=0)

    def test_empty_caption_fails(self):
        client = ComfyClient()
        client.run = Mock(return_value={"outputs": {}})
        with self.assertRaisesRegex(RuntimeError, "empty caption"):
            client.caption("ref.png")

    def test_auto_pipeline_passes_caption_to_generation_and_saves_artifacts(self):
        client = Mock()
        client.preflight.return_value = ["v1-5-pruned-emaonly-fp16.safetensors"]
        client.upload.return_value = "uploaded.png"
        client.caption.return_value = "green tree"
        client.generate.return_value = (sample_image(), {"test": True})
        with tempfile.TemporaryDirectory() as tmp:
            studio = Studio(client, tmp)
            data = {"mode": "auto", "image": base64.b64encode(sample_image()).decode(),
                    "direction": "watercolor"}
            job_id = studio.start(data)
            deadline = time.monotonic() + 3
            while studio.busy and time.monotonic() < deadline:
                time.sleep(0.01)
            job = studio.jobs[job_id]
            self.assertEqual(job["status"], "done", job)
            self.assertEqual(client.generate.call_args.args, ("uploaded.png", "watercolor, green tree"))
            self.assertTrue((Path(tmp) / f"{job_id}.png").exists())
            meta = json.loads((Path(tmp) / f"{job_id}.json").read_text())
            self.assertEqual(meta["caption"], "green tree")

    def test_failed_job_releases_busy_slot(self):
        client = Mock()
        client.preflight.side_effect = RuntimeError("missing models")
        with tempfile.TemporaryDirectory() as tmp:
            studio = Studio(client, tmp)
            studio.jobs["test"] = {}
            studio.busy = True
            studio.execute("test", sample_image(), "auto", "", "", validate_options({}))
            self.assertFalse(studio.busy)
            self.assertEqual(studio.jobs["test"]["status"], "error")

    def test_parallel_jobs_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            studio = Studio(Mock(), tmp)
            studio.busy = True
            with self.assertRaisesRegex(RuntimeError, "already running"):
                studio.start({"image": base64.b64encode(sample_image()).decode()})


if __name__ == "__main__":
    unittest.main()
