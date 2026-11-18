"""Add chunk role for parent-child retrieval.

Revision ID: 0013_chunk_parent_child
Revises: 0012_access_admin
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_chunk_parent_child"
down_revision = "0012_access_admin"
branch_labels = None
depends_on = None


def _indexes(table: str) -> set[str]:
    bind = op.get_bind()
    return {item["name"] for item in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    existing = _indexes("chunks")
    if "chunk_role" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("chunks")}:
        op.add_column(
            "chunks",
            sa.Column(
                "chunk_role",
                sa.String(length=16),
                nullable=False,
                server_default="leaf",
            ),
        )
    if "ix_chunks_parent_chunk_id" not in existing:
        op.create_index("ix_chunks_parent_chunk_id", "chunks", ["parent_chunk_id"])
    if "ix_chunks_chunk_role" not in existing:
        op.create_index("ix_chunks_chunk_role", "chunks", ["chunk_role"])


def downgrade() -> None:
    existing = _indexes("chunks")
    if "ix_chunks_chunk_role" in existing:
        op.drop_index("ix_chunks_chunk_role", table_name="chunks")
    if "ix_chunks_parent_chunk_id" in existing:
        op.drop_index("ix_chunks_parent_chunk_id", table_name="chunks")
    op.drop_column("chunks", "chunk_role")
