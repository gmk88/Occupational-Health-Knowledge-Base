from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_duplicate_and_partial_failure_and_cancel():
    pytest.skip("requires infrastructure")
