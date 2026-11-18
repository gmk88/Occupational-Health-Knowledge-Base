"""Add document lifecycle metadata and relations.

Revision ID: 0015_document_lifecycle
Revises: 0014_scenario_taxonomy
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_document_lifecycle"
down_revision = "0014_scenario_taxonomy"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_column("documents", "standard_key"):
        op.add_column("documents", sa.Column("standard_key", sa.String(100), nullable=True))
    if not _has_column("documents", "standard_no"):
        op.add_column("documents", sa.Column("standard_no", sa.String(120), nullable=True))
    if not _has_column("documents", "edition_year"):
        op.add_column("documents", sa.Column("edition_year", sa.Integer(), nullable=True))
    if not _has_column("documents", "lifecycle_status"):
        op.add_column(
            "documents",
            sa.Column(
                "lifecycle_status",
                sa.String(20),
                nullable=False,
                server_default="CURRENT",
            ),
        )
    if not _has_column("documents", "document_role"):
        op.add_column(
            "documents",
            sa.Column(
                "document_role",
                sa.String(20),
                nullable=False,
                server_default="MAIN",
            ),
        )
    if not _has_column("documents", "issue_date"):
        op.add_column("documents", sa.Column("issue_date", sa.DateTime(timezone=True), nullable=True))
    if not _has_column("documents", "effective_date"):
        op.add_column("documents", sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True))

    if not _has_column("document_versions", "standard_no"):
        op.add_column("document_versions", sa.Column("standard_no", sa.String(120), nullable=True))
    if not _has_column("document_versions", "edition_year"):
        op.add_column("document_versions", sa.Column("edition_year", sa.Integer(), nullable=True))
    if not _has_column("document_versions", "effective_date"):
        op.add_column(
            "document_versions",
            sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        )
    if not _has_column("document_versions", "change_note"):
        op.add_column("document_versions", sa.Column("change_note", sa.Text(), nullable=True))
    if not _has_column("document_versions", "replaces_version_id"):
        op.add_column(
            "document_versions",
            sa.Column("replaces_version_id", sa.UUID(), nullable=True),
        )

    op.execute("CREATE INDEX IF NOT EXISTS ix_documents_standard_key ON documents (standard_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_documents_standard_no ON documents (standard_no)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_documents_lifecycle_status ON documents (lifecycle_status)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_documents_document_role ON documents (document_role)")

    if not _has_table("document_relations"):
        op.create_table(
            "document_relations",
            sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column(
                "source_document_id",
                sa.UUID(),
                sa.ForeignKey("documents.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "target_document_id",
                sa.UUID(),
                sa.ForeignKey("documents.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("relation_type", sa.String(30), nullable=False),
            sa.Column("volume_no", sa.String(30), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "source_document_id",
                "target_document_id",
                "relation_type",
                name="uq_document_relation",
            ),
        )
        op.create_index(
            "ix_document_relations_source",
            "document_relations",
            ["source_document_id"],
        )
        op.create_index(
            "ix_document_relations_target",
            "document_relations",
            ["target_document_id"],
        )
        op.create_index(
            "ix_document_relations_type",
            "document_relations",
            ["relation_type"],
        )


def downgrade() -> None:
    if _has_table("document_relations"):
        op.drop_table("document_relations")
    for table, column in (
        ("document_versions", "replaces_version_id"),
        ("document_versions", "change_note"),
        ("document_versions", "effective_date"),
        ("document_versions", "edition_year"),
        ("document_versions", "standard_no"),
        ("documents", "effective_date"),
        ("documents", "issue_date"),
        ("documents", "document_role"),
        ("documents", "lifecycle_status"),
        ("documents", "edition_year"),
        ("documents", "standard_no"),
        ("documents", "standard_key"),
    ):
        if _has_column(table, column):
            op.drop_column(table, column)
