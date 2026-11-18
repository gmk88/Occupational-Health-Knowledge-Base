"""Add per-job chunk parameters and switch default chunk mode to fixed.

Revision ID: 0007_job_chunk_params
Revises: 0006_document_chunk_mode
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_job_chunk_params"
down_revision = "0006_document_chunk_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "processing_jobs",
        sa.Column("chunk_target_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("chunk_max_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "processing_jobs",
        sa.Column("chunk_overlap_tokens", sa.Integer(), nullable=True),
    )
    op.alter_column(
        "processing_jobs",
        "chunk_mode",
        server_default="fixed",
        existing_type=sa.String(20),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "processing_jobs",
        "chunk_mode",
        server_default="structure",
        existing_type=sa.String(20),
        existing_nullable=False,
    )
    op.drop_column("processing_jobs", "chunk_overlap_tokens")
    op.drop_column("processing_jobs", "chunk_max_tokens")
    op.drop_column("processing_jobs", "chunk_target_tokens")
