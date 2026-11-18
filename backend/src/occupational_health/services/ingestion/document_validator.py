from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from occupational_health.core.errors import ApiError
from occupational_health.services.extraction.document_loader import (
    SUPPORTED_EXTENSIONS,
    document_format,
    load_pages,
)


@dataclass(frozen=True)
class ValidatedDocument:
    page_count: int
    has_text_layer: bool
    format: str


def validate_document(path: Path, max_size_bytes: int, max_pages: int) -> ValidatedDocument:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ApiError(
            400,
            "UNSUPPORTED_TYPE",
            "仅支持 PDF、Word、TXT、Markdown 文件",
        )
    size = path.stat().st_size
    if size <= 0:
        raise ApiError(400, "DOCUMENT_INVALID", "文件为空或已损坏")
    if size > max_size_bytes:
        raise ApiError(
            413,
            "FILE_TOO_LARGE",
            "文件超过大小上限",
            {"max_file_size_bytes": max_size_bytes},
        )
    fmt = document_format(path)
    try:
        pages = load_pages(path)
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(400, "DOCUMENT_INVALID", "文件无法解析，可能已损坏") from exc
    page_count = len(pages)
    if page_count <= 0:
        raise ApiError(400, "DOCUMENT_INVALID", "文档内容为空")
    if page_count > max_pages:
        raise ApiError(
            413, "TOO_MANY_PAGES", "文档页数超过上限", {"max_pages": max_pages}
        )
    has_text_layer = any(page.strip() for page in pages)
    return ValidatedDocument(page_count=page_count, has_text_layer=has_text_layer, format=fmt)
