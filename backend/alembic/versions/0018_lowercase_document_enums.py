"""Normalise document enums to lowercase values.

Revision ID: 0018_lowercase_document_enums
Revises: 0017_chunk_anchors
"""

from alembic import op
from sqlalchemy import String, text

revision = "0018_lowercase_document_enums"
down_revision = "0017_chunk_anchors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("UPDATE documents SET lifecycle_status = 'current' WHERE lifecycle_status = 'CURRENT'"))
    op.execute(text("UPDATE documents SET document_role = 'main' WHERE document_role = 'MAIN'"))
    op.alter_column(
        "documents",
        "lifecycle_status",
        server_default="current",
        existing_type=String(20),
        existing_nullable=False,
    )
    op.alter_column(
        "documents",
        "document_role",
        server_default="main",
        existing_type=String(20),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute(text("UPDATE documents SET lifecycle_status = 'CURRENT' WHERE lifecycle_status = 'current'"))
    op.execute(text("UPDATE documents SET document_role = 'MAIN' WHERE document_role = 'main'"))
