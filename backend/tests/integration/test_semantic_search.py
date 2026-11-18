from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_semantic_search_requires_infrastructure():
    pytest.skip("requires Qdrant, embedding and indexed data")
