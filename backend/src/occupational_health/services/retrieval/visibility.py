from __future__ import annotations

import uuid

from sqlalchemy import select

from occupational_health.db.models.content import Chunk
from occupational_health.db.models.documents import Document, DocumentVersion
from occupational_health.db.session import SessionLocal
from occupational_health.domain.enums import DocumentStatus, VersionStatus


def _visibility_maps(db, chunks: list[Chunk]) -> tuple[dict, dict]:
    documents = {
        document.id: document
        for document in db.scalars(
            select(Document).where(
                Document.id.in_({chunk.document_id for chunk in chunks})
            )
        )
    }
    versions = {
        version.id: version
        for version in db.scalars(
            select(DocumentVersion).where(
                DocumentVersion.id.in_(
                    {
                        document.current_version_id
                        for document in documents.values()
                        if document.current_version_id
                    }
                )
            )
        )
    }
    return documents, versions


def _is_visible(chunk: Chunk, documents: dict, versions: dict) -> bool:
    document = documents.get(chunk.document_id)
    if not document or document.status != DocumentStatus.SEARCHABLE:
        return False
    current = (
        versions.get(document.current_version_id)
        if document.current_version_id
        else None
    )
    return bool(
        current
        and current.status == VersionStatus.CURRENT
        and current.id == chunk.version_id
    )


def visible_chunks(chunk_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    if not chunk_ids:
        return {}
    with SessionLocal() as db:
        chunks = list(
            db.scalars(
                select(Chunk).where(
                    Chunk.id.in_(chunk_ids), Chunk.index_visible.is_(True)
                )
            )
        )
        if not chunks:
            return {}
        documents, versions = _visibility_maps(db, chunks)
        visible: dict[uuid.UUID, dict] = {}
        for chunk in chunks:
            if not _is_visible(chunk, documents, versions):
                continue
            document = documents.get(chunk.document_id)
            current = versions.get(document.current_version_id)
            visible[chunk.id] = {
                "text": chunk.raw_text,
                "raw_text": chunk.raw_text,
                "document_id": chunk.document_id,
                "version_number": current.version_number,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "masking_revision": chunk.masking_revision,
                "block_type": chunk.block_type,
                "chunk_role": chunk.chunk_role,
                "parent_chunk_id": chunk.parent_chunk_id,
                "page_offsets": chunk.page_offsets or {},
                "table_id": chunk.table_id,
                "section_title": chunk.section_title,
                "table_header": chunk.table_header,
                "table_html": chunk.table_html,
                "ordinal": chunk.ordinal,
            }
        return visible
