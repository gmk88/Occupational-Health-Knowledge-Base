from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from occupational_health.eval.config import EvalConfig

_CORE_METRICS = (
    "required_fact_coverage",
    "numeric_exact_match",
    "standard_no_match",
    "citation_page_accuracy",
    "lifecycle_valid",
    "document_role_valid",
    "forbidden_fact_presence",
    "table_row_accuracy",
    "formula_completeness",
    "abstention_accuracy",
)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def summarize(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    summary: dict[str, float | None] = {}
    for metric in _CORE_METRICS:
        values = [
            float(row["metrics"][metric])
            for row in rows
            if isinstance(row.get("metrics", {}).get(metric), (int, float))
        ]
        summary[metric] = _average(values)
    return summary


def _markdown_table(
    headers: list[str], rows: list[list[str]], limit: int | None = None
) -> list[str]:
    shown = rows[:limit] if limit else rows
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in shown:
        cells = [str(cell).replace("|", "\\|").replace("\n", " ") for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_reports(
    rows: list[dict[str, Any]],
    ragas_result: dict[str, Any],
    config: EvalConfig,
) -> dict[str, str]:
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    json_path = output_dir / f"ragas_report_{stamp}.json"
    md_path = output_dir / f"ragas_report_{stamp}.md"
    csv_path = output_dir / f"ragas_details_{stamp}.csv"

    summary = summarize(rows)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": config.safe_dict(),
        "summary": summary,
        "ragas": ragas_result,
        "cases": rows,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# RAGAS 评估报告",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 检索模式：{config.mode}",
        f"- top_k：{config.top_k}",
        f"- Judge LLM：{config.llm_model if config.enable_llm else '未启用'}",
        f"- RAGAS 状态：{ragas_result.get('status')}",
        "",
        "## 总体指标",
        "",
    ]
    metric_rows = [
        [metric, "-" if summary.get(metric) is None else f"{summary[metric]:.4f}"]
        for metric in _CORE_METRICS
    ]
    lines.extend(_markdown_table(["指标", "平均分"], metric_rows))

    ragas_scores = ragas_result.get("scores") or {}
    if ragas_scores:
        lines.extend(["", "## RAGAS 指标", ""])
        lines.extend(
            _markdown_table(
                ["指标", "分数"],
                [[key, f"{value:.4f}"] for key, value in ragas_scores.items()],
            )
        )
    elif ragas_result.get("error"):
        lines.extend(["", f"> RAGAS 未运行：{ragas_result['error']}"])

    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        query_type = row["case"].get("query_type", "source")
        by_type.setdefault(query_type, []).append(row)

    lines.extend(["", "## 按问题类型", ""])
    type_rows: list[list[str]] = []
    for query_type, group in sorted(by_type.items()):
        values = [
            _average(
                [
                    float(row["metrics"][metric])
                    for row in group
                    if isinstance(row["metrics"].get(metric), (int, float))
                ]
            )
            for metric in ("required_fact_coverage", "citation_page_accuracy")
        ]
        type_rows.append(
            [
                query_type,
                str(len(group)),
                "-" if values[0] is None else f"{values[0]:.4f}",
                "-" if values[1] is None else f"{values[1]:.4f}",
            ]
        )
    lines.extend(
        _markdown_table(
            ["问题类型", "数量", "事实覆盖率", "页码准确率"], type_rows
        )
    )

    failures = []
    for row in rows:
        bad = [
            metric
            for metric in _CORE_METRICS
            if isinstance(row["metrics"].get(metric), (int, float))
            and row["metrics"][metric] < 1.0
            and metric not in {"context_text_coverage"}
        ]
        if bad:
            failures.append(
                [
                    row["case"]["id"],
                    row["case"]["query"],
                    ", ".join(bad),
                    row["answer"][:120],
                ]
            )

    lines.extend(["", "## 待改进样例", ""])
    if failures:
        lines.extend(
            _markdown_table(["ID", "问题", "低分指标", "答案预览"], failures, limit=30)
        )
    else:
        lines.append("无")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    fieldnames = [
        "id",
        "query",
        "query_type",
        "synthesis_method",
        "answer",
        "context_count",
        *_CORE_METRICS,
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            case = row["case"]
            item: dict[str, Any] = {
                "id": case.get("id"),
                "query": case.get("query"),
                "query_type": case.get("query_type"),
                "synthesis_method": row.get("synthesis_method"),
                "answer": row.get("answer"),
                "context_count": len(row.get("contexts") or []),
            }
            for metric in _CORE_METRICS:
                item[metric] = row["metrics"].get(metric)
            writer.writerow(item)

    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "csv": str(csv_path),
    }
