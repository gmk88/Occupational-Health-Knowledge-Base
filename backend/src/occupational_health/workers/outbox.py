from __future__ import annotations

import logging

from occupational_health.db.models.operations import OutboxEvent
from occupational_health.db.repositories.outbox import OutboxRepository
from occupational_health.db.session import SessionLocal

logger = logging.getLogger(__name__)


def run_outbox(limit: int = 50) -> int:
    processed = 0
    with SessionLocal() as db:
        repository = OutboxRepository(db)
        for event in repository.claim(limit):
            try:
                handle(event)
                repository.mark_done(event)
                processed += 1
            except Exception as exc:
                logger.warning(
                    "outbox event failed", extra={"event_type": event.event_type}
                )
                repository.mark_retry(event, str(exc)[:500])
        db.commit()
    return processed


def handle(event: OutboxEvent) -> None:
    from qdrant_client import QdrantClient

    from occupational_health.core.config import get_settings
    from occupational_health.services.indexing.qdrant import QdrantIndexer

    settings = get_settings()
    client = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value()
    )
    indexer = QdrantIndexer(client)
    if event.event_type in ("index.hide", "index.purge"):
        revisions = event.payload.get("pipeline_revisions") or []
        if not revisions and event.payload.get("pipeline_revision"):
            revisions = [event.payload["pipeline_revision"]]
        for revision in revisions:
            indexer.hide_revision(revision)
        if not revisions and event.payload.get("document_id"):
            indexer.hide_document(event.payload["document_id"])
    elif event.event_type == "file.purge":
        from occupational_health.storage.files import PrivateFileStorage

        storage = PrivateFileStorage(settings.storage_root)
        storage.delete(event.payload.get("storage_key", ""))
