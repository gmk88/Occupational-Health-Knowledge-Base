"""Replace document-type categories with occupational-health scenarios.

Revision ID: 0014_scenario_taxonomy
Revises: 0013_chunk_parent_child
"""

from datetime import datetime, timezone
import uuid

from alembic import op
from sqlalchemy import text

revision = "0014_scenario_taxonomy"
down_revision = "0013_chunk_parent_child"
branch_labels = None
depends_on = None

SCENARIOS = [
    ("general", "通用", 0),
    ("dust", "粉尘危害", 1),
    ("chemical", "化学毒物", 2),
    ("physical", "物理因素", 3),
    ("health_surveillance", "职业健康监护", 4),
    ("assessment", "检测评价", 5),
    ("protection", "防护与应急", 6),
]

LEGACY_TYPE_TAGS = {
    "regulation_standard": "类型:法规标准",
    "inspection_report": "类型:检测评价",
    "health_surveillance": "类型:健康监护",
    "chemical_sds": "类型:化学品安全",
    "training_material": "类型:培训材料",
    "other": "类型:其他资料",
}

LEGACY_CATEGORIES = [
    ("regulation_standard", "法规标准", 0),
    ("inspection_report", "检测评价报告", 1),
    ("health_surveillance", "职业健康监护", 2),
    ("chemical_sds", "化学品安全数据", 3),
    ("training_material", "培训材料", 4),
    ("other", "其他", 5),
]


def _ensure_category(connection, code: str, name: str, order: int, now: datetime) -> uuid.UUID:
    row = connection.execute(
        text(
            """
            INSERT INTO categories (id, code, name, active, sort_order, created_at, updated_at)
            VALUES (:id, :code, :name, true, :sort, :now, :now)
            ON CONFLICT (code) DO UPDATE
            SET name = excluded.name,
                active = true,
                sort_order = excluded.sort_order,
                updated_at = excluded.updated_at
            RETURNING id
            """
        ),
        {"id": uuid.uuid4(), "code": code, "name": name, "sort": order, "now": now},
    ).fetchone()
    return row[0]


def _ensure_tag(connection, name: str, now: datetime) -> uuid.UUID:
    normalized = name.strip().casefold()
    row = connection.execute(
        text(
            """
            INSERT INTO tags (id, name, normalized_name, created_at)
            VALUES (:id, :name, :normalized, :now)
            ON CONFLICT (normalized_name) DO NOTHING
            RETURNING id
            """
        ),
        {"id": uuid.uuid4(), "name": name, "normalized": normalized, "now": now},
    ).fetchone()
    if row:
        return row[0]
    return connection.execute(
        text("SELECT id FROM tags WHERE normalized_name = :normalized"),
        {"normalized": normalized},
    ).scalar_one()


def upgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(timezone.utc)

    for code, name, order in SCENARIOS:
        _ensure_category(connection, code, name, order, now)

    tag_ids = {
        code: _ensure_tag(connection, name, now)
        for code, name in LEGACY_TYPE_TAGS.items()
    }

    rows = connection.execute(
        text(
            """
            SELECT d.id, c.code
            FROM documents d
            LEFT JOIN categories c ON c.id = d.category_id
            WHERE d.status <> 'deleted'
            """
        )
    ).all()
    for document_id, old_code in rows:
        tag_id = tag_ids.get(old_code)
        if tag_id:
            connection.execute(
                text(
                    """
                    INSERT INTO document_tags (document_id, tag_id)
                    VALUES (:document_id, :tag_id)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"document_id": document_id, "tag_id": tag_id},
            )

    general_id = connection.execute(
        text("SELECT id FROM categories WHERE code = 'general'")
    ).scalar_one()
    connection.execute(
        text("UPDATE documents SET category_id = :general_id"),
        {"general_id": general_id},
    )

    legacy_to_delete = [
        code for code in LEGACY_TYPE_TAGS if code != "health_surveillance"
    ]
    for code in legacy_to_delete:
        connection.execute(
            text("DELETE FROM categories WHERE code = :code"), {"code": code}
        )


def downgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(timezone.utc)

    for code, name, order in LEGACY_CATEGORIES:
        _ensure_category(connection, code, name, order, now)

    other_id = connection.execute(
        text("SELECT id FROM categories WHERE code = 'other'")
    ).scalar_one()
    connection.execute(
        text("UPDATE documents SET category_id = :other_id"), {"other_id": other_id}
    )

    for old_code, tag_name in LEGACY_TYPE_TAGS.items():
        category_id = connection.execute(
            text("SELECT id FROM categories WHERE code = :code"), {"code": old_code}
        ).scalar_one()
        tag = connection.execute(
            text("SELECT id FROM tags WHERE normalized_name = :name"),
            {"name": tag_name.casefold()},
        ).fetchone()
        if not tag:
            continue
        connection.execute(
            text(
                """
                UPDATE documents d
                SET category_id = :category_id
                FROM document_tags dt
                WHERE dt.document_id = d.id AND dt.tag_id = :tag_id
                """
            ),
            {"category_id": category_id, "tag_id": tag[0]},
        )

    for code, _name, _order in SCENARIOS:
        if code != "health_surveillance":
            connection.execute(
                text("DELETE FROM categories WHERE code = :code"), {"code": code}
            )
