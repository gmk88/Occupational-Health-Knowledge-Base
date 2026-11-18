"""Processing-job history retention.

Only the newest ``keep`` jobs are shown in the task list; older terminal jobs are
removed together with their events. Quality reports are kept on purpose: they
belong to the document version, not to the task record.
"""

from __future__ import annotations

from sqlalchemy import delete, select

from occupational_health.db.models.jobs import JobEvent, ProcessingJob
from occupational_health.db.session import SessionLocal
from occupational_health.domain.enums import JobStatus

TERMINAL_STATUSES = frozenset(
    {
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.PARTIAL_SUCCESS,
        JobStatus.CANCELLED,
    }
)


def select_dropped(
    jobs: list[ProcessingJob], keep: int
) -> list[ProcessingJob]:
    """Pick jobs to delete from a list sorted newest-first.

    Non-terminal jobs are never dropped, even when they fall outside the
    retention window: their task may still be running.
    """
    if keep <= 0:
        return []
    return [job for job in jobs[keep:] if job.status in TERMINAL_STATUSES]


def prune_job_history(keep: int) -> int:
    """Delete terminal jobs beyond the newest ``keep``. Returns removed count."""
    if keep <= 0:
        return 0
    with SessionLocal() as db:
        jobs = list(
            db.scalars(
                select(ProcessingJob).order_by(
                    ProcessingJob.created_at.desc(), ProcessingJob.id.desc()
                )
            )
        )
        dropped = select_dropped(jobs, keep)
        if not dropped:
            return 0
        ids = [job.id for job in dropped]
        db.execute(delete(JobEvent).where(JobEvent.job_id.in_(ids)))
        db.execute(delete(ProcessingJob).where(ProcessingJob.id.in_(ids)))
        db.commit()
        return len(ids)
