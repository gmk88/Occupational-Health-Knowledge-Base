from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from occupational_health.eval.dataset import EvalCase
from occupational_health.eval.retrieve import RetrievedContext

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_PUNCT = re.compile(r"[\s\W_]+", re.UNICODE)
_ABSTAIN_MARKERS = (
    "未找到",
    "没有找到",
    "未在",
    "未检索到",
    "知识库中未",
    "无法回答",
    "not found",
    "no information",
)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return _PUNCT.sub("", normalized)


def contains_fact(text: str | None, fact: str) -> bool:
    needle = normalize_text(fact)
    if not needle:
        return False
    return needle in normalize_text(text)


def numeric_tokens(value: str) -> set[str]:
    return {token.replace(",", ".") for token in _NUMBER.findall(value or "")}


def _context_texts(contexts: Iterable[RetrievedContext]) -> list[str]:
    return [context.text for context in contexts]


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def evaluate_custom(
    case: EvalCase,
    contexts: list[RetrievedContext],
    answer: str,
) -> dict[str, float | None]:
    """Compute deterministic domain metrics that RAGAS does not cover."""
    texts = _context_texts(contexts)
    combined_context = "\n".join(texts)
    metrics: dict[str, float | None] = {}

    required = case.required_facts
    if required:
        hits = sum(any(contains_fact(text, fact) for text in texts) for fact in required)
        metrics["required_fact_coverage"] = round(hits / len(required), 4)
    else:
        metrics["required_fact_coverage"] = None

    expected_numbers: set[str] = set()
    for fact in required:
        expected_numbers.update(numeric_tokens(fact))
    if expected_numbers and answer:
        answer_numbers = numeric_tokens(answer)
        metrics["numeric_exact_match"] = round(
            len(expected_numbers & answer_numbers) / len(expected_numbers), 4
        )
    else:
        metrics["numeric_exact_match"] = None

    expected_standards = [
        document.standard_no for document in case.gold_documents if document.standard_no
    ]
    if expected_standards:
        metadata_standards = [
            str(context.metadata.get("standard_no") or "") for context in contexts
        ]
        metrics["standard_no_match"] = round(
            sum(
                any(contains_fact(value, standard) for value in metadata_standards)
                for standard in expected_standards
            )
            / len(expected_standards),
            4,
        )
    else:
        metrics["standard_no_match"] = None

    expected_pages = [
        document.page for document in case.gold_documents if document.page is not None
    ]
    if expected_pages:
        page_hits = []
        for expected in expected_pages:
            hit = False
            for context in contexts:
                start = context.metadata.get("page_start")
                end = context.metadata.get("page_end")
                if start is None or end is None:
                    continue
                if int(start) <= expected <= int(end):
                    hit = True
                    break
            page_hits.append(1.0 if hit else 0.0)
        metrics["citation_page_accuracy"] = round(sum(page_hits) / len(page_hits), 4)
        metrics["gold_page_recall"] = metrics["citation_page_accuracy"]
    else:
        metrics["citation_page_accuracy"] = None
        metrics["gold_page_recall"] = None

    bad_statuses = {"replaced", "abolished", "superseded"}
    if case.expect_no_answer or case.allow_historical:
        metrics["lifecycle_valid"] = None
    else:
        bad = [
            context
            for context in contexts
            if str(context.metadata.get("lifecycle_status") or "") in bad_statuses
        ]
        valid = 1.0 if not bad else 0.0
        if case.expected_lifecycle:
            wanted = {str(value) for value in case.expected_lifecycle}
            seen = {
                str(context.metadata.get("lifecycle_status") or "")
                for context in contexts
            }
            valid *= 1.0 if wanted & seen else 0.0
        metrics["lifecycle_valid"] = valid

    if case.expected_document_roles:
        wanted_roles = {str(value) for value in case.expected_document_roles}
        seen_roles = {
            str(context.metadata.get("document_role") or "") for context in contexts
        }
        metrics["document_role_valid"] = round(
            len(wanted_roles & seen_roles) / len(wanted_roles), 4
        )
    else:
        metrics["document_role_valid"] = None

    if case.forbidden_facts and answer:
        leaked = [fact for fact in case.forbidden_facts if contains_fact(answer, fact)]
        metrics["forbidden_fact_presence"] = 0.0 if leaked else 1.0
        metrics["forbidden_facts"] = leaked  # type: ignore[assignment]
    else:
        metrics["forbidden_fact_presence"] = None

    if case.query_type == "table_row":
        hits = [any(contains_fact(text, fact) for text in texts) for fact in required]
        metrics["table_row_accuracy"] = (
            round(sum(hits) / len(hits), 4) if hits else None
        )
    else:
        metrics["table_row_accuracy"] = None

    if case.query_type == "formula":
        hits = [any(contains_fact(text, fact) for text in texts) for fact in required]
        metrics["formula_completeness"] = (
            round(sum(hits) / len(hits), 4) if hits else None
        )
    else:
        metrics["formula_completeness"] = None

    if answer:
        abstained = any(marker in answer.lower() for marker in _ABSTAIN_MARKERS)
        if case.expect_no_answer:
            metrics["abstention_accuracy"] = 1.0 if abstained else 0.0
        else:
            metrics["abstention_accuracy"] = 0.0 if abstained else 1.0
    else:
        metrics["abstention_accuracy"] = None

    metrics["context_text_coverage"] = (
        round(len(combined_context.strip()) / 10000, 4)
        if combined_context.strip()
        else 0.0
    )
    return metrics
