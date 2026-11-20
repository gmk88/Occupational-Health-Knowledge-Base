from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from occupational_health.db.models.enum_type import value_enum
from occupational_health.db.session import Base, utcnow
from occupational_health.domain.enums import JobStage, JobStatus, JobType


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    job_type: Mapped[JobType] = mapped_column(value_enum(JobType, 20))
    trigger_source: Mapped[str] = mapped_column(String(20), default="web")
    chunk_mode: Mapped[str] = mapped_column(String(20), default="fixed")
    # 可选的逐任务切分参数；为空时由 pipeline 回退到全局 settings 默认值。
    chunk_target_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    chunk_max_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    chunk_overlap_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    status: Mapped[JobStatus] = mapped_column(
        value_enum(JobStatus, 20),
        default=JobStatus.QUEUED,
        index=True,
    )
    current_stage: Mapped[JobStage] = mapped_column(
        value_enum(JobStage, 20), default=JobStage.VALIDATION
    )
    pipeline_revision: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, index=True)
    target_activation_epoch: Mapped[int] = mapped_column(Integer)
    input_fingerprint: Mapped[str] = mapped_column(String(128))
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    processed_pages: Mapped[int] = mapped_column(Integer, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    retry_of_job_id: Mapped[uuid.UUID | None] = mapped_column()
    celery_task_id: Mapped[str | None] = mapped_column(String(100))
    requested_by: Mapped[uuid.UUID | None] = mapped_column()
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(50))
    safe_error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (UniqueConstraint("job_id", "sequence", name="uq_job_event"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    from_status: Mapped[str] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30))
    stage: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(500))
    safe_details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class QualityReport(Base):
    __tablename__ = "quality_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(index=True)
    pipeline_revision: Mapped[uuid.UUID] = mapped_column()
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    effective_char_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    ocr_page_ratio: Mapped[float] = mapped_column(Numeric(4, 3), default=0)
    average_ocr_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    noise_char_count: Mapped[int] = mapped_column(Integer, default=0)
    processing_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    low_quality_pages: Mapped[list] = mapped_column(JSONB, default=list)
    failed_pages: Mapped[list] = mapped_column(JSONB, default=list)
    report_schema_version: Mapped[str] = mapped_column(String(20), default="1.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
