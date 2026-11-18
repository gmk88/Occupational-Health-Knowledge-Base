from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from occupational_health.core.logging import request_id_context
from occupational_health.db.models.operations import AuditLog
from occupational_health.db.session import SessionLocal
from occupational_health.domain.enums import ActorType

FORBIDDEN_METADATA = {
    "password",
    "token",
    "api_key",
    "raw_text",
    "query",
    "storage_key",
}


@dataclass
class MemoryAuditService:
    events: list[dict] = field(default_factory=list)

    def record(
        self,
        actor_type: ActorType,
        actor_id: uuid.UUID,
        action: str,
        object_type: str,
        object_id: str | None,
        result: str,
        metadata: dict | None = None,
    ) -> None:
        self.events.append(
            {
                "actor_type": actor_type.value,
                "actor_id": str(actor_id),
                "action": action,
                "object_type": object_type,
                "object_id": object_id,
                "result": result,
                "metadata": metadata or {},
                "created_at": datetime.now(UTC),
            }
        )


class AuditService:
    def record(
        self,
        actor_type: ActorType,
        actor_id: uuid.UUID,
        action: str,
        object_type: str,
        object_id: str | None,
        result: str,
        metadata: dict | None = None,
        db=None,
    ) -> None:
        safe_metadata = {
            key: value
            for key, value in (metadata or {}).items()
            if key not in FORBIDDEN_METADATA
        }
        event = AuditLog(
            request_id=request_id_context.get() or "system",
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            result=result,
            safe_metadata=safe_metadata,
        )
        if db is not None:
            db.add(event)
            return
        with SessionLocal() as session:
            session.add(event)
            session.commit()
