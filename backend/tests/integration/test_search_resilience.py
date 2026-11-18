from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_degradation_requires_running_services():
    pytest.skip("requires Qdrant and embedding fault injection")
