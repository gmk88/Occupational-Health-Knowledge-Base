"""Normalise all string-backed enum columns to lowercase values.

Revision ID: 0019_normalize_all_enum_values
Revises: 0018_lowercase_document_enums
"""

from alembic import op
from sqlalchemy import text

revision = "0019_normalize_all_enum_values"
down_revision = "0018_lowercase_document_enums"
branch_labels = None
depends_on = None

COLUMNS = [
    ("api_clients", "status"),
    ("audit_logs", "actor_type"),
    ("chunk_anchors", "anchor_type"),
    ("chunk_anchors", "match_method"),
    ("chunk_anchors", "status"),
    ("chunks", "chunk_role"),
    ("document_fingerprints", "state"),
    ("document_relations", "relation_type"),
    ("document_versions", "status"),
    ("documents", "status"),
    ("documents", "lifecycle_status"),
    ("documents", "document_role"),
    ("job_events", "from_status"),
    ("job_events", "to_status"),
    ("job_events", "stage"),
    ("masking_annotations", "sensitive_type"),
    ("masking_annotations", "origin"),
    ("masking_annotations", "review_status"),
    ("pages", "status"),
    ("pages", "source_type"),
    ("processing_jobs", "status"),
    ("processing_jobs", "current_stage"),
    ("processing_jobs", "job_type"),
    ("processing_jobs", "chunk_mode"),
    ("search_audits", "actor_type"),
    ("search_audits", "mode"),
    ("users", "role"),
    ("users", "status"),
]


def upgrade() -> None:
    for table, column in COLUMNS:
        op.execute(
            text(
                f'UPDATE {table} SET "{column}" = lower("{column}") '
                f'WHERE "{column}" IS NOT NULL AND "{column}" <> lower("{column}")'
            )
        )


def downgrade() -> None:
    pass
