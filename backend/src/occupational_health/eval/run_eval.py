from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from occupational_health.eval.config import EvalConfig
from occupational_health.eval.custom_metrics import evaluate_custom
from occupational_health.eval.dataset import load_golden
from occupational_health.eval.ragas_adapter import run_ragas
from occupational_health.eval.report import summarize, write_reports
from occupational_health.eval.retrieve import RetrievalRunner
from occupational_health.eval.synthesize import synthesize_answer


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run RAGAS and domain evaluation")
    parser.add_argument("--golden", type=Path, help="JSONL golden dataset")
    parser.add_argument("--mode", choices=["hybrid", "semantic", "keyword"])
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--llm", dest="enable_llm", action="store_true")
    parser.add_argument("--no-llm", dest="enable_llm", action="store_false")
    parser.set_defaults(enable_llm=None)
    return parser


def _ragas_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        case = row["case"]
        ground_truth = case.get("reference_answer") or ""
        if not ground_truth and case.get("expect_no_answer"):
            ground_truth = "未在知识库中找到相关信息。"
        result.append(
            {
                "question": case["query"],
                "contexts": row["contexts"],
                "answer": row["answer"],
                "ground_truth": ground_truth,
            }
        )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config = EvalConfig.from_env()

    if args.golden:
        config.golden_path = args.golden
    if args.mode:
        config.mode = args.mode
    if args.top_k:
        config.top_k = args.top_k
    if args.output_dir:
        config.output_dir = args.output_dir
    if args.enable_llm is not None:
        config.enable_llm = args.enable_llm

    cases = load_golden(config.golden_path)
    rows: list[dict[str, Any]] = []

    with RetrievalRunner(config) as runner:
        for case in cases:
            contexts = runner.retrieve(case)
            synthesis = synthesize_answer(case, contexts, config)
            metrics = evaluate_custom(case, contexts, synthesis.answer)
            rows.append(
                {
                    "case": case.model_dump(),
                    "contexts": [context.text for context in contexts],
                    "contexts_metadata": [context.metadata for context in contexts],
                    "answer": synthesis.answer,
                    "synthesis_method": synthesis.method,
                    "synthesis_error": synthesis.error,
                    "metrics": metrics,
                }
            )

    ragas_result = run_ragas(_ragas_rows(rows), config)
    paths = write_reports(rows, ragas_result, config)

    output = {
        "cases": len(cases),
        "summary": summarize(rows),
        "ragas": ragas_result,
        "reports": paths,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
