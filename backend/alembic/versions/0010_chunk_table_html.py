"""Store the original table HTML from structured parsers.

Revision ID: 0010_chunk_table_html
Revises: 0009_chunk_table_groups
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_chunk_table_html"
down_revision = "0009_chunk_table_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("table_html", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "table_html")
