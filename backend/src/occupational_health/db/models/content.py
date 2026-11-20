from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from occupational_health.db.models.enum_type import value_enum
from occupational_health.db.session import Base, utcnow
from occupational_health.domain.enums import PageSource, PageStatus, SensitiveType


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint(
            "version_id", "pipeline_revision", "page_number", name="uq_page"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    pipeline_revision: Mapped[uuid.UUID] = mapped_column(index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    source_type: Mapped[PageSource] = mapped_column(value_enum(PageSource, 20))
    raw_text: Mapped[str] = mapped_column(Text)
    cleaned_text: Mapped[str] = mapped_column(Text)
    masked_text: Mapped[str] = mapped_column(Text, default="")
    masking_revision: Mapped[int] = mapped_column(Integer, default=0)
    effective_char_count: Mapped[int] = mapped_column(Integer, default=0)
    noise_char_count: Mapped[int] = mapped_column(Integer, default=0)
    ocr_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    layout_warning_codes: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[PageStatus] = mapped_column(
        value_enum(PageStatus, 20), default=PageStatus.PENDING
    )
    failure_code: Mapped[str | None] = mapped_column(String(50))
    safe_failure_message: Mapped[str | None] = mapped_column(String(500))
    offset_map: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class MaskingAnnotation(Base):
    __tablename__ = "masking_annotations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column()
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    base_text_hash: Mapped[str] = mapped_column(String(64))
    sensitive_type: Mapped[SensitiveType] = mapped_column(value_enum(SensitiveType, 20))
    replacement: Mapped[str] = mapped_column(String(100))
    origin: Mapped[str] = mapped_column(String(20), default="rule")
    review_status: Mapped[str] = mapped_column(String(20), default="accepted")
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column()
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "pipeline_revision",
            "chunker_version",
            "ordinal",
            name="uq_chunk",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    pipeline_revision: Mapped[uuid.UUID] = mapped_column(index=True)
    chunker_version: Mapped[str] = mapped_column(String(50))
    ordinal: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    source_types: Mapped[list] = mapped_column(JSONB, default=list)
    raw_text: Mapped[str] = mapped_column(Text)
    masked_text: Mapped[str] = mapped_column(Text)
    # "text" 正文；"table" 整表。历史数据里可能还有 "table_row"/"table_summary"。
    block_type: Mapped[str] = mapped_column(String(20), default="text")
    table_header: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 同一张表的所有行共享 table_id；跨页默认不合并（确认页可人工合并）。
    table_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # 原始表标识：人工合并后仍保留，用于「一键撤销合并」。
    source_table_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 父子块：parent 提供完整语义，child 用于检索命中；旧数据为 leaf。
    chunk_role: Mapped[str] = mapped_column(String(16), default="leaf", index=True)
    parent_chunk_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    # MinerU 等解析器给出的原始表格 HTML（含 rowspan/colspan），供确认页还原。
    table_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 人工合并前的原始块快照，用于确认页「一键撤销合并」。
    merged_snapshot: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # 人工在确认页修改过内容后标记，便于审计与复核。
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    page_offsets: Mapped[dict] = mapped_column(JSONB, default=dict)
    token_count: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    masking_revision: Mapped[int] = mapped_column(Integer, default=0)
    embedding_model: Mapped[str] = mapped_column(String(200))
    embedding_revision: Mapped[str] = mapped_column(String(100))
    embedding_dimensions: Mapped[int] = mapped_column(Integer, default=1024)
    index_visible: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ChunkAnchor(Base):
    """Locates a chunk inside the cleaned text of its source page."""

    __tablename__ = "chunk_anchors"
    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            "page_number",
            "start_offset",
            "end_offset",
            "anchor_type",
            name="uq_chunk_anchor",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(index=True)
    pipeline_revision: Mapped[uuid.UUID] = mapped_column(index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote: Mapped[str] = mapped_column(Text, default="")
    quote_hash: Mapped[str] = mapped_column(String(64), index=True)
    anchor_type: Mapped[str] = mapped_column(String(30), default="text", index=True)
    match_method: Mapped[str] = mapped_column(String(30), default="exact")
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=1)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
