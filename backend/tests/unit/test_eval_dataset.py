from pathlib import Path

import pytest

from occupational_health.eval.dataset import load_golden


def test_load_sample_golden_dataset() -> None:
    path = Path(__file__).resolve().parents[2] / "eval/golden/ragas_cases.sample.jsonl"
    cases = load_golden(path)
    assert len(cases) >= 5
    assert cases[0].id == "limit-benzene-001"
    assert "PC-TWA" in cases[0].required_facts
    assert any(case.expect_no_answer for case in cases)


def test_load_golden_rejects_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_golden("/definitely/missing/ragas.jsonl")
