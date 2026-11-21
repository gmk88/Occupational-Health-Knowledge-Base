"""Locate a retrieval chunk inside the text of its source page.

Offsets are Unicode code-point based (Python string indexes) and refer to the
exact ``text`` returned by the page endpoint, so the front-end can render the
highlight without re-parsing the document.
"""

from __future__ import annotations

# Short fragments are likely to match unrelated text (page headers, units...).
_MIN_ANCHOR_CHARS = 12
_MAX_ANCHORS = 200
_MAX_SPANS = 24
# Markdown table separators differ between the extracted page text and the
# chunk text produced by the table parser; ignoring them keeps offsets usable.
_IGNORED_CHARS = frozenset({"|"})


def _compact(text: str) -> tuple[str, list[int]]:
    """Drop whitespace/table pipes, keeping a map back to source offsets."""
    chars: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(text):
        if char.isspace() or char in _IGNORED_CHARS:
            continue
        chars.append(char)
        offsets.append(index)
    return "".join(chars), offsets


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged[:_MAX_SPANS]


def _fragments(chunk_text: str) -> list[str]:
    """Split a chunk into line/sentence anchors for partial page matches."""
    fragments: list[str] = []
    for line in chunk_text.splitlines()[:_MAX_ANCHORS]:
        if not line.strip():
            continue
        if len(line.strip()) <= _MIN_ANCHOR_CHARS * 3:
            fragments.append(line)
            continue
        # Long paragraphs may be split differently from the page text; sentence
        # level anchors still locate the part that belongs to this page.
        sentence_start = 0
        for index, char in enumerate(line):
            if char not in "。！？；!?;" or index - sentence_start < _MIN_ANCHOR_CHARS:
                continue
            fragments.append(line[sentence_start : index + 1])
            sentence_start = index + 1
        if sentence_start < len(line):
            fragments.append(line[sentence_start:])
    return fragments


def locate_chunk(page_text: str, chunk_text: str) -> list[dict]:
    """Return ``{start_offset, end_offset, type}`` spans for a chunk.

    A whole-chunk exact match is preferred. Cross-page chunks, overlapped
    chunks and table chunks are located by their longest matching fragments;
    an empty list means the page text cannot be anchored reliably.
    """
    if not page_text or not chunk_text:
        return []
    compact_page, offsets = _compact(page_text)
    compact_chunk, _ = _compact(chunk_text)
    if not compact_page or len(compact_chunk) < _MIN_ANCHOR_CHARS:
        return []

    hits: list[tuple[int, int]] = []
    whole = compact_page.find(compact_chunk)
    if whole >= 0:
        hits.append((whole, whole + len(compact_chunk)))
    else:
        cursor = 0
        for fragment in _fragments(chunk_text):
            compact_fragment, _ = _compact(fragment)
            if len(compact_fragment) < _MIN_ANCHOR_CHARS:
                continue
            found = compact_page.find(compact_fragment, cursor)
            if found < 0:
                found = compact_page.find(compact_fragment)
            if found < 0:
                continue
            end = found + len(compact_fragment)
            hits.append((found, end))
            cursor = end

    return [
        {
            "start_offset": offsets[start],
            "end_offset": offsets[end - 1] + 1,
            "type": "chunk",
        }
        for start, end in _merge(hits)
        if 0 <= start < end <= len(offsets)
    ]
