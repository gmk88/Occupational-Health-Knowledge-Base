"""Keep the pre-merge snapshot so manual chunk merges can be undone.

Revision ID: 0011_chunk_merged_snapshot
Revises: 0010_chunk_table_html
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_chunk_merged_snapshot"
down_revision = "0010_chunk_table_html"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column("merged_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chunks", "merged_snapshot")
