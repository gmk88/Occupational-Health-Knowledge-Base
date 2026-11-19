from __future__ import annotations

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    category_ids: list[str] = Field(default_factory=list, max_length=100)
    tag_ids: list[str] = Field(default_factory=list, max_length=100)
    # 物理过滤返回格式：text 正文 / table 表格（table 兼容历史 table_row、table_summary）。
    block_types: list[str] = Field(default_factory=list, max_length=10)
    # 自动识别场景只用于排序加权，不作为硬过滤。
    scenario_ids: list[str] = Field(default_factory=list, max_length=20)
    include_replaced: bool = False
    uploaded_from: str | None = None
    uploaded_to: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=512)
    mode: str = "hybrid"
    top_k: int = Field(default=5, ge=1, le=5)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    include_raw: bool = False
    rrf_k: int | None = None


class SearchResult(BaseModel):
    chunk_id: str
    matched_chunk_id: str | None = None
    text: str
    document_id: str
    document_name: str
    version_number: int
    page_start: int
    page_end: int
    category: dict | None = None
    tags: list[dict] = []
    lifecycle_status: str = "current"
    document_role: str = "main"
    standard_no: str | None = None
    related_documents: list[dict] = []
    amendment_notice: str | None = None
    source_location: dict | None = None
    scores: dict
    recall_sources: list[str]
    highlights: list[dict]
    kind: str = "chunk"  # "chunk" | "table"
    table: dict | None = None


class SearchData(BaseModel):
    items: list[SearchResult]
    total: int
    took_ms: int
    mode: str
    ranking: str
    degraded: bool
    degraded_sources: list[str]
    suggestions: list[str]
