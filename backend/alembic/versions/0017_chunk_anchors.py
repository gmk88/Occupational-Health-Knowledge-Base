"""Add chunk anchors for source tracing.

Revision ID: 0017_chunk_anchors
Revises: 0016_fix_lifecycle_defaults
"""

from alembic import op
import sqlalchemy as sa

revision = "0017_chunk_anchors"
down_revision = "0016_fix_lifecycle_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chunk_anchors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("pipeline_revision", sa.UUID(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=False, server_default=""),
        sa.Column("quote_hash", sa.String(64), nullable=False),
        sa.Column("anchor_type", sa.String(30), nullable=False, server_default="text"),
        sa.Column("match_method", sa.String(30), nullable=False, server_default="exact"),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chunk_id",
            "page_number",
            "start_offset",
            "end_offset",
            "anchor_type",
            name="uq_chunk_anchor",
        ),
    )
    op.create_index("ix_chunk_anchors_chunk_id", "chunk_anchors", ["chunk_id"])
    op.create_index("ix_chunk_anchors_version_id", "chunk_anchors", ["version_id"])
    op.create_index(
        "ix_chunk_anchors_pipeline_revision",
        "chunk_anchors",
        ["pipeline_revision"],
    )
    op.create_index("ix_chunk_anchors_quote_hash", "chunk_anchors", ["quote_hash"])
    op.create_index("ix_chunk_anchors_anchor_type", "chunk_anchors", ["anchor_type"])
    op.create_index("ix_chunk_anchors_status", "chunk_anchors", ["status"])


def downgrade() -> None:
    op.drop_table("chunk_anchors")
