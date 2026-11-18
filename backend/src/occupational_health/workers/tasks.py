from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy.exc import DataError

from occupational_health.core.config import get_settings
from occupational_health.db.models.jobs import ProcessingJob
from occupational_health.db.session import SessionLocal
from occupational_health.domain.enums import JobStatus
from occupational_health.services.jobs.retention import prune_job_history
from occupational_health.workers.celery_app import celery_app
from occupational_health.workers.pipeline import _mark_failed, process_document

_LOGGER = logging.getLogger(__name__)


def _prune_history() -> None:
    """Trim old task records; never let cleanup break the task itself."""
    try:
        removed = prune_job_history(get_settings().job_history_keep)
        if removed:
            _LOGGER.info("pruned %s old processing jobs", removed)
    except Exception as exc:
        _LOGGER.warning("job history pruning failed: %s", exc)


@celery_app.task(
    bind=True,
    name="process_document",
    max_retries=3,
    retry_backoff=True,
    retry_jitter=True,
)
def process_document_task(self, job_id: str, storage_key: str) -> None:
    settings = get_settings()
    file_path = Path(settings.storage_root) / storage_key
    try:
        process_document(uuid.UUID(job_id), file_path, settings)
    except Exception as exc:
        # 数据本身的问题重试多少次都不会成功，直接给终态，避免反复重跑解析。
        if isinstance(exc, DataError):
            _mark_failed(uuid.UUID(job_id), exc, terminal=True)
            return
        # 单一重试权威：job.attempt_count 决定是否重试，Celery autoretry 已移除。
        if _mark_failed(uuid.UUID(job_id), exc):
            raise self.retry(exc=exc)
    finally:
        _prune_history()


@celery_app.task(
    bind=True,
    name="finalize_document",
    max_retries=3,
    retry_backoff=True,
    retry_jitter=True,
)
def finalize_document_task(self, job_id: str) -> None:
    """Phase two, triggered only after a human confirms the chunk preview."""
    from occupational_health.workers.pipeline import finalize_document

    settings = get_settings()
    try:
        finalize_document(uuid.UUID(job_id), settings)
    except Exception as exc:
        if isinstance(exc, DataError):
            _mark_failed(uuid.UUID(job_id), exc, terminal=True)
            return
        if _mark_failed(uuid.UUID(job_id), exc):
            raise self.retry(exc=exc)
    finally:
        _prune_history()


@celery_app.task(bind=True, name="cancel_document", max_retries=1)
def cancel_document_task(self, job_id: str) -> None:
    try:
        with SessionLocal() as db:
            job = db.get(ProcessingJob, uuid.UUID(job_id))
            if job and job.status not in (
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.PARTIAL_SUCCESS,
                JobStatus.CANCELLED,
            ):
                job.status = JobStatus.CANCELLED
                db.commit()
    finally:
        _prune_history()
