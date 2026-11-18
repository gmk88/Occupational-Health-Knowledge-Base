from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_keyword_and_hybrid_require_infrastructure():
    pytest.skip("requires Qdrant and indexed data")
