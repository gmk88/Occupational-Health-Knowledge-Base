from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_quickstart_scenarios_require_full_infrastructure():
    pytest.skip("requires PostgreSQL, Qdrant, embedding and model assets")
