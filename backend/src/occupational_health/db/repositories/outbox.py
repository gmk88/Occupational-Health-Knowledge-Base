from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from occupational_health.db.models.operations import OutboxEvent
from occupational_health.db.session import utcnow


class OutboxRepository:
    def __init__(self, db) -> None:
        self.db = db

    def enqueue(
        self,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        event_type: str,
        payload: dict,
    ) -> OutboxEvent:
        event = OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
        )
        self.db.add(event)
        return event

    def claim(self, limit: int = 50) -> list[OutboxEvent]:
        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.processed_at.is_(None), OutboxEvent.available_at <= utcnow()
            )
            .order_by(OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = list(self.db.scalars(statement))
        for event in events:
            event.attempt_count += 1
        self.db.flush()
        return events

    def mark_done(self, event: OutboxEvent) -> None:
        event.processed_at = utcnow()
        event.last_error = None
        self.db.flush()

    def mark_retry(self, event: OutboxEvent, safe_error: str) -> None:
        event.available_at = utcnow() + timedelta(
            seconds=min(600, 2 ** min(event.attempt_count, 10))
        )
        event.last_error = safe_error[:500]
        self.db.flush()
