from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    category_id: str | None = None
    tags: list[str] | None = Field(default=None, max_length=50)
    source: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)


class DocumentLifecyclePatch(BaseModel):
    lifecycle_status: str | None = Field(default=None, max_length=20)
    document_role: str | None = Field(default=None, max_length=20)
    standard_key: str | None = Field(default=None, max_length=100)
    standard_no: str | None = Field(default=None, max_length=120)
    edition_year: int | None = Field(default=None, ge=1900, le=2100)
    effective_date: str | None = None
    change_note: str | None = Field(default=None, max_length=2000)


class DocumentRelationCreate(BaseModel):
    target_document_id: str
    relation_type: str = Field(min_length=1, max_length=30)
    volume_no: str | None = Field(default=None, max_length=30)
    note: str | None = Field(default=None, max_length=2000)