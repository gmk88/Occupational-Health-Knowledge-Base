from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import fitz  # PyMuPDF

from occupational_health.core.errors import ApiError

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}

SUPPORTED_MEDIA_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
]

# Non-paginated formats (TXT/MD/DOCX) are split into pseudo-pages of this many
# characters so the rest of the pipeline can treat every document uniformly.
_TEXT_PAGE_CHARS = 3000


def document_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ApiError(400, "UNSUPPORTED_TYPE", "不支持的文件类型")
    with path.open("rb") as stream:
        head = stream.read(4096)
    if head.startswith(b"%PDF-"):
        return "pdf"
    if suffix == ".docx" or head.startswith(b"PK\x03\x04"):
        return "docx"
    if suffix in {".txt", ".md", ".markdown"}:
        return "text"
    # 兼容旧数据：早期上传把 TXT/MD 也存成了 .pdf 后缀，按纯文本回退解析。
    # 只检查二进制特征，不能在截断样本上做严格 UTF-8 解码（可能切断多字节字符）。
    if b"\x00" in head:
        raise ApiError(400, "DOCUMENT_INVALID", "PDF 文件已损坏或不受支持")
    return "text"


@lru_cache(maxsize=64)
def load_pages(path: Path) -> list[str]:
    """Return the raw text of every (pseudo-)page of a document."""
    fmt = document_format(path)
    if fmt == "pdf":
        return _load_pdf_pages(path)
    if fmt == "docx":
        return _load_docx_pages(path)
    return _load_text_pages(path)


def extract_page_text(path: Path, page_number: int, min_chars: int) -> tuple[str, int]:
    """Return raw text and effective character count for one page.

    ``min_chars`` is accepted for interface compatibility; callers compare the
    returned effective count against it themselves.
    """
    del min_chars
    pages = load_pages(path)
    raw = pages[page_number - 1] if 1 <= page_number <= len(pages) else ""
    effective = len([ch for ch in raw if not ch.isspace()])
    return raw, effective


def _load_pdf_pages(path: Path) -> list[str]:
    document = fitz.open(path)
    try:
        if document.needs_pass:
            raise ApiError(400, "PDF_ENCRYPTED", "文档已加密，无法解析")
        return [document[i].get_text("text") or "" for i in range(document.page_count)]
    finally:
        document.close()


def _load_docx_pages(path: Path) -> list[str]:
    try:
        from docx import Document
    except ImportError as exc:
        raise ApiError(503, "MODEL_UNAVAILABLE", "Word 解析依赖未安装") from exc
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(str(path))
    parts: list[str] = []
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            text = Paragraph(child, document).text.strip()
            if text:
                parts.append(text)
        elif child.tag == qn("w:tbl"):
            table = Table(child, document)
            rows = [
                "| " + " | ".join(" ".join(cell.text.split()) for cell in row.cells) + " |"
                for row in table.rows
            ]
            if not rows:
                continue
            column_count = len(table.rows[0].cells)
            parts.append(rows[0])
            parts.append("| " + " | ".join(["---"] * column_count) + " |")
            parts.extend(rows[1:])
    return _chunk_text("\n".join(parts))


def _load_text_pages(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return _chunk_text(text)


def _chunk_text(text: str) -> list[str]:
    if not text.strip():
        return []
    return [
        text[start : start + _TEXT_PAGE_CHARS]
        for start in range(0, len(text), _TEXT_PAGE_CHARS)
    ]
