from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from occupational_health.db.session import Base, utcnow
from occupational_health.domain.enums import ActorType, RetrievalMode


def _enum_values(enum_cls):
    return [member.value for member in enum_cls]


class SearchAudit(Base):
    __tablename__ = "search_audits"
    __table_args__ = (
        Index("ix_search_audits_actor_created", "actor_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(
            ActorType,
            native_enum=False,
            length=20,
            values_callable=_enum_values,
        )
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(index=True)
    mode: Mapped[RetrievalMode] = mapped_column(
        Enum(
            RetrievalMode,
            native_enum=False,
            length=20,
            values_callable=_enum_values,
        )
    )
    query_hash: Mapped[str] = mapped_column(String(64))
    query_length: Mapped[int] = mapped_column(Integer)
    filters: Mapped[dict] = mapped_column(JSONB, default=dict)
    top_k: Mapped[int] = mapped_column(Integer)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    took_ms: Mapped[int] = mapped_column(Integer, default=0)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    degraded_sources: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
