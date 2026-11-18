from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_entry(root: Path, name: str, entry: dict, errors: list[str]) -> None:
    directory = root / entry["path"]
    if not directory.is_dir():
        errors.append(f"{name}: missing directory {directory}")
        return
    revision = entry.get("revision", "")
    if not revision:
        errors.append(f"{name}: revision must not be empty")
    elif name == "qwen" and len(revision) != 40:
        print(
            f"WARN: {name} revision '{revision}' is not a pinned commit hash",
            file=sys.stderr,
        )
    for relative, expected in entry.get("files", {}).items():
        path = directory / relative
        if not path.is_file():
            errors.append(f"{name}: missing file {relative}")
        elif sha256(path) != expected.lower():
            errors.append(f"{name}: SHA-256 mismatch for {relative}")


def probe_qwen(root: Path, entry: dict) -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(str(root / entry["path"]), local_files_only=True)
    vector = model.encode(["职业健康"], normalize_embeddings=True)[0]
    if len(vector) != 1024:
        raise RuntimeError(f"Expected 1024 dimensions, got {len(vector)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify offline model assets.")
    parser.add_argument("--root", type=Path, default=Path("var/models"))
    parser.add_argument(
        "--probe", action="store_true", help="Run a local Qwen embedding probe"
    )
    args = parser.parse_args()
    manifest_path = args.root / "manifest.json"
    if not manifest_path.is_file():
        print(f"FAIL: missing {manifest_path}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for name in ("qwen", "paddleocr"):
        entry = manifest.get(name)
        if not isinstance(entry, dict):
            errors.append(f"{name}: missing manifest entry")
        else:
            verify_entry(args.root, name, entry, errors)
    if errors:
        print("\n".join(f"FAIL: {error}" for error in errors), file=sys.stderr)
        return 1
    if args.probe:
        try:
            probe_qwen(args.root, manifest["qwen"])
        except Exception as exc:
            print(f"FAIL: offline Qwen probe: {exc}", file=sys.stderr)
            return 1
    print(
        "OK: model files, immutable revisions and checksums verified; no downloads attempted"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
