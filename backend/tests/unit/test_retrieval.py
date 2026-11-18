from __future__ import annotations

import pytest

from occupational_health.core.errors import ApiError
from occupational_health.services.retrieval.fusion import reciprocal_rank_fusion
from occupational_health.services.retrieval.highlights import find_highlights
from occupational_health.services.retrieval.terms import extract_exact_terms
from occupational_health.services.retrieval.validation import validate_query


def test_rrf_boosts_items_in_both_lists() -> None:
    fused = reciprocal_rank_fusion([["b"], ["b", "a"]], k=60)
    assert fused[0][0] == "b"
    assert fused[1][0] == "a"


def test_extract_exact_terms() -> None:
    terms = extract_exact_terms("CAS 71-43-2 和 PC-TWA 的接触限值 GBZ 2.1-2019")
    assert "CAS 71-43-2" in terms
    assert "PC-TWA" in terms
    assert any(term.startswith("GBZ") for term in terms)


def test_validation_rejects_empty_and_too_long() -> None:
    with pytest.raises(ApiError) as empty:
        validate_query("   ", 512, "hybrid", 10, 50)
    assert empty.value.code == "QUERY_EMPTY"
    with pytest.raises(ApiError) as long_query:
        validate_query("长" * 513, 512, "hybrid", 10, 50)
    assert long_query.value.code == "QUERY_TOO_LONG"
    with pytest.raises(ApiError) as symbols:
        validate_query("!!!", 512, "hybrid", 10, 50)
    assert symbols.value.code == "VALIDATION_ERROR"


def test_highlights_find_terms() -> None:
    highlights = find_highlights("喷漆岗位苯系物接触限值", ["苯系物"])
    assert highlights and highlights[0]["end_offset"] > highlights[0]["start_offset"]
