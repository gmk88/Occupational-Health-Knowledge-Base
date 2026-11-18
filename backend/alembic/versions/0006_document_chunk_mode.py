"""Add chunk mode to processing jobs.

Revision ID: 0006_document_chunk_mode
Revises: 0005_api_clients
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_document_chunk_mode"
down_revision = "0005_api_clients"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "processing_jobs",
        sa.Column("chunk_mode", sa.String(20), nullable=False, server_default="structure"),
    )


def downgrade() -> None:
    op.drop_column("processing_jobs", "chunk_mode")
