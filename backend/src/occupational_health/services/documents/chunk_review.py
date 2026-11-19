"""Human review of chunked text before embedding/indexing.

Phase one of the pipeline persists chunks without vectorising them. This
service exposes those chunks for preview/editing and, on confirmation, enqueues
phase two (embedding + Qdrant + publish).
"""

from __future__ import annotations

import hashlib
import logging
import uuid

from sqlalchemy import delete, func, select

from occupational_health.core.config import get_settings
from occupational_health.core.errors import ApiError
from occupational_health.db.models.content import Chunk
from occupational_health.db.models.documents import Document, DocumentVersion, StoredFile
from occupational_health.db.models.jobs import JobEvent, ProcessingJob
from occupational_health.db.session import SessionLocal, utcnow
from occupational_health.domain.enums import ChunkRole, JobStage, JobStatus
from occupational_health.services.chunking.service import (
    approximate_token_count,
    build_children_from_parents,
)
from occupational_health.services.extraction.table_html import parse_html_table
from occupational_health.services.retrieval.anchors import rebuild_chunk_anchors

logger = logging.getLogger(__name__)

_MAX_CHUNK_CHARS = 20_000

_SNAPSHOT_FIELDS = (
    "ordinal",
    "page_start",
    "page_end",
    "source_types",
    "raw_text",
    "masked_text",
    "block_type",
    "table_header",
    "table_id",
    "source_table_id",
    "section_title",
    "table_html",
    "is_edited",
    "token_count",
    "content_hash",
    "page_offsets",
    "chunk_role",
)


def _snapshot(chunk: Chunk) -> dict:
    return {field: getattr(chunk, field) for field in _SNAPSHOT_FIELDS}


def _first(chunks: list[Chunk], field: str) -> str | None:
    for chunk in chunks:
        value = getattr(chunk, field)
        if value:
            return value
    return None


def _refresh_text_metrics(chunk: Chunk) -> None:
    content = chunk.raw_text or ""
    chunk.token_count = approximate_token_count(content)
    chunk.content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()


def _job_chunks(db, job: ProcessingJob) -> list[Chunk]:
    return list(
        db.scalars(
            select(Chunk)
            .where(
                Chunk.version_id == job.version_id,
                Chunk.pipeline_revision == job.pipeline_revision,
                Chunk.chunk_role != ChunkRole.CHILD.value,
            )
            .order_by(Chunk.ordinal)
        )
    )


def _regenerate_children(db, job: ProcessingJob) -> int:
    """Rebuild retrieval children from the current, possibly edited parents."""
    settings = get_settings()
    parents = list(
        db.scalars(
            select(Chunk)
            .where(
                Chunk.version_id == job.version_id,
                Chunk.pipeline_revision == job.pipeline_revision,
                Chunk.chunk_role == ChunkRole.PARENT.value,
            )
            .order_by(Chunk.ordinal)
        )
    )
    if not parents:
        return 0
    db.execute(
        delete(Chunk).where(
            Chunk.version_id == job.version_id,
            Chunk.pipeline_revision == job.pipeline_revision,
            Chunk.chunk_role == ChunkRole.CHILD.value,
        )
    )
    parent_dicts = [
        {
            "ordinal": chunk.ordinal,
            "text": chunk.raw_text,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "block_type": chunk.block_type,
            "table_header": chunk.table_header,
            "table_id": chunk.table_id,
            "section_title": chunk.section_title,
            "page_offsets": chunk.page_offsets or {},
        }
        for chunk in parents
    ]
    children = build_children_from_parents(
        parent_dicts,
        settings.child_chunk_target_tokens,
        settings.child_chunk_max_tokens,
        settings.child_chunk_overlap_tokens,
        ordinal_start=max((parent.ordinal for parent in parents), default=-1) + 1,
    )
    parent_by_ordinal = {parent.ordinal: parent for parent in parents}
    for child in children:
        parent = parent_by_ordinal[child["parent_ordinal"]]
        db.add(
            Chunk(
                id=uuid.uuid5(
                    job.version_id, f"{job.pipeline_revision}:{child['ordinal']}"
                ),
                document_id=job.document_id,
                version_id=job.version_id,
                pipeline_revision=job.pipeline_revision,
                chunker_version=parent.chunker_version,
                chunk_role=ChunkRole.CHILD.value,
                parent_chunk_id=str(parent.id),
                ordinal=child["ordinal"],
                page_start=child["page_start"],
                page_end=child["page_end"],
                source_types=parent.source_types,
                raw_text=child["text"],
                masked_text=child["text"],
                block_type=child["block_type"],
                table_header=child.get("table_header"),
                table_id=child.get("table_id"),
                source_table_id=child.get("table_id"),
                section_title=child.get("section_title"),
                table_html=None,
                is_edited=False,
                page_offsets=child.get("page_offsets") or {},
                token_count=child["token_count"],
                content_hash=child["content_hash"],
                embedding_model=parent.embedding_model,
                embedding_revision=parent.embedding_revision,
                embedding_dimensions=parent.embedding_dimensions,
                index_visible=False,
            )
        )
    db.commit()
    return len(children)


class ChunkReviewService:
    def _job(self, db, job_id: uuid.UUID) -> ProcessingJob:
        job = db.get(ProcessingJob, job_id)
        if not job:
            raise ApiError(404, "NOT_FOUND", "任务不存在")
        return job

    def _reviewable(self, db, job_id: uuid.UUID) -> ProcessingJob:
        job = self._job(db, job_id)
        if job.status != JobStatus.PENDING_CONFIRMATION:
            raise ApiError(
                409,
                "JOB_NOT_REVIEWABLE",
                "该任务当前不在待确认状态，无法修改或确认切分结果",
            )
        return job

    def list_chunks(self, job_id: uuid.UUID) -> dict:
        with SessionLocal() as db:
            job = self._job(db, job_id)
            document = db.get(Document, job.document_id)
            version = db.get(DocumentVersion, job.version_id) if job.version_id else None
            stored = db.get(StoredFile, version.file_id) if version else None
            rows = _job_chunks(db, job)
            return {
                "job": {
                    "id": str(job.id),
                    "status": job.status.value,
                    "filename": stored.original_filename if stored else None,
                    "document_title": document.title if document else None,
                    "document_id": str(job.document_id),
                    "total_pages": job.total_pages,
                    "created_at": job.created_at,
                },
                "editable": job.status == JobStatus.PENDING_CONFIRMATION,
                "items": [_chunk_dict(chunk) for chunk in rows],
                "tables": _table_summary(rows),
            }

    def get_chunk(self, chunk_id: uuid.UUID) -> dict:
        """Published chunk lookup for external callers (MCP tools).

        The knowledge base publishes standards and regulations, so external
        callers receive the parsed source text unchanged.
        """
        with SessionLocal() as db:
            chunk = db.get(Chunk, chunk_id)
            if not chunk or not chunk.index_visible:
                raise ApiError(404, "NOT_FOUND", "切分块不存在或尚未入库")
            if chunk.chunk_role == ChunkRole.CHILD.value and chunk.parent_chunk_id:
                chunk = db.get(Chunk, uuid.UUID(chunk.parent_chunk_id))
                if not chunk or not chunk.index_visible:
                    raise ApiError(404, "NOT_FOUND", "切分块不存在或尚未入库")
            data = _chunk_dict(chunk)
            data.pop("raw_text", None)
            data["text"] = chunk.raw_text
            document = db.get(Document, chunk.document_id)
            version = (
                db.get(DocumentVersion, document.current_version_id)
                if document and document.current_version_id
                else None
            )
            data["document_id"] = str(chunk.document_id)
            data["document_name"] = document.title if document else None
            data["lifecycle_status"] = (
                document.lifecycle_status.value if document else None
            )
            data["standard_no"] = document.standard_no if document else None
            data["version_number"] = version.version_number if version else None
            return data

    def update_chunk(self, job_id: uuid.UUID, chunk_id: uuid.UUID, text: str) -> dict:
        content = (text or "").strip()
        if not content:
            raise ApiError(400, "VALIDATION_ERROR", "切分内容不能为空")
        if len(content) > _MAX_CHUNK_CHARS:
            raise ApiError(400, "VALIDATION_ERROR", "单个切分块内容过长")
        with SessionLocal() as db:
            job = self._reviewable(db, job_id)
            chunk = self._owned_chunk(db, job, chunk_id)
            chunk.raw_text = content
            chunk.masked_text = content
            chunk.token_count = approximate_token_count(content)
            chunk.content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            chunk.is_edited = True
            chunk.updated_at = utcnow()
            rebuild_chunk_anchors(db, chunk)
            db.commit()
            return _chunk_dict(chunk)

    def delete_chunk(self, job_id: uuid.UUID, chunk_id: uuid.UUID) -> dict:
        with SessionLocal() as db:
            job = self._reviewable(db, job_id)
            chunk = self._owned_chunk(db, job, chunk_id)
            db.execute(
                delete(Chunk).where(Chunk.parent_chunk_id == str(chunk_id))
            )
            db.delete(chunk)
            db.commit()
            return {"id": str(chunk_id), "deleted": True}

    def merge_chunks(
        self, job_id: uuid.UUID, chunk_ids: list[uuid.UUID]
    ) -> dict:
        """Merge adjacent chunks into the first one and keep an undo snapshot."""
        unique_ids = list(dict.fromkeys(chunk_ids))
        if len(unique_ids) < 2:
            raise ApiError(400, "VALIDATION_ERROR", "至少选择两个切分块才能合并")
        with SessionLocal() as db:
            job = self._reviewable(db, job_id)
            chunks = [self._owned_chunk(db, job, chunk_id) for chunk_id in unique_ids]
            # 用「在有序列表中的位置」判断相邻，不依赖 ordinal 是否连续编号，
            # 否则合并过一次留下空号后再合并会误判。
            positions = {
                row.id: index for index, row in enumerate(_job_chunks(db, job))
            }
            indexes = sorted(positions[chunk.id] for chunk in chunks)
            chunks.sort(key=lambda item: positions[item.id])
            if indexes != list(range(indexes[0], indexes[0] + len(indexes))):
                raise ApiError(
                    409, "CHUNKS_NOT_ADJACENT", "只能合并上下相邻的切分块"
                )

            head = chunks[0]
            head.merged_snapshot = [_snapshot(chunk) for chunk in chunks]
            head.raw_text = "\n\n".join(chunk.raw_text for chunk in chunks)
            head.masked_text = "\n\n".join(chunk.masked_text for chunk in chunks)
            head.page_start = min(chunk.page_start for chunk in chunks)
            head.page_end = max(chunk.page_end for chunk in chunks)
            head.block_type = (
                "table"
                if any(chunk.block_type == "table" for chunk in chunks)
                else "text"
            )
            head.table_header = _first(chunks, "table_header")
            head.table_id = _first(chunks, "table_id")
            head.source_table_id = _first(chunks, "source_table_id")
            head.section_title = _first(chunks, "section_title")
            html_parts = [chunk.table_html for chunk in chunks if chunk.table_html]
            head.table_html = "\n".join(html_parts) or None
            if len(head.raw_text) > _MAX_CHUNK_CHARS:
                raise ApiError(
                    400, "VALIDATION_ERROR", "合并后的内容过长，请减少合并的块数"
                )
            head.is_edited = True
            head.updated_at = utcnow()
            _refresh_text_metrics(head)
            rebuild_chunk_anchors(db, head)

            for chunk in chunks[1:]:
                db.execute(
                    delete(Chunk).where(Chunk.parent_chunk_id == str(chunk.id))
                )
                db.delete(chunk)
            # 保留原有 ordinal（允许空号），撤销时才能按原序号精确还原。
            db.commit()
            return {"items": [_chunk_dict(row) for row in _job_chunks(db, job)]}

    def unmerge_chunk(self, job_id: uuid.UUID, chunk_id: uuid.UUID) -> dict:
        """Restore the chunks that were merged into ``chunk_id``."""
        with SessionLocal() as db:
            job = self._reviewable(db, job_id)
            chunk = self._owned_chunk(db, job, chunk_id)
            snapshot = chunk.merged_snapshot or []
            if len(snapshot) < 2:
                raise ApiError(
                    409, "CHUNK_NOT_MERGED", "该切分块不是合并产生的，无法撤销"
                )
            db.delete(chunk)
            db.flush()
            restored: list[Chunk] = []
            for offset, entry in enumerate(snapshot):
                text = entry.get("raw_text") or ""
                restored_chunk = Chunk(
                    id=uuid.uuid4(),
                    document_id=chunk.document_id,
                    version_id=chunk.version_id,
                    pipeline_revision=chunk.pipeline_revision,
                    chunker_version=chunk.chunker_version,
                    # 合并块已删除，快照序号此刻必然空闲，可直接还原。
                    ordinal=entry.get("ordinal", offset),
                    page_start=entry.get("page_start") or 1,
                    page_end=entry.get("page_end") or 1,
                    source_types=entry.get("source_types") or [],
                    raw_text=text,
                    masked_text=entry.get("masked_text") or text,
                    block_type=entry.get("block_type") or "text",
                    table_header=entry.get("table_header"),
                    table_id=entry.get("table_id"),
                    source_table_id=entry.get("source_table_id"),
                    section_title=entry.get("section_title"),
                    table_html=entry.get("table_html"),
                    merged_snapshot=None,
                    is_edited=entry.get("is_edited", False),
                    token_count=entry.get("token_count")
                    or approximate_token_count(text),
                    content_hash=entry.get("content_hash")
                    or hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    chunk_role=entry.get("chunk_role") or chunk.chunk_role,
                    parent_chunk_id=None,
                    page_offsets=entry.get("page_offsets") or {},
                    embedding_model=chunk.embedding_model,
                    embedding_revision=chunk.embedding_revision,
                    embedding_dimensions=chunk.embedding_dimensions,
                    index_visible=False,
                )
                db.add(restored_chunk)
                restored.append(restored_chunk)
            db.flush()
            for restored_chunk in restored:
                rebuild_chunk_anchors(db, restored_chunk)
            db.commit()
            return {"items": [_chunk_dict(row) for row in _job_chunks(db, job)]}

    def confirm(self, job_id: uuid.UUID) -> dict:
        with SessionLocal() as db:
            job = self._reviewable(db, job_id)
            _regenerate_children(db, job)
            count = len(_job_chunks(db, job))
            if not count:
                raise ApiError(409, "NO_CHUNKS", "没有可入库的切分块，请重新处理文档")
            sequence = (
                db.scalar(
                    select(func.count())
                    .select_from(JobEvent)
                    .where(JobEvent.job_id == job.id)
                )
                or 0
            ) + 1
            db.add(
                JobEvent(
                    job_id=job.id,
                    sequence=sequence,
                    from_status=JobStatus.PENDING_CONFIRMATION.value,
                    to_status=JobStatus.EMBEDDING.value,
                    stage=JobStage.EMBEDDING.value,
                    message="人工确认切分结果，开始向量化",
                )
            )
            job.status = JobStatus.EMBEDDING
            job.current_stage = JobStage.EMBEDDING
            job.error_code = None
            job.safe_error_message = None
            job.heartbeat_at = utcnow()
            db.commit()

        try:
            from occupational_health.workers.tasks import finalize_document_task

            finalize_document_task.delay(str(job_id))
            logger.info("chunk review confirmed", extra={"job_id": str(job_id)})
        except Exception as exc:
            logger.exception(
                "failed to enqueue finalize task", extra={"job_id": str(job_id)}
            )
            with SessionLocal() as db:
                job = self._job(db, job_id)
                job.status = JobStatus.PENDING_CONFIRMATION
                job.current_stage = JobStage.REVIEW
                db.commit()
            raise ApiError(503, "QUEUE_UNAVAILABLE", "任务队列不可用，请稍后重试确认") from exc
        return {
            "job_id": str(job_id),
            "status": JobStatus.EMBEDDING.value,
            "chunk_count": count or 0,
        }

    def _owned_chunk(self, db, job: ProcessingJob, chunk_id: uuid.UUID) -> Chunk:
        chunk = db.get(Chunk, chunk_id)
        if (
            not chunk
            or chunk.version_id != job.version_id
            or chunk.pipeline_revision != job.pipeline_revision
        ):
            raise ApiError(404, "NOT_FOUND", "切分块不存在")
        if chunk.chunk_role == ChunkRole.CHILD.value:
            raise ApiError(409, "CHILD_CHUNK_READONLY", "检索子块不可单独编辑，请修改父块")
        if chunk.index_visible:
            raise ApiError(409, "CHUNK_LOCKED", "该切分块已入库，不能再修改")
        return chunk


def _chunk_dict(chunk: Chunk) -> dict:
    return {
        "id": str(chunk.id),
        "chunk_role": chunk.chunk_role,
        "ordinal": chunk.ordinal,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "block_type": chunk.block_type,
        "table_header": chunk.table_header,
        "table_id": chunk.table_id,
        "section_title": chunk.section_title,
        "table_html": chunk.table_html,
        "text": chunk.masked_text,
        "raw_text": chunk.raw_text,
        "token_count": chunk.token_count,
        "is_edited": chunk.is_edited,
        "index_visible": chunk.index_visible,
        # 是否由人工合并产生，确认页据此显示「撤销合并」。
        "merged": bool(chunk.merged_snapshot),
    }


def _table_summary(chunks: list[Chunk]) -> list[dict]:
    """One entry per whole-table chunk, for the review page overview."""
    tables = [
        chunk
        for chunk in chunks
        if chunk.block_type == "table" and chunk.table_id
    ]
    return [
        {
            "table_id": chunk.table_id,
            "section_title": chunk.section_title,
            "header": chunk.table_header,
            "row_count": len(parse_html_table(chunk.table_html or "")),
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "merged": chunk.page_end > chunk.page_start,
        }
        for chunk in sorted(tables, key=lambda item: item.page_start)
    ]
