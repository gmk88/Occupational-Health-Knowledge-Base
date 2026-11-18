"""Index search audits by actor so per-client usage queries stay fast.

Revision ID: 0012_access_admin
Revises: 0011_chunk_merged_snapshot
"""

from alembic import op

revision = "0012_access_admin"
down_revision = "0011_chunk_merged_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_search_audits_actor_created",
        "search_audits",
        ["actor_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_search_audits_actor_created", table_name="search_audits")
