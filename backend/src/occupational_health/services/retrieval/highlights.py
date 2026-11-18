from __future__ import annotations

import re


def find_highlights(text: str, terms: list[str]) -> list[dict]:
    highlights: list[dict] = []
    for term in terms:
        if not term:
            continue
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        for match in pattern.finditer(text):
            highlights.append(
                {"start_offset": match.start(), "end_offset": match.end()}
            )
    return _dedupe(highlights)


def _dedupe(highlights: list[dict]) -> list[dict]:
    highlights.sort(key=lambda item: (item["start_offset"], item["end_offset"]))
    result = []
    for item in highlights:
        if result and item["start_offset"] < result[-1]["end_offset"]:
            continue
        result.append(item)
    return result
