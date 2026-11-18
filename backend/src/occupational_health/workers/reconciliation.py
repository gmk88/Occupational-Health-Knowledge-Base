from __future__ import annotations

import logging

from qdrant_client import QdrantClient
from qdrant_client.http import models
from sqlalchemy import select

from occupational_health.core.config import get_settings
from occupational_health.db.models.documents import Document
from occupational_health.db.session import SessionLocal
from occupational_health.services.indexing.schema import COLLECTION

logger = logging.getLogger(__name__)


def reconcile() -> dict:
    settings = get_settings()
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value(),
    )
    with SessionLocal() as db:
        documents = db.scalars(select(Document).where(Document.status == "deleted"))
        deleted_ids = [str(document.id) for document in documents]
    removed = 0
    if deleted_ids:
        condition = models.FieldCondition(
            key="document_id",
            match=models.MatchAny(any=deleted_ids),
        )
        result = client.delete(
            COLLECTION,
            points_selector=models.FilterSelector(filter=models.Filter(must=[condition])),
        )
        removed = len(result.result) if result and result.result else 0
    return {"orphan_points_removed": removed}


if __name__ == "__main__":
    print(reconcile())
