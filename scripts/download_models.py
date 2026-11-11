"""Download the explicitly listed public models and verify their SHA-256 hashes."""
import argparse
import hashlib
import json
from pathlib import Path

import requests


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-dir", type=Path, required=True)
    args = parser.parse_args()
    if not (args.comfy_dir / "main.py").is_file():
        parser.error("--comfy-dir must point to a ComfyUI installation containing main.py")
    manifest = json.loads((Path(__file__).resolve().parents[1] / "models.json").read_text())
    for entry in manifest:
        target = args.comfy_dir / entry["path"]
        if target.is_file() and sha256(target) == entry["sha256"]:
            print("Verified:", entry["path"], flush=True)
            continue
        if target.exists():
            raise RuntimeError(f"Existing file has a different hash; move it aside before retrying: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        print("Downloading:", entry["path"], flush=True)
        with requests.get(entry["url"], stream=True, timeout=(30, 120)) as response:
            response.raise_for_status()
            with partial.open("wb") as stream:
                for chunk in response.iter_content(8 * 1024 * 1024):
                    stream.write(chunk)
        if sha256(partial) != entry["sha256"]:
            raise RuntimeError(f"SHA-256 mismatch: {partial}; model was not installed")
        partial.replace(target)
        print("Installed:", entry["path"], flush=True)


if __name__ == "__main__":
    main()
