from __future__ import annotations

from types import SimpleNamespace

from occupational_health.domain.enums import JobStatus
from occupational_health.services.jobs.retention import select_dropped


def _jobs(*statuses: JobStatus) -> list:
    return [SimpleNamespace(status=status) for status in statuses]


def test_keeps_newest_n_terminal_jobs() -> None:
    jobs = _jobs(JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
    dropped = select_dropped(jobs, 2)
    assert [job.status for job in dropped] == [JobStatus.CANCELLED]


def test_never_drops_running_job() -> None:
    jobs = _jobs(JobStatus.COMPLETED, JobStatus.PARSING)
    assert select_dropped(jobs, 1) == []


def test_zero_disables_retention() -> None:
    jobs = _jobs(JobStatus.COMPLETED, JobStatus.COMPLETED)
    assert select_dropped(jobs, 0) == []
