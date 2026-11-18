from __future__ import annotations

import argparse
import sys
import time

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the public API.")
    parser.add_argument("--base", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    headers = {"Authorization": f"Bearer {args.token}"}
    started = time.perf_counter()
    try:
        health = httpx.get(f"{args.base}/health")
        print(f"health: {health.status_code}")
        limits = httpx.get(f"{args.base}/system/limits", headers=headers)
        print(f"limits: {limits.status_code}")
        print(f"smoke test passed in {round(time.perf_counter() - started, 1)}s")
        return 0
    except httpx.HTTPError as exc:
        print(f"smoke test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
