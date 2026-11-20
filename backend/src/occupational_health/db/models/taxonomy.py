from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from occupational_health.db.models.enum_type import value_enum
from occupational_health.db.session import Base, utcnow
from occupational_health.domain.enums import RelationKind


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    normalized_name: Mapped[str] = mapped_column(String(100), unique=True)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tags.id", ondelete="SET NULL")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class DocumentTag(Base):
    __tablename__ = "document_tags"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class DocumentRelation(Base):
    __tablename__ = "document_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_document_id",
            "target_document_id",
            "relation_type",
            name="uq_document_relation",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    target_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    relation_type: Mapped[RelationKind] = mapped_column(
        value_enum(RelationKind, 30), index=True
    )
    volume_no: Mapped[str | None] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )