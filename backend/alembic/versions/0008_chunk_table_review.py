"""Add table-row chunk metadata and manual-edit flag.

Revision ID: 0008_chunk_table_review
Revises: 0007_job_chunk_params
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_chunk_table_review"
down_revision = "0007_job_chunk_params"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "block_type",
            sa.String(length=20),
            nullable=False,
            server_default="text",
        ),
    )
    op.add_column(
        "chunks",
        sa.Column("table_header", sa.Text(), nullable=True),
    )
    op.add_column(
        "chunks",
        sa.Column(
            "is_edited",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("chunks", "is_edited")
    op.drop_column("chunks", "table_header")
    op.drop_column("chunks", "block_type")
