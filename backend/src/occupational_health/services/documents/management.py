from __future__ import annotations

import csv
import io
import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import object_session

from occupational_health.core.errors import ApiError
from occupational_health.db.models.content import Chunk
from occupational_health.db.models.documents import (
    Document,
    DocumentVersion,
    StoredFile,
)
from occupational_health.db.models.jobs import JobEvent, ProcessingJob, QualityReport
from occupational_health.db.models.operations import OutboxEvent
from occupational_health.db.models.taxonomy import DocumentTag, Tag
from occupational_health.db.session import SessionLocal, utcnow
from occupational_health.domain.enums import (
    ChunkMode,
    DocumentStatus,
    JobStatus,
    JobType,
    VersionStatus,
)

TERMINAL = {
    JobStatus.COMPLETED,
    JobStatus.PARTIAL_SUCCESS,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
}

logger = logging.getLogger(__name__)


class ManagementService:
    def cancel_job(self, job_id: uuid.UUID, actor: uuid.UUID) -> dict:
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            if not job:
                raise ApiError(404, "NOT_FOUND", "任务不存在")
            if job.status in TERMINAL:
                raise ApiError(409, "CONFLICT", "终态任务不可取消")
            job.cancel_requested_at = utcnow()
            db.add(
                JobEvent(
                    job_id=job.id,
                    sequence=_next_sequence(db, job.id),
                    from_status=job.status.value,
                    to_status="cancelled",
                    stage="cleanup",
                    message="请求取消",
                )
            )
            db.commit()
            return _job_dict(job)

    def retry_job(self, job_id: uuid.UUID, actor: uuid.UUID) -> dict:
        with SessionLocal() as db:
            source = db.get(ProcessingJob, job_id)
            if not source:
                raise ApiError(404, "NOT_FOUND", "任务不存在")
            if source.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
                raise ApiError(409, "CONFLICT", "仅失败或已取消任务可重试")
            document = db.get(Document, source.document_id)
            stored = _stored_file(db, source.version_id)
            page_count = stored.page_count or source.total_pages
            if page_count <= 0:
                raise ApiError(409, "CONFLICT", "原文件页数未知，无法重试")
            document.activation_epoch += 1
            job = ProcessingJob(
                document_id=source.document_id,
                version_id=source.version_id,
                job_type=JobType.RETRY,
                chunk_mode=source.chunk_mode,
                chunk_target_tokens=source.chunk_target_tokens,
                chunk_max_tokens=source.chunk_max_tokens,
                chunk_overlap_tokens=source.chunk_overlap_tokens,
                target_activation_epoch=document.activation_epoch,
                input_fingerprint=source.input_fingerprint,
                total_pages=page_count,
                retry_of_job_id=source.id,
                requested_by=actor,
                heartbeat_at=utcnow(),
            )
            db.add(job)
            db.flush()
            db.add(
                JobEvent(
                    job_id=job.id,
                    sequence=1,
                    from_status="",
                    to_status=JobStatus.QUEUED.value,
                    stage="validation",
                    message="重试任务",
                )
            )
            db.commit()
            result = _job_dict(job)
            job_id = str(job.id)
            storage_key = stored.storage_key
        _enqueue(job_id, storage_key)
        return result

    def delete_document(self, document_id: uuid.UUID, actor: uuid.UUID) -> dict:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if not document or document.status == DocumentStatus.DELETED:
                raise ApiError(404, "NOT_FOUND", "文档不存在")
            revisions = [
                str(revision)
                for revision in db.scalars(
                    select(Chunk.pipeline_revision)
                    .where(Chunk.document_id == document.id)
                    .distinct()
                )
            ]
            document.status = DocumentStatus.DELETED
            document.deleted_at = utcnow()
            # 待确认/执行中的任务一并取消，避免首页继续提醒确认已删除的文档。
            for job in db.scalars(
                select(ProcessingJob).where(
                    ProcessingJob.document_id == document.id
                )
            ):
                if job.status not in TERMINAL:
                    job.status = JobStatus.CANCELLED
                    job.finished_at = utcnow()
            # 数据库侧立刻下线，检索的二次校验也不会再放行。
            db.execute(
                update(Chunk)
                .where(Chunk.document_id == document.id)
                .values(index_visible=False)
            )
            db.add(
                OutboxEvent(
                    aggregate_type="document",
                    aggregate_id=document.id,
                    event_type="index.hide",
                    payload={
                        "document_id": str(document.id),
                        "pipeline_revisions": revisions,
                    },
                )
            )
            db.commit()
        # Qdrant 侧的向量点同步删除；索引服务异常不影响文档删除结果。
        self._purge_index(revisions, document_id)
        return {
            "document_id": str(document_id),
            "status": "deleted",
            "index_revisions_removed": len(revisions),
        }

    @staticmethod
    def _purge_index(revisions: list[str], document_id: uuid.UUID) -> None:
        try:
            from qdrant_client import QdrantClient

            from occupational_health.core.config import get_settings
            from occupational_health.services.indexing.qdrant import QdrantIndexer

            settings = get_settings()
            indexer = QdrantIndexer(
                QdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key.get_secret_value(),
                    timeout=10,
                )
            )
            for revision in revisions:
                indexer.delete_revision(uuid.UUID(revision))
            if not revisions:
                indexer.hide_document(document_id)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "failed to purge index for deleted document %s: %s",
                document_id,
                exc,
            )

    def list_versions(self, document_id: uuid.UUID) -> list[dict]:
        with SessionLocal() as db:
            versions = db.scalars(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.version_number.desc())
            )
            return [_version_dict(version) for version in versions]

    def rollback(
        self, document_id: uuid.UUID, version_number: int, actor: uuid.UUID
    ) -> dict:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if not document or document.status == DocumentStatus.DELETED:
                raise ApiError(404, "NOT_FOUND", "文档不存在")
            target = db.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.version_number == version_number,
                )
            )
            if not target:
                raise ApiError(404, "NOT_FOUND", "版本不存在")
            document.current_version_id = target.id
            document.active_pipeline_revision = None
            document.activation_epoch += 1
            db.execute(
                update(DocumentVersion)
                .where(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.status == VersionStatus.CURRENT,
                )
                .values(status=VersionStatus.REPLACED, replaced_at=utcnow())
            )
            target.status = VersionStatus.CURRENT
            target.activated_at = utcnow()
            db.commit()
            return {
                "document_id": str(document_id),
                "version_number": version_number,
                "status": "current",
            }

    def quality_export(self, document_id: uuid.UUID, format: str) -> dict:
        with SessionLocal() as db:
            report = db.scalar(
                select(QualityReport)
                .where(QualityReport.document_id == document_id)
                .order_by(QualityReport.created_at.desc())
            )
            if not report:
                raise ApiError(404, "NOT_FOUND", "尚未生成质量报告")
            data = {
                "page_count": report.page_count,
                "effective_char_count": report.effective_char_count,
                "chunk_count": report.chunk_count,
                "ocr_page_ratio": float(report.ocr_page_ratio or 0),
                "average_ocr_confidence": (
                    float(report.average_ocr_confidence)
                    if report.average_ocr_confidence is not None
                    else None
                ),
                "noise_char_count": report.noise_char_count,
                "low_quality_pages": report.low_quality_pages,
                "failed_pages": report.failed_pages,
                "processing_duration_ms": report.processing_duration_ms,
            }
            if format == "csv":
                buffer = io.StringIO()
                writer = csv.writer(buffer)
                writer.writerow(data.keys())
                writer.writerow(data.values())
                return {"format": "csv", "content": buffer.getvalue()}
            return {"format": "json", "content": data}

    def merge_tags(self, source_tag_id: uuid.UUID, target_tag_id: uuid.UUID) -> dict:
        if source_tag_id == target_tag_id:
            raise ApiError(409, "CONFLICT", "不能合并到自身")
        with SessionLocal() as db:
            source = db.get(Tag, source_tag_id)
            target = db.get(Tag, target_tag_id)
            if not source or not target:
                raise ApiError(404, "NOT_FOUND", "标签不存在")
            source.merged_into_id = target.id
            for link in db.scalars(
                select(DocumentTag).where(DocumentTag.tag_id == source.id)
            ):
                if not db.scalar(
                    select(DocumentTag).where(
                        DocumentTag.document_id == link.document_id,
                        DocumentTag.tag_id == target.id,
                    )
                ):
                    db.add(DocumentTag(document_id=link.document_id, tag_id=target.id))
                db.delete(link)
            db.commit()
            return {"id": str(target.id), "name": target.name}

    def reprocess(self, document_id: uuid.UUID, actor: uuid.UUID) -> dict:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if not document or document.status == DocumentStatus.DELETED:
                raise ApiError(404, "NOT_FOUND", "文档不存在")
            version_id = document.current_version_id
            if not version_id:
                raise ApiError(409, "CONFLICT", "文档尚未处理完成，无法重新处理")
            stored = _stored_file(db, version_id)
            page_count = stored.page_count
            if page_count <= 0:
                raise ApiError(409, "CONFLICT", "原文件页数未知，无法重新处理")
            document.activation_epoch += 1
            latest = db.scalar(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document.id)
                .order_by(ProcessingJob.created_at.desc())
            )
            # 重新处理始终使用当前推荐的语义父子块；不再沿用历史任务的旧切分模式。
            chunk_mode = ChunkMode.PARENT_CHILD.value
            job = ProcessingJob(
                document_id=document.id,
                version_id=version_id,
                job_type=JobType.REPROCESS,
                chunk_mode=chunk_mode,
                chunk_target_tokens=None,
                chunk_max_tokens=None,
                chunk_overlap_tokens=None,
                target_activation_epoch=document.activation_epoch,
                input_fingerprint="reprocess",
                total_pages=page_count,
                requested_by=actor,
                heartbeat_at=utcnow(),
            )
            db.add(job)
            db.flush()
            db.add(
                JobEvent(
                    job_id=job.id,
                    sequence=1,
                    from_status="",
                    to_status=JobStatus.QUEUED.value,
                    stage="validation",
                    message="重新处理",
                )
            )
            db.commit()
            result = _job_dict(job)
            job_id = str(job.id)
            storage_key = stored.storage_key
        _enqueue(job_id, storage_key)
        return result

    def correct_masking(self, document_id: uuid.UUID, actor: uuid.UUID) -> dict:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if not document or document.status == DocumentStatus.DELETED:
                raise ApiError(404, "NOT_FOUND", "文档不存在")
            document.masking_revision += 1
            db.commit()
            return {
                "document_id": str(document_id),
                "masking_revision": document.masking_revision,
                "updated_chunks": 0,
                "status": "published",
            }


def _stored_file(db, version_id: uuid.UUID | None) -> StoredFile:
    version = db.get(DocumentVersion, version_id) if version_id else None
    stored = db.get(StoredFile, version.file_id) if version else None
    if not stored:
        raise ApiError(409, "CONFLICT", "原文件信息缺失，无法重新处理")
    return stored


def _enqueue(job_id: str, storage_key: str) -> None:
    try:
        from occupational_health.workers.tasks import process_document_task

        result = process_document_task.delay(job_id, storage_key)
        logger.info(
            "document job enqueued",
            extra={"job_id": job_id, "result": result.id},
        )
    except Exception as exc:
        logger.exception("failed to enqueue document job", extra={"job_id": job_id})
        # 投递失败时把任务标为失败，避免界面永远停在「排队中」。
        with SessionLocal() as db:
            job = db.get(ProcessingJob, uuid.UUID(job_id))
            if job:
                job.status = JobStatus.FAILED
                job.error_code = "ENQUEUE_FAILED"
                job.safe_error_message = "任务投递失败，请稍后重试"
                job.finished_at = utcnow()
                db.commit()
        raise ApiError(503, "TASK_ENQUEUE_FAILED", "任务投递失败，请稍后重试") from exc


def _next_sequence(db, job_id: uuid.UUID) -> int:
    latest = db.scalar(
        select(JobEvent.sequence)
        .where(JobEvent.job_id == job_id)
        .order_by(JobEvent.sequence.desc())
        .limit(1)
    )
    return (latest or 0) + 1


def _version_dict(version: DocumentVersion) -> dict:
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "status": version.status.value,
        "content_sha256": version.content_sha256,
        "created_at": version.created_at,
        "activated_at": version.activated_at,
    }


def _job_dict(job: ProcessingJob) -> dict:
    db = object_session(job)
    filename = None
    document_title = None
    if db is not None:
        version = db.get(DocumentVersion, job.version_id) if job.version_id else None
        stored = db.get(StoredFile, version.file_id) if version else None
        filename = stored.original_filename if stored else None
        document = db.get(Document, job.document_id)
        document_title = document.title if document else None
    return {
        "id": str(job.id),
        "document_id": str(job.document_id),
        "version_id": str(job.version_id) if job.version_id else None,
        "filename": filename,
        "document_title": document_title,
        "job_type": job.job_type.value,
        "status": job.status.value,
        "current_stage": job.current_stage.value,
        "processed_pages": job.processed_pages,
        "total_pages": job.total_pages,
        "retry_of_job_id": str(job.retry_of_job_id) if job.retry_of_job_id else None,
        "created_at": job.created_at,
    }
