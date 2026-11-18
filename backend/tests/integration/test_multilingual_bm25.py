from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_multilingual_bm25_quality_gate():
    pytest.skip("requires Qdrant 1.20+ and labeled Chinese corpus")
