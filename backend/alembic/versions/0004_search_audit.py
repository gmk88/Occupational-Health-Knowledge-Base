"""Search audit table.

Revision ID: 0004_search_audit
Revises: 0003_seed_categories
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_search_audit"
down_revision = "0003_seed_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_audits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("query_length", sa.Integer(), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("took_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("degraded_sources", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, columns in (("request_id", ["request_id"]), ("actor_id", ["actor_id"]), ("created_at", ["created_at"])):
        op.create_index(f"ix_search_audits_{name}", "search_audits", columns)


def downgrade() -> None:
    op.drop_table("search_audits")
