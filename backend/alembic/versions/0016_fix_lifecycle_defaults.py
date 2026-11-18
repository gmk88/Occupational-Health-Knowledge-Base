"""Normalise lifecycle enum values.

Revision ID: 0016_fix_lifecycle_defaults
Revises: 0015_document_lifecycle
"""

from alembic import op
from sqlalchemy import text

revision = "0016_fix_lifecycle_defaults"
down_revision = "0015_document_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text("UPDATE documents SET lifecycle_status = 'CURRENT' WHERE lifecycle_status = 'current'")
    )
    op.execute(
        text("UPDATE documents SET document_role = 'MAIN' WHERE document_role = 'main'")
    )
    op.alter_column(
        "documents",
        "lifecycle_status",
        server_default="CURRENT",
        existing_type=__import__("sqlalchemy").String(20),
        existing_nullable=False,
    )
    op.alter_column(
        "documents",
        "document_role",
        server_default="MAIN",
        existing_type=__import__("sqlalchemy").String(20),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute(
        text("UPDATE documents SET lifecycle_status = 'current' WHERE lifecycle_status = 'CURRENT'")
    )
    op.execute(
        text("UPDATE documents SET document_role = 'main' WHERE document_role = 'MAIN'")
    )
