from __future__ import annotations

import time
import uuid

from qdrant_client.http import models
from sqlalchemy import select

from occupational_health.core.logging import request_id_context
from occupational_health.db.models.documents import Document
from occupational_health.db.models.taxonomy import (
    Category,
    DocumentRelation,
    DocumentTag,
    Tag,
)
from occupational_health.db.session import SessionLocal
from occupational_health.services.retrieval.fusion import reciprocal_rank_fusion
from occupational_health.services.retrieval.highlights import find_highlights
from occupational_health.services.retrieval.terms import extract_exact_terms
from occupational_health.services.retrieval.validation import validate_query
from occupational_health.services.extraction.table_html import expand_rows, parse_html_table
from occupational_health.services.retrieval.visibility import visible_chunks


class RetrievalService:
    def __init__(
        self, settings, semantic=None, keyword=None, document_service=None, audit=None
    ) -> None:
        self.settings = settings
        self.semantic = semantic
        self.keyword = keyword
        self.document_service = document_service
        self.audit = audit

    def search(
        self,
        principal,
        query: str,
        mode: str,
        top_k: int,
        filters: dict,
        include_raw: bool,
    ) -> dict:
        from occupational_health.domain.enums import RetrievalMode

        query, resolved_mode, top_k = validate_query(
            query,
            self.settings.max_query_characters,
            mode,
            top_k,
            self.settings.max_top_k,
        )
        started = time.perf_counter()
        qdrant_filter = self._build_filter(filters)
        # 显式过滤后候选池可以减半；自动场景只加权，不缩小范围。
        has_scope = bool(filters.get("category_ids") or filters.get("tag_ids"))
        recall_multiplier = 10 if has_scope else 20
        recall_limit = max(self.settings.recall_candidates, top_k * recall_multiplier)
        degraded: list[str] = []

        def retrieve_with(qfilter):
            semantic_ranked: list[str] = []
            keyword_ranked: list[str] = []
            local_degraded: list[str] = []
            if resolved_mode in (RetrievalMode.SEMANTIC, RetrievalMode.HYBRID):
                try:
                    semantic_ranked = [
                        chunk_id
                        for chunk_id, _ in self.semantic.retrieve(
                            query, recall_limit, qfilter
                        )
                    ]
                except Exception:
                    local_degraded.append("semantic")
            if resolved_mode in (RetrievalMode.KEYWORD, RetrievalMode.HYBRID):
                try:
                    keyword_ranked = [
                        chunk_id
                        for chunk_id, _ in self.keyword.retrieve(
                            query,
                            recall_limit,
                            qfilter,
                            include_raw=include_raw,
                        )
                    ]
                except Exception:
                    local_degraded.append("keyword")
            ranked_lists = (
                [semantic_ranked, keyword_ranked]
                if resolved_mode == RetrievalMode.HYBRID
                else (
                    [semantic_ranked]
                    if resolved_mode == RetrievalMode.SEMANTIC
                    else [keyword_ranked]
                )
            )
            return (
                reciprocal_rank_fusion(ranked_lists, self.settings.rrf_k),
                semantic_ranked,
                keyword_ranked,
                local_degraded,
            )

        fused, semantic_ranked, keyword_ranked, degraded = retrieve_with(qdrant_filter)
        if not fused and has_scope:
            # 显式过滤无结果时回退全库，避免漏检。
            relaxed = models.Filter(
                must=[
                    models.FieldCondition(
                        key="index_visible", match=models.MatchValue(value=True)
                    )
                ]
            )
            fused, semantic_ranked, keyword_ranked, relaxed_degraded = retrieve_with(relaxed)
            degraded.extend(item for item in relaxed_degraded if item not in degraded)
            degraded.append("filter_relaxed")
        if len(degraded) >= 2 and {"semantic", "keyword"}.issubset(set(degraded)):
            from occupational_health.core.errors import ApiError

            raise ApiError(503, "INDEX_UNAVAILABLE", "检索服务暂时不可用，请稍后重试")
        chunk_ids = [
            uuid.UUID(chunk_id)
            for chunk_id, _ in fused[:recall_limit]
        ]
        visible = visible_chunks(chunk_ids)
        parent_ids = [
            uuid.UUID(record["parent_chunk_id"])
            for record in visible.values()
            if record.get("parent_chunk_id")
        ]
        parents = visible_chunks(parent_ids) if parent_ids else {}
        contexts = self._contexts(
            {
                item["document_id"]
                for item in [*visible.values(), *parents.values()]
            }
        )
        terms = (
            extract_exact_terms(query)
            or [token for token in query.split() if len(token) >= 2][:8]
        )
        items = []
        seen_targets: set[uuid.UUID] = set()
        scenario_ids = {str(value) for value in filters.get("scenario_ids") or []}
        for chunk_id, _score in fused:
            child_id = uuid.UUID(chunk_id)
            child = visible.get(child_id)
            if not child or not child.get("parent_chunk_id"):
                record = child
                target_id = child_id
            else:
                target_id = uuid.UUID(child["parent_chunk_id"])
                record = parents.get(target_id)
                if not record:
                    record = child
                    target_id = child_id
            if not record or target_id in seen_targets:
                continue
            seen_targets.add(target_id)
            text = record["raw_text"] if include_raw else record["text"]
            context = contexts.get(record["document_id"], {})
            common = {
                "chunk_id": str(target_id),
                "matched_chunk_id": str(child_id),
                "text": text,
                "document_id": str(record["document_id"]),
                "document_name": context.get("name", ""),
                "version_number": record["version_number"],
                "page_start": record["page_start"],
                "page_end": record["page_end"],
                "category": context.get("category"),
                "tags": context.get("tags", []),
                "lifecycle_status": context.get("lifecycle_status", "current"),
                "document_role": context.get("document_role", "main"),
                "standard_no": context.get("standard_no"),
                "related_documents": context.get("related_documents", []),
                "amendment_notice": context.get("amendment_notice"),
                "scores": {"rrf": round(_score, 4)},
                "recall_sources": (
                    ["semantic"]
                    if chunk_id in semantic_ranked and chunk_id not in keyword_ranked
                    else ["keyword"]
                ),
                "highlights": find_highlights(text, terms),
            }
            category = common.get("category") or {}
            boost = 1.1 if scenario_ids and str(category.get("id")) in scenario_ids else 1.0
            if common.get("document_role") in {"amendment", "corrigendum", "supplement"}:
                boost *= 1.05
            if common.get("lifecycle_status") in {"replaced", "abolished", "superseded"}:
                boost *= 0.8
            # 自动场景、修改单和状态只改变排序，不参与 Qdrant 过滤。
            rank_score = _score * boost
            # 整表一个 chunk；历史 table_row / table_summary 按普通文本块兼容返回。
            if record["block_type"] == "table":
                item = {**common, "kind": "table", "table": _table_payload(record)}
            else:
                item = {**common, "kind": "chunk"}
            item["_rank_score"] = rank_score
            items.append(item)
        items.sort(key=lambda item: item.pop("_rank_score", 0), reverse=True)
        items = items[:top_k]
        took_ms = round((time.perf_counter() - started) * 1000)
        self._audit(
            principal,
            query,
            resolved_mode,
            filters,
            top_k,
            len(items),
            took_ms,
            degraded,
        )
        suggestions = []
        if not items:
            suggestions = ["change_keywords", "relax_filters", "switch_mode"]
        return {
            "items": items,
            "total": len(items),
            "took_ms": took_ms,
            "mode": resolved_mode.value,
            "ranking": f"RRF(k={self.settings.rrf_k}), equal weights",
            "degraded": bool(degraded),
            "degraded_sources": degraded,
            "suggestions": suggestions,
        }

    def _build_filter(self, filters: dict) -> models.Filter | None:
        must: list[models.Condition] = [
            models.FieldCondition(
                key="index_visible", match=models.MatchValue(value=True)
            )
        ]
        if not filters.get("include_replaced"):
            must.append(
                models.FieldCondition(
                    key="lifecycle_status",
                    match=models.MatchAny(any=["current", "pending"]),
                )
            )
        # scenario_ids 只用于排序加权，不能写入 Qdrant filter。
        if filters.get("document_ids"):
            must.append(
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchAny(
                        any=[str(value) for value in filters["document_ids"]]
                    ),
                )
            )
        if filters.get("category_ids"):
            category_ids = [str(value) for value in filters["category_ids"]]
            # 场景过滤默认包含通用场景，避免漏掉普适标准。
            with SessionLocal() as db:
                general = db.scalar(
                    select(Category).where(
                        Category.code == "general", Category.active.is_(True)
                    )
                )
            if general and str(general.id) not in category_ids:
                category_ids.append(str(general.id))
            must.append(
                models.FieldCondition(
                    key="category_id",
                    match=models.MatchAny(any=category_ids),
                )
            )
        if filters.get("tag_ids"):
            must.append(
                models.FieldCondition(
                    key="tag_ids",
                    match=models.MatchAny(
                        any=[str(value) for value in filters["tag_ids"]]
                    ),
                )
            )
        block_types = filters.get("block_types") or []
        if block_types:
            expanded: set[str] = set()
            for item in block_types:
                if item == "table":
                    # 兼容改造前的行级与父块数据。
                    expanded.update({"table", "table_row", "table_summary"})
                elif item == "text":
                    # 公式块属于正文，不应被“只要正文”的过滤条件排除。
                    expanded.update({"text", "formula"})
                else:
                    expanded.add(item)
            must.append(
                models.FieldCondition(
                    key="block_type", match=models.MatchAny(any=sorted(expanded))
                )
            )
        if filters.get("uploaded_from") or filters.get("uploaded_to"):
            range_filter: dict = {}
            if filters.get("uploaded_from"):
                range_filter["gte"] = filters["uploaded_from"]
            if filters.get("uploaded_to"):
                range_filter["lte"] = filters["uploaded_to"]
            must.append(
                models.FieldCondition(
                    key="uploaded_at", range=models.Range(**range_filter)
                )
            )
        return models.Filter(must=must)

    def _contexts(self, document_ids: set[uuid.UUID]) -> dict:
        if not document_ids:
            return {}
        with SessionLocal() as db:
            documents = {
                document.id: document
                for document in db.scalars(
                    select(Document).where(Document.id.in_(document_ids))
                )
            }
            category_ids = {document.category_id for document in documents.values()}
            categories = {
                category.id: category
                for category in db.scalars(
                    select(Category).where(Category.id.in_(category_ids))
                )
            }
            relations = list(
                db.scalars(
                    select(DocumentRelation).where(
                        (DocumentRelation.source_document_id.in_(document_ids))
                        | (DocumentRelation.target_document_id.in_(document_ids))
                    )
                )
            )
            related_ids = {
                relation.target_document_id if relation.source_document_id in document_ids else relation.source_document_id
                for relation in relations
            }
            related_documents = {
                document.id: document
                for document in db.scalars(
                    select(Document).where(Document.id.in_(related_ids))
                )
            } if related_ids else {}
            contexts = {}
            for document in documents.values():
                tags = list(
                    db.scalars(
                        select(Tag)
                        .join(DocumentTag)
                        .where(DocumentTag.document_id == document.id)
                    )
                )
                category = categories.get(document.category_id)
                doc_relations = [
                    relation
                    for relation in relations
                    if document.id
                    in {relation.source_document_id, relation.target_document_id}
                ]
                related_items = []
                amendment_notice = None
                for relation in doc_relations:
                    other_id = (
                        relation.target_document_id
                        if relation.source_document_id == document.id
                        else relation.source_document_id
                    )
                    other = related_documents.get(other_id)
                    if not other:
                        continue
                    related_items.append(
                        {
                            "document_id": str(other.id),
                            "title": other.title,
                            "relation_type": relation.relation_type.value,
                            "volume_no": relation.volume_no,
                        }
                    )
                    if relation.relation_type.value in {"amends", "corrects"}:
                        amendment_notice = f"存在关联{relation.relation_type.value}文件：{other.title}"
                contexts[document.id] = {
                    "name": document.title,
                    "lifecycle_status": document.lifecycle_status.value,
                    "document_role": document.document_role.value,
                    "standard_no": document.standard_no,
                    "related_documents": related_items,
                    "amendment_notice": amendment_notice,
                    "category": (
                        {
                            "id": str(category.id),
                            "code": category.code,
                            "name": category.name,
                        }
                        if category
                        else None
                    ),
                    "tags": [{"id": str(tag.id), "name": tag.name} for tag in tags],
                }
            return contexts

    def _audit(
        self,
        principal,
        query: str,
        mode,
        filters: dict,
        top_k: int,
        result_count: int,
        took_ms: int,
        degraded: list[str],
    ) -> None:
        if self.audit:
            self.audit.record_search(
                principal.actor_type,
                principal.id,
                request_id_context.get() or "system",
                mode,
                query,
                filters,
                top_k,
                result_count,
                took_ms,
                bool(degraded),
                degraded,
            )


def _table_payload(record: dict) -> dict:
    """Structured cells for the front-end table renderer."""
    html = record.get("table_html") or ""
    rows = parse_html_table(html) if html else []
    expanded = expand_rows(rows)
    return {
        "id": record.get("table_id") or "",
        "caption": record.get("section_title"),
        "header": record.get("table_header"),
        "total_rows": len(expanded),
        "row_count": len(expanded),
        "column_count": max((len(row) for row in expanded), default=0),
        "row_range": [
            (record.get("page_offsets") or {}).get("row_start") or 1,
            (record.get("page_offsets") or {}).get("row_end") or len(expanded),
        ],
        "rows": [
            [
                {"text": cell.text, "rowspan": cell.rowspan, "colspan": cell.colspan}
                for cell in row
            ]
            for row in rows
        ],
    }
