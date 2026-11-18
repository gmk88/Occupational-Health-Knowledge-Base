from __future__ import annotations

import hashlib
import uuid

from occupational_health.db.models.retrieval import SearchAudit
from occupational_health.db.session import SessionLocal
from occupational_health.domain.enums import ActorType, RetrievalMode


def record_search(
    actor_type: ActorType,
    actor_id: uuid.UUID,
    request_id: str,
    mode: RetrievalMode,
    query: str,
    filters: dict,
    top_k: int,
    result_count: int,
    took_ms: int,
    degraded: bool,
    degraded_sources: list[str],
) -> None:
    with SessionLocal() as db:
        db.add(
            SearchAudit(
                request_id=request_id,
                actor_type=actor_type,
                actor_id=actor_id,
                mode=mode,
                query_hash=hashlib.sha256(query.encode("utf-8")).hexdigest(),
                query_length=len(query),
                filters=filters,
                top_k=top_k,
                result_count=result_count,
                took_ms=took_ms,
                degraded=degraded,
                degraded_sources=degraded_sources,
            )
        )
        db.commit()


class RetrievalAuditService:
    def record_search(self, *args, **kwargs) -> None:
        record_search(*args, **kwargs)
