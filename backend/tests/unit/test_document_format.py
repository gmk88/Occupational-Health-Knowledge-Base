from pathlib import Path

from occupational_health.services.extraction.document_loader import (
    document_format,
    load_pages,
)


def test_legacy_text_file_stored_with_pdf_suffix(tmp_path: Path) -> None:
    path = tmp_path / "legacy.pdf"
    content = "# 标题\n\n" + "职业健康正文内容" * 100
    path.write_text(content, encoding="utf-8")
    assert document_format(path) == "text"
    assert load_pages(path) == [content]


def test_real_pdf_is_detected_by_magic_bytes(tmp_path: Path) -> None:
    path = tmp_path / "document.md"
    path.write_bytes(b"%PDF-1.7\n%not-a-real-pdf")
    assert document_format(path) == "pdf"
