from __future__ import annotations

from dataclasses import dataclass

from occupational_health.domain.enums import PageSource, PageStatus


@dataclass
class PageQuality:
    page_number: int
    source_type: PageSource
    effective_char_count: int
    noise_char_count: int
    ocr_confidence: float | None = None
    failed: bool = False
    failure_code: str | None = None
    layout_warnings: list[str] | None = None


def page_status(quality: PageQuality, low_confidence: float) -> PageStatus:
    if quality.failed:
        return PageStatus.FAILED
    if quality.effective_char_count == 0:
        return PageStatus.EMPTY
    if quality.source_type in (PageSource.OCR, PageSource.MIXED):
        if quality.ocr_confidence is None or quality.ocr_confidence < low_confidence:
            return PageStatus.LOW_QUALITY
    return PageStatus.COMPLETED


def summarize(pages: list[PageQuality], low_confidence: float) -> dict:
    total = len(pages)
    if total == 0:
        return {
            "page_count": 0,
            "effective_char_count": 0,
            "ocr_page_ratio": 0.0,
            "average_ocr_confidence": None,
            "noise_char_count": 0,
            "low_quality_pages": [],
            "failed_pages": [],
        }
    effective = sum(page.effective_char_count for page in pages)
    noise = sum(page.noise_char_count for page in pages)
    ocr_pages = [
        page for page in pages if page.source_type in (PageSource.OCR, PageSource.MIXED)
    ]
    confidences = [
        page.ocr_confidence for page in ocr_pages if page.ocr_confidence is not None
    ]
    low_quality = [
        page.page_number
        for page in pages
        if page_status(page, low_confidence) == PageStatus.LOW_QUALITY
    ]
    failed = [
        {"page_number": page.page_number, "code": page.failure_code}
        for page in pages
        if page.failed
    ]
    return {
        "page_count": total,
        "effective_char_count": effective,
        "ocr_page_ratio": round(len(ocr_pages) / total, 3),
        "average_ocr_confidence": (
            round(sum(confidences) / len(confidences), 3) if confidences else None
        ),
        "noise_char_count": noise,
        "low_quality_pages": low_quality,
        "failed_pages": failed,
    }
