from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure pipeline success rate and latency."
    )
    parser.add_argument(
        "--results", type=Path, default=Path("tests/performance/results.json")
    )
    args = parser.parse_args()
    if args.results.is_file():
        data = json.loads(args.results.read_text(encoding="utf-8"))
        print(data)
    else:
        print(
            "No results file; run the live harness to produce tests/performance/results.json"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
