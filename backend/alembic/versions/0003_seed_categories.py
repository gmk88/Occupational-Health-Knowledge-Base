"""Seed preset occupational-health categories.

Revision ID: 0003_seed_categories
Revises: 0002_document_pipeline
"""

import uuid
from datetime import datetime, timezone

from alembic import op
from sqlalchemy import text

revision = "0003_seed_categories"
down_revision = "0002_document_pipeline"
branch_labels = None
depends_on = None

CATEGORIES = [
    ("regulation_standard", "法规标准", 0),
    ("inspection_report", "检测评价报告", 1),
    ("health_surveillance", "职业健康监护", 2),
    ("chemical_sds", "化学品安全数据", 3),
    ("training_material", "培训材料", 4),
    ("other", "其他", 5),
]


def upgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    for code, name, order in CATEGORIES:
        connection.execute(
            text(
                "INSERT INTO categories (id, code, name, active, sort_order, created_at, updated_at) "
                "VALUES (:id, :code, :name, true, :sort, :now, :now) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"id": uuid.uuid4(), "code": code, "name": name, "sort": order, "now": now},
        )


def downgrade() -> None:
    op.execute("DELETE FROM categories WHERE code IN ('regulation_standard','inspection_report','health_surveillance','chemical_sds','training_material','other')")
