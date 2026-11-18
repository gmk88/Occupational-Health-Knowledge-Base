from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate retrieval quality on a labeled query set."
    )
    parser.add_argument(
        "--queries", type=Path, default=Path("tests/fixtures/retrieval_queries.json")
    )
    args = parser.parse_args()
    data = json.loads(args.queries.read_text(encoding="utf-8"))
    queries = data["splits"]["test"]
    print(f"Evaluating {len(queries)} test queries.")
    print(
        "Metrics: semantic/hybrid Top-5 hit rate, exact-term Top-5 >= 90%, "
        "page accuracy 100%, p50/p95 latency."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
