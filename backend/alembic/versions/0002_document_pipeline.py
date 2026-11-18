"""Document, version, page, chunk, masking, job and quality tables.

Revision ID: 0002_document_pipeline
Revises: 0001_foundation
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_document_pipeline"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def _columns_ts() -> list[sa.Column]:
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *_columns_ts(),
    )
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("normalized_name", sa.String(100), nullable=False, unique=True),
        sa.Column("merged_into_id", sa.Uuid(), sa.ForeignKey("tags.id", ondelete="SET NULL")),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "stored_files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("storage_key", sa.String(500), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(300), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False, server_default="application/pdf"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purge_after", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("category_id", sa.Uuid(), sa.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source", sa.String(500)),
        sa.Column("notes", sa.Text()),
        sa.Column("uploader_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("current_version_id", sa.Uuid()),
        sa.Column("active_pipeline_revision", sa.Uuid()),
        sa.Column("activation_epoch", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("masking_revision", sa.Integer(), nullable=False, server_default="0"),
        *_columns_ts(),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_uploader_id", "documents", ["uploader_id"])
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("stored_files.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("quality_summary", postgresql.JSONB()),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("document_id", "version_number", name="uq_version_number"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.create_table(
        "document_fingerprints",
        sa.Column("sha256", sa.String(64), primary_key=True),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("initial_version_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_document_fingerprints_document_id", "document_fingerprints", ["document_id"])
    op.create_table(
        "document_tags",
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Uuid(), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "pages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pipeline_revision", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("cleaned_text", sa.Text(), nullable=False),
        sa.Column("masked_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("masking_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("effective_char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("noise_char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ocr_confidence", sa.Numeric(4, 3)),
        sa.Column("layout_warning_codes", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("failure_code", sa.String(50)),
        sa.Column("safe_failure_message", sa.String(500)),
        sa.Column("offset_map", postgresql.JSONB(), nullable=False),
        *_columns_ts(),
        sa.UniqueConstraint("version_id", "pipeline_revision", "page_number", name="uq_page"),
    )
    op.create_table(
        "masking_annotations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.Uuid(), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.Uuid()),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("base_text_hash", sa.String(64), nullable=False),
        sa.Column("sensitive_type", sa.String(20), nullable=False),
        sa.Column("replacement", sa.String(100), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False, server_default="rule"),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="accepted"),
        sa.Column("reviewer_id", sa.Uuid()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        *_columns_ts(),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pipeline_revision", sa.Uuid(), nullable=False),
        sa.Column("chunker_version", sa.String(50), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("source_types", postgresql.JSONB(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("masked_text", sa.Text(), nullable=False),
        sa.Column("page_offsets", postgresql.JSONB(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("masking_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_model", sa.String(200), nullable=False),
        sa.Column("embedding_revision", sa.String(100), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False, server_default="1024"),
        sa.Column("index_visible", sa.Boolean(), nullable=False, server_default="false"),
        *_columns_ts(),
        sa.UniqueConstraint("version_id", "pipeline_revision", "chunker_version", "ordinal", name="uq_chunk"),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_pipeline_revision", "chunks", ["pipeline_revision"])
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey("document_versions.id", ondelete="CASCADE")),
        sa.Column("job_type", sa.String(20), nullable=False),
        sa.Column("trigger_source", sa.String(20), nullable=False, server_default="web"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("current_stage", sa.String(20), nullable=False, server_default="validation"),
        sa.Column("pipeline_revision", sa.Uuid(), nullable=False),
        sa.Column("target_activation_epoch", sa.Integer(), nullable=False),
        sa.Column("input_fingerprint", sa.String(128), nullable=False),
        sa.Column("total_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("retry_of_job_id", sa.Uuid()),
        sa.Column("celery_task_id", sa.String(100)),
        sa.Column("requested_by", sa.Uuid()),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(50)),
        sa.Column("safe_error_message", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_processing_jobs_document_id", "processing_jobs", ["document_id"])
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])
    op.create_table(
        "job_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(30), nullable=False),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("safe_details", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("job_id", "sequence", name="uq_job_event"),
    )
    op.create_table(
        "quality_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_revision", sa.Uuid(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("effective_char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ocr_page_ratio", sa.Numeric(4, 3), nullable=False, server_default="0"),
        sa.Column("average_ocr_confidence", sa.Numeric(4, 3)),
        sa.Column("noise_char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processing_duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("low_quality_pages", postgresql.JSONB(), nullable=False),
        sa.Column("failed_pages", postgresql.JSONB(), nullable=False),
        sa.Column("report_schema_version", sa.String(20), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in ("quality_reports", "job_events", "processing_jobs", "chunks", "masking_annotations", "pages", "document_tags", "document_fingerprints", "document_versions", "documents", "stored_files", "tags", "categories"):
        op.drop_table(table)
