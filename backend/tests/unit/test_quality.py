from occupational_health.domain.enums import PageSource
from occupational_health.services.extraction.quality import (
    PageQuality,
    page_status,
    summarize,
)


def test_low_confidence_ocr_page_is_flagged() -> None:
    page = PageQuality(1, PageSource.OCR, 100, 0, ocr_confidence=0.6)
    assert page_status(page, 0.75).value == "low_quality"


def test_summary_counts_ocr_ratio_and_failures() -> None:
    pages = [
        PageQuality(1, PageSource.TEXT_LAYER, 100, 0),
        PageQuality(2, PageSource.OCR, 100, 5, ocr_confidence=0.9),
        PageQuality(3, PageSource.OCR, 50, 0, failed=True, failure_code="OCR_FAILED"),
    ]
    summary = summarize(pages, 0.75)
    assert summary["ocr_page_ratio"] == 0.667
    assert summary["average_ocr_confidence"] == 0.9
    assert summary["failed_pages"] == [{"page_number": 3, "code": "OCR_FAILED"}]
