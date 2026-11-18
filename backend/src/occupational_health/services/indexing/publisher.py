from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import update

from occupational_health.db.models.content import Chunk
from occupational_health.db.models.documents import Document, DocumentVersion
from occupational_health.db.models.jobs import ProcessingJob
from occupational_health.db.session import SessionLocal
from occupational_health.domain.enums import DocumentStatus, JobStatus, VersionStatus


def publish(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    job_id: uuid.UUID,
    pipeline_revision: uuid.UUID,
    target_epoch: int,
    chunk_count: int,
) -> bool:
    """Activate the revision only when it is still the newest request."""
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if not document or document.activation_epoch != target_epoch:
            return False
        now = datetime.now(UTC)
        db.execute(
            update(DocumentVersion)
            .where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.status == VersionStatus.CURRENT,
                DocumentVersion.id != version_id,
            )
            .values(status=VersionStatus.REPLACED, replaced_at=now)
        )
        version = db.get(DocumentVersion, version_id)
        if version:
            version.status = VersionStatus.CURRENT
            version.activated_at = now
        document.current_version_id = version_id
        document.active_pipeline_revision = pipeline_revision
        document.status = DocumentStatus.SEARCHABLE
        document.updated_at = now
        # 重新处理时复用 version_id 但换 pipeline_revision，旧块必须一并下线，
        # 否则检索会同时返回新旧两套切分结果。
        db.execute(
            update(Chunk)
            .where(
                Chunk.version_id == version_id,
                Chunk.pipeline_revision != pipeline_revision,
            )
            .values(index_visible=False)
        )
        db.execute(
            update(Chunk)
            .where(
                Chunk.version_id == version_id,
                Chunk.pipeline_revision == pipeline_revision,
            )
            .values(index_visible=True)
        )
        db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id)
            .values(
                status=JobStatus.COMPLETED,
                finished_at=now,
                processed_pages=ProcessingJob.total_pages,
                error_code=None,
                safe_error_message=None,
            )
        )
        db.commit()
        return True


def mark_needs_review(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    job_id: uuid.UUID,
    message: str,
) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document:
            document.status = DocumentStatus.NEEDS_REVIEW
        version = db.get(DocumentVersion, version_id)
        if version:
            version.status = VersionStatus.NEEDS_REVIEW
        job = db.get(ProcessingJob, job_id)
        if job:
            job.status = JobStatus.PARTIAL_SUCCESS
            job.error_code = "LOW_CONTENT"
            job.safe_error_message = message
            job.finished_at = datetime.now(UTC)
        db.commit()


def quality_gate(summary: dict, min_chars: int) -> bool:
    return summary["effective_char_count"] >= min_chars
