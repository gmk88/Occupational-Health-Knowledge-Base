from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download offline models from ModelScope into D:/models."
    )
    parser.add_argument("--root", type=Path, default=Path("D:/models"))
    args = parser.parse_args()
    root = args.root
    root.mkdir(parents=True, exist_ok=True)
    qwen_dir = root / "Qwen3-Embedding-0.6B"
    if not (qwen_dir / "model.safetensors").is_file():
        subprocess.run(  # noqa: S603, S607
            [  # noqa: S607
                "modelscope",
                "download",
                "--model",
                "Qwen/Qwen3-Embedding-0.6B",
                "--local_dir",
                str(qwen_dir),
            ],
            check=True,
        )
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "ModelScope")
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(root / "paddlex"))
    from paddleocr import PPStructureV3

    pipeline = PPStructureV3()
    print("PP-StructureV3 models ready:", pipeline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
