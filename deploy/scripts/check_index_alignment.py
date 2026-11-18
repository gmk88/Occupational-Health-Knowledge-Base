"""只读诊断：对比 PostgreSQL 可见 chunk 数与 Qdrant 集合点数。

用法（在 backend 目录执行）：
    .venv\\Scripts\\python.exe ..\\deploy\\scripts\\check_index_alignment.py

只报告差异，不修改任何数据。
"""

from __future__ import annotations

from qdrant_client import QdrantClient
from sqlalchemy import func, select

from occupational_health.core.config import get_settings
from occupational_health.db.models.content import Chunk
from occupational_health.db.session import SessionLocal
from occupational_health.services.indexing.schema import COLLECTION


def main() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        visible = (
            db.scalar(
                select(func.count())
                .select_from(Chunk)
                .where(Chunk.index_visible.is_(True))
            )
            or 0
        )
        total = db.scalar(select(func.count()).select_from(Chunk)) or 0

    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value(),
        timeout=10,
    )
    try:
        info = client.get_collection(COLLECTION)
        points = info.points_count
    finally:
        client.close()

    print(f"PostgreSQL chunks: total={total} visible={visible}")
    print(f"Qdrant points:     {points} (collection={COLLECTION})")
    if points is None:
        print("结论：Qdrant 未返回点数，无法对比。")
    elif points == visible:
        print("结论：可见 chunk 与索引点数一致。")
    else:
        print(
            f"结论：存在差异 {visible - points:+d}。"
            " 本脚本只读，不会自动重建索引；请结合最近任务日志人工确认。"
        )


if __name__ == "__main__":
    main()
