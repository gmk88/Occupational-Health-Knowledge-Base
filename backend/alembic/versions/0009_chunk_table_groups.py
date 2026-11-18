"""Add table-group identity, row order, caption and parent chunk reference.

Revision ID: 0009_chunk_table_groups
Revises: 0008_chunk_table_review
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_chunk_table_groups"
down_revision = "0008_chunk_table_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("table_id", sa.String(length=36), nullable=True))
    op.add_column("chunks", sa.Column("source_table_id", sa.String(length=36), nullable=True))
    op.add_column("chunks", sa.Column("row_index", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("section_title", sa.String(length=500), nullable=True))
    op.add_column("chunks", sa.Column("parent_chunk_id", sa.String(length=36), nullable=True))
    op.create_index("ix_chunks_table_id", "chunks", ["table_id"])


def downgrade() -> None:
    op.drop_index("ix_chunks_table_id", table_name="chunks")
    op.drop_column("chunks", "parent_chunk_id")
    op.drop_column("chunks", "section_title")
    op.drop_column("chunks", "row_index")
    op.drop_column("chunks", "source_table_id")
    op.drop_column("chunks", "table_id")
