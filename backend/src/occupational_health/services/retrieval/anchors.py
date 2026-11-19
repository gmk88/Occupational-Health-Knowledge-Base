from __future__ import annotations

import difflib
import hashlib
import re
import unicodedata
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Iterable

from sqlalchemy import delete, select

from occupational_health.db.models.content import Chunk, ChunkAnchor, Page
from occupational_health.db.session import SessionLocal

_MAX_CANDIDATE_CHARS = 2000


def _squash(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize(text: str) -> tuple[str, list[int]]:
    """Normalize text while keeping a map back to source offsets."""
    normalized: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(text):
        value = unicodedata.normalize("NFKC", char).casefold()
        if not value:
            continue
        for normalized_char in value:
            if normalized_char.isalnum():
                normalized.append(normalized_char)
                offsets.append(index)
    return "".join(normalized), offsets


def _candidates(chunk_text: str, block_type: str) -> list[str]:
    clean = _squash(chunk_text)
    if not clean:
        return []
    candidates = [clean[:_MAX_CANDIDATE_CHARS]]
    if block_type == "table":
        lines = [line.strip() for line in clean.splitlines() if line.strip()]
        if lines:
            candidates.append(" ".join(lines[:3])[:800])
    else:
        lines = [line.strip() for line in clean.splitlines() if line.strip()]
        if lines:
            candidates.append(max(lines, key=len)[:500])
            candidates.append(" ".join(lines[:3])[:800])
    seen: set[str] = set()
    result: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


def _match_offsets(candidate: str, page_text: str) -> tuple[int, int, str, float, str] | None:
    position = page_text.find(candidate)
    if position >= 0:
        return position, position + len(candidate), candidate, 1.0, "exact"

    needle, needle_map = _normalize(candidate)
    haystack, haystack_map = _normalize(page_text)
    if not needle or not haystack:
        return None

    position = haystack.find(needle)
    if position >= 0:
        start = haystack_map[position]
        end = haystack_map[position + len(needle) - 1] + 1
        return start, end, page_text[start:end], 0.95, "normalized_exact"

    matcher = difflib.SequenceMatcher(None, needle, haystack, autojunk=False)
    match = matcher.find_longest_match(0, len(needle), 0, len(haystack))
    required = min(len(needle), max(12, int(len(needle) * 0.6)))
    if match.size < required or match.a >= len(needle_map) or match.b >= len(haystack_map):
        return None
    start = haystack_map[match.b]
    end = haystack_map[match.b + match.size - 1] + 1
    confidence = min(0.89, 0.6 + 0.3 * (match.size / max(1, len(needle))))
    return start, end, page_text[start:end], confidence, "fuzzy"


def _anchor_type(chunk: Chunk) -> str:
    if chunk.block_type == "table":
        return "table_row"
    if chunk.block_type == "formula":
        return "formula"
    return "text"


def build_chunk_anchors(db, chunk: Chunk) -> list[ChunkAnchor]:
    """Build text-level anchors for one chunk from its source pages."""
    pages = list(
        db.scalars(
            select(Page)
            .where(
                Page.version_id == chunk.version_id,
                Page.pipeline_revision == chunk.pipeline_revision,
                Page.page_number >= chunk.page_start,
                Page.page_number <= min(chunk.page_end, chunk.page_start + 2),
            )
            .order_by(Page.page_number)
        )
    )
    candidates = _candidates(chunk.raw_text, chunk.block_type)
    quote_hash = chunk.content_hash or hashlib.sha256(
        (chunk.raw_text or "").encode("utf-8")
    ).hexdigest()
    anchor_type = _anchor_type(chunk)
    anchors: list[ChunkAnchor] = []

    for page in pages:
        page_text = page.cleaned_text or page.raw_text or ""
        matched: tuple[int, int, str, float, str] | None = None
        for candidate in candidates:
            matched = _match_offsets(candidate, page_text)
            if matched:
                break
        if matched:
            start, end, quote, confidence, method = matched
            status = "active"
        else:
            start = end = None
            quote = candidates[0][:300] if candidates else ""
            confidence = 0.0
            method = "page_fallback"
            status = "page_only"
        anchors.append(
            ChunkAnchor(
                chunk_id=chunk.id,
                version_id=chunk.version_id,
                pipeline_revision=chunk.pipeline_revision,
                page_number=page.page_number,
                start_offset=start,
                end_offset=end,
                quote=quote,
                quote_hash=quote_hash,
                anchor_type=anchor_type if start is not None else "page_only",
                match_method=method,
                confidence=confidence,
                status=status,
            )
        )

    if not anchors:
        anchors.append(
            ChunkAnchor(
                chunk_id=chunk.id,
                version_id=chunk.version_id,
                pipeline_revision=chunk.pipeline_revision,
                page_number=chunk.page_start,
                start_offset=None,
                end_offset=None,
                quote=candidates[0][:300] if candidates else "",
                quote_hash=quote_hash,
                anchor_type="page_only",
                match_method="page_fallback",
                confidence=0.0,
                status="page_only",
            )
        )
    return anchors


def rebuild_chunk_anchors(db, chunk: Chunk) -> int:
    db.execute(delete(ChunkAnchor).where(ChunkAnchor.chunk_id == chunk.id))
    anchors = build_chunk_anchors(db, chunk)
    for anchor in anchors:
        db.add(anchor)
    return len(anchors)


def rebuild_all_chunk_anchors(batch_size: int = 500) -> int:
    total = 0
    last_id = uuid.UUID(int=0)
    with SessionLocal() as db:
        while True:
            chunks = list(
                db.scalars(
                    select(Chunk)
                    .where(Chunk.id > last_id)
                    .order_by(Chunk.id)
                    .limit(batch_size)
                )
            )
            if not chunks:
                break
            for chunk in chunks:
                total += rebuild_chunk_anchors(db, chunk)
                last_id = chunk.id
            db.commit()
    return total


def _anchor_dict(anchor: ChunkAnchor) -> dict:
    confidence = anchor.confidence
    if isinstance(confidence, Decimal):
        confidence = float(confidence)
    return {
        "chunk_id": str(anchor.chunk_id),
        "page_number": anchor.page_number,
        "start_offset": anchor.start_offset,
        "end_offset": anchor.end_offset,
        "quote": anchor.quote,
        "anchor_type": anchor.anchor_type,
        "match_method": anchor.match_method,
        "confidence": confidence,
        "status": anchor.status,
    }


def anchors_payload(db, chunk_ids: Iterable[uuid.UUID]) -> dict[str, list[dict]]:
    ids = [value for value in dict.fromkeys(chunk_ids)]
    if not ids:
        return {}
    rows = db.scalars(
        select(ChunkAnchor)
        .where(ChunkAnchor.chunk_id.in_(ids))
        .order_by(ChunkAnchor.chunk_id, ChunkAnchor.page_number, ChunkAnchor.id)
    ).all()
    payload: dict[str, list[dict]] = defaultdict(list)
    for anchor in rows:
        payload[str(anchor.chunk_id)].append(_anchor_dict(anchor))
    return dict(payload)


def page_anchors(
    db,
    version_id: uuid.UUID,
    pipeline_revision: uuid.UUID,
    page_number: int,
    chunk_id: uuid.UUID | None = None,
) -> list[dict]:
    statement = (
        select(ChunkAnchor)
        .where(
            ChunkAnchor.version_id == version_id,
            ChunkAnchor.pipeline_revision == pipeline_revision,
            ChunkAnchor.page_number == page_number,
        )
        .order_by(ChunkAnchor.id)
    )
    if chunk_id:
        statement = statement.where(ChunkAnchor.chunk_id == chunk_id)
    return [_anchor_dict(anchor) for anchor in db.scalars(statement).all()]
