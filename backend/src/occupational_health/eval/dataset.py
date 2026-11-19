from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class GoldDocument(BaseModel):
    title: str
    standard_no: str | None = None
    page: int | None = Field(default=None, ge=1)
    content_hash: str | None = None


class EvalCase(BaseModel):
    id: str
    query: str
    query_type: str = "source"
    reference_answer: str = ""
    required_facts: list[str] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)
    gold_documents: list[GoldDocument] = Field(default_factory=list)
    expected_lifecycle: list[str] = Field(default_factory=list)
    expected_document_roles: list[str] = Field(default_factory=list)
    must_have_citation: bool = False
    expect_no_answer: bool = False
    allow_historical: bool = False
    notes: str = ""

    @field_validator("query")
    @classmethod
    def _query_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be empty")
        return value


def load_golden(path: str | Path) -> list[EvalCase]:
    """Load a JSONL golden dataset.

    Blank lines and lines starting with ``#`` are ignored, so comments are
    allowed in checked-in sample datasets.
    """
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"golden dataset not found: {source}")

    cases: list[EvalCase] = []
    seen: set[str] = set()
    for line_no, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON at {source}:{line_no}: {exc}") from exc
        case = EvalCase.model_validate(payload)
        if case.id in seen:
            raise ValueError(f"duplicate eval case id: {case.id}")
        seen.add(case.id)
        cases.append(case)
    if not cases:
        raise ValueError(f"golden dataset is empty: {source}")
    return cases
