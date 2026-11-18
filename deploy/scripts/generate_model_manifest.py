from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate model manifest with SHA-256 checksums."
    )
    parser.add_argument("--root", type=Path, default=Path("D:/models"))
    args = parser.parse_args()
    root = args.root
    qwen_dir = root / "Qwen3-Embedding-0.6B"
    qwen_files = [
        "model.safetensors",
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
    ]
    manifest = {
        "qwen": {
            "path": "Qwen3-Embedding-0.6B",
            "revision": "master",
            "files": {
                name: sha256(qwen_dir / name)
                for name in qwen_files
                if (qwen_dir / name).is_file()
            },
        },
        "paddleocr": {
            "path": "paddlex",
            "revision": "ModelScope",
            "files": {},
        },
    }
    target = root / "manifest.json"
    target.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"manifest written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
