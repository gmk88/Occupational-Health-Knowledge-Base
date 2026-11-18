from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_text_pdf_does_not_run_ocr_and_points_are_idempotent():
    # 需要运行中的 PostgreSQL/Qdrant/embedding 与测试 PDF 资产。
    pytest.skip("requires infrastructure and model assets")
