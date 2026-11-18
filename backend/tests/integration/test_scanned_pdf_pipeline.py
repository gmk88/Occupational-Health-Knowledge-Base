from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_scanned_and_mixed_pages_are_routed_correctly():
    pytest.skip("requires infrastructure and model assets")
