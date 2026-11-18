from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local runtime prerequisites.")
    parser.add_argument("--models", type=Path, default=Path("var/models"))
    args = parser.parse_args()
    failures: list[str] = []
    if sys.version_info < (3, 11) or sys.version_info >= (3, 14):
        failures.append("Python must be >=3.11 and <3.14")
    for module in ("fastapi", "sqlalchemy", "celery", "qdrant_client", "fitz"):
        if importlib.util.find_spec(module) is None:
            failures.append(f"missing Python module: {module}")
    if not shutil.which("node"):
        failures.append("Node.js is not available")
    for directory in (Path("var/data"), args.models):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".write-test"
            probe.write_text("ok", encoding="ascii")
            probe.unlink()
        except OSError:
            failures.append(f"directory is not writable: {directory}")
    manifest = args.models / "manifest.json"
    if not manifest.is_file():
        failures.append(f"missing model manifest: {manifest}")
    else:
        try:
            json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failures.append("model manifest is not valid JSON")
    for variable in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        if os.environ.get(variable) != "1":
            failures.append(f"{variable}=1 is required")
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures), file=sys.stderr)
        return 1
    print("OK: local runtime prerequisites passed; service readiness is checked by /api/v1/health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
