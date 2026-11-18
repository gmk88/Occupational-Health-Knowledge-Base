from __future__ import annotations

import fitz


def extract_page_text(path, page_number: int, min_chars: int) -> tuple[str, int]:
    """Return raw text and effective character count for one page."""
    document = fitz.open(path)
    try:
        page = document[page_number - 1]
        raw = page.get_text("text") or ""
    finally:
        document.close()
    effective = len([ch for ch in raw if not ch.isspace()])
    return raw, effective
