from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from qdrant_client import QdrantClient
from sqlalchemy import delete, select

from occupational_health.db.models.content import Chunk, MaskingAnnotation, Page
from occupational_health.db.models.documents import Document, DocumentVersion
from occupational_health.db.models.jobs import ProcessingJob, QualityReport
from occupational_health.db.models.taxonomy import DocumentTag, Tag
from occupational_health.db.session import SessionLocal
from occupational_health.domain.enums import (
    ChunkMode,
    ChunkRole,
    DocumentStatus,
    JobStage,
    JobStatus,
    PageSource,
    PageStatus,
    SensitiveType,
    VersionStatus,
)
from occupational_health.services.chunking.service import (
    ChunkInput,
    approximate_token_count,
    sanitize_text,
    split_pages,
)
from occupational_health.services.documents.auto_tagging import (
    apply_auto_classification,
)
from occupational_health.services.embedding.client import EmbeddingClient
from occupational_health.services.extraction.cleaning import clean_text, correct_ocr_text
from occupational_health.services.extraction.rapid_ocr import RapidOcrAdapter
from occupational_health.services.extraction.quality import (
    PageQuality,
    page_status,
    summarize,
)
from occupational_health.services.extraction.document_loader import (
    document_format,
    extract_page_text,
)
from occupational_health.services.extraction.mineru import MineruAdapter
from occupational_health.services.indexing.publisher import (
    mark_needs_review,
    publish,
    quality_gate,
)
from occupational_health.services.indexing.qdrant import QdrantIndexer
from occupational_health.services.masking.service import mask_text
from occupational_health.services.retrieval.anchors import rebuild_chunk_anchors

_LOGGER = logging.getLogger(__name__)

_CHUNKER_VERSION = {
    ChunkMode.STRUCTURE: "structure-v3",
    ChunkMode.SENTENCE: "sentence-v2",
    ChunkMode.FIXED: "fixed-v2",
    ChunkMode.PARENT_CHILD: "parent-child-v1",
}


def _is_pdf(path: Path) -> bool:
    try:
        return document_format(path) == "pdf"
    except Exception:
        # 损坏/加密文件交给原有链路给出规范错误，不在这里中断任务。
        return False


def _embedding_text(chunk: Chunk, max_tokens: int) -> str:
    """Cap the embedding input of huge tables; the stored text stays complete."""
    if chunk.block_type != "table":
        return chunk.raw_text
    if approximate_token_count(chunk.raw_text) <= max_tokens:
        return chunk.raw_text
    kept: list[str] = []
    total = 0
    for line in chunk.raw_text.splitlines():
        cost = approximate_token_count(line)
        if kept and total + cost > max_tokens:
            break
        kept.append(line)
        total += cost
    return "\n".join(kept)


def process_document(job_id: uuid.UUID, file_path: Path, settings) -> None:
    if not file_path.is_file():
        raise FileNotFoundError(f"stored file not found for job {job_id}")
    indexer = _indexer(settings)
    # 异常向上传播，由 tasks.process_document_task 统一决定是否重试（见 P2-9）。
    _process(job_id, file_path, settings, indexer)


def _process(job_id: uuid.UUID, file_path: Path, settings, indexer: QdrantIndexer) -> None:
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if not job:
            return
        document = db.get(Document, job.document_id)
        if not document:
            return
        now = datetime.now(UTC)
        job.status = JobStatus.PARSING
        job.current_stage = JobStage.EXTRACTION
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        # 断点续跑：从上次已处理页之后继续（首次 processed_pages 为 0）。
        start_page = job.processed_pages

        # Chunk 需整体重建（聚合依赖全部页）；Page 仅在首次清空，重试时保留已完成部分。
        db.execute(
            delete(Chunk).where(
                Chunk.version_id == job.version_id,
                Chunk.pipeline_revision == job.pipeline_revision,
            )
        )
        if start_page == 0:
            db.execute(
                delete(Page).where(
                    Page.version_id == job.version_id,
                    Page.pipeline_revision == job.pipeline_revision,
                )
            )
        db.commit()

        page_qualities: list[PageQuality] = []
        chunks_input: list[ChunkInput] = []
        page_sources: dict[int, PageSource] = {}

        # 恢复断点前已处理的页（供 chunk 聚合与质量汇总复用，避免重跑 OCR）。
        if start_page > 0:
            for existing in db.scalars(
                select(Page)
                .where(
                    Page.version_id == job.version_id,
                    Page.pipeline_revision == job.pipeline_revision,
                )
                .order_by(Page.page_number)
            ):
                source = existing.source_type
                page_sources[existing.page_number] = source
                if existing.cleaned_text:
                    chunks_input.append(
                        ChunkInput(existing.page_number, existing.cleaned_text, source.value)
                    )
                page_qualities.append(
                    PageQuality(
                        existing.page_number,
                        source,
                        existing.effective_char_count,
                        existing.noise_char_count,
                        ocr_confidence=existing.ocr_confidence,
                        failed=existing.status == PageStatus.FAILED,
                        failure_code=existing.failure_code,
                    )
                )

        pending = range(start_page + 1, job.total_pages + 1)

        # 阶段 0：PDF 优先用 MinerU 结构化解析（含表格 HTML），失败回退旧链路。
        mineru_pages = None
        page_segments = None
        if settings.mineru_enabled and _is_pdf(file_path):
            job.current_stage = JobStage.MINERU
            db.commit()

            total_pages = job.total_pages

            def heartbeat(progress: float = 0.0) -> None:
                with SessionLocal() as hb_db:
                    hb_job = hb_db.get(ProcessingJob, job_id)
                    if hb_job:
                        hb_job.heartbeat_at = _now()
                        # 整份文档解析期间按模型阶段估算页数，避免一直显示 0/N。
                        estimated = min(
                            int(progress * total_pages), max(total_pages - 1, 0)
                        )
                        if estimated > (hb_job.processed_pages or 0):
                            hb_job.processed_pages = estimated
                        hb_db.commit()

            try:
                adapter = MineruAdapter(settings)
                if adapter.available():
                    mineru_pages = adapter.parse(
                        file_path,
                        str(job.version_id),
                        on_heartbeat=heartbeat,
                        total_pages=job.total_pages or 0,
                    )
                    # 保留全部页：断点续跑时 chunks_input 来自已落库的 Page，
                    # 若按 pending 过滤会丢掉表格结构（重试时 pending 为空）。
                    # MinerU segments bypass clean_text; apply deterministic OCR
                    # corrections to their text/HTML before chunking.
                    page_segments = {
                        number: [
                            replace(
                                segment,
                                text=correct_ocr_text(segment.text) or "",
                                html=correct_ocr_text(segment.html),
                            )
                            for segment in parsed.segments
                        ]
                        for number, parsed in mineru_pages.items()
                    }
                    # 心跳由独立 session 写入，刷新后再进入逐页写库，避免进度倒退。
                    db.refresh(job)
                    _LOGGER.info(
                        "mineru parsed %s pages for job %s", len(mineru_pages), job.id
                    )
                else:
                    _LOGGER.warning("mineru-kit unavailable, using legacy extractors")
            except Exception as exc:
                _LOGGER.warning(
                    "mineru failed (%s: %s), using legacy extractors",
                    type(exc).__name__,
                    exc,
                )
                mineru_pages = None
                page_segments = None
            if mineru_pages is None:
                job.current_stage = JobStage.EXTRACTION
                db.commit()

        # 阶段 1：逐页提取文本，判定 source，收集需 OCR 的页。
        text_pages: dict[int, tuple[str, int]] = {}
        ocr_pages: list[int] = []
        if mineru_pages is None:
            for page_number in pending:
                raw, effective = extract_page_text(
                    file_path, page_number, settings.text_layer_min_chars
                )
                # 只要存在文本层就直接采用（哪怕字符较少，如封面/图表页），
                # 仅当页面完全没有文本（纯扫描件）时才回退 OCR。
                if effective > 0:
                    text_pages[page_number] = (raw, effective)
                else:
                    ocr_pages.append(page_number)

        # 阶段 2：批量 OCR（一次 predict，结果按页映射，单页失败不影响整体）。
        ocr_results: dict[int, dict] = {}
        if ocr_pages:
            job.current_stage = JobStage.OCR
            job.heartbeat_at = _now()
            db.commit()
            ocr_adapter = RapidOcrAdapter()
            ocr_results = ocr_adapter.recognize_batch(file_path, ocr_pages)
            job.current_stage = JobStage.EXTRACTION
            job.heartbeat_at = _now()
            db.commit()

        # 阶段 3：逐页清洗/写库，每 N 页提交一次。
        for index, page_number in enumerate(pending, start=1):
            failed_code = None
            failed_message = None
            confidence = None
            if mineru_pages is not None:
                parsed = mineru_pages.get(page_number)
                raw = parsed.text if parsed else ""
                source = (
                    PageSource.OCR
                    if parsed and parsed.used_ocr
                    else PageSource.TEXT_LAYER
                )
                effective = len([char for char in raw if not char.isspace()])
            elif page_number in ocr_pages:
                source = PageSource.OCR
                result = ocr_results.get(page_number) or {}
                raw = result.get("text", "")
                if raw and not result.get("failed"):
                    confidence = result.get("confidence")
                    effective = len([ch for ch in raw if not ch.isspace()])
                else:
                    failed_code = "OCR_FAILED"
                    failed_message = "该页 OCR 识别失败"
                    effective = 0
                    raw = ""
            else:
                source = PageSource.TEXT_LAYER
                raw, effective = text_pages[page_number]

            cleaned, noise = clean_text(raw)
            masked, annotations, _spans = mask_text(cleaned)
            page = Page(
                version_id=job.version_id,
                pipeline_revision=job.pipeline_revision,
                page_number=page_number,
                source_type=source,
                raw_text=sanitize_text(raw) or "",
                cleaned_text=sanitize_text(cleaned) or "",
                masked_text=sanitize_text(masked) or "",
                effective_char_count=effective,
                noise_char_count=noise,
                ocr_confidence=confidence,
                layout_warning_codes=[],
                status=(
                    PageStatus.FAILED
                    if failed_code
                    else page_status(
                        PageQuality(
                            page_number,
                            source,
                            effective,
                            noise,
                            ocr_confidence=confidence,
                        ),
                        settings.ocr_low_confidence,
                    )
                ),
                failure_code=failed_code,
                safe_failure_message=failed_message,
                offset_map={},
            )
            db.add(page)
            db.flush()
            for annotation in annotations:
                db.add(
                    MaskingAnnotation(
                        version_id=job.version_id,
                        page_id=page.id,
                        start_offset=annotation["start_offset"],
                        end_offset=annotation["end_offset"],
                        base_text_hash=annotation["base_text_hash"],
                        sensitive_type=SensitiveType(annotation["sensitive_type"]),
                        replacement=annotation["replacement"],
                    )
                )
            page_qualities.append(
                PageQuality(
                    page_number,
                    source,
                    effective,
                    noise,
                    ocr_confidence=confidence,
                    failed=bool(failed_code),
                    failure_code=failed_code,
                )
            )
            page_sources[page_number] = source
            if cleaned:
                chunks_input.append(ChunkInput(page_number, cleaned, source.value))
            job.processed_pages = max(job.processed_pages or 0, page_number)
            job.heartbeat_at = _now()
            if index % settings.pipeline_commit_every == 0:
                db.commit()
        db.commit()

        job.current_stage = JobStage.CHUNKING
        db.commit()
        chunk_mode = ChunkMode(job.chunk_mode or ChunkMode.FIXED.value)
        chunk_dicts = split_pages(
            chunks_input,
            job.chunk_target_tokens or settings.chunk_target_tokens,
            job.chunk_max_tokens or settings.chunk_max_tokens,
            (
                job.chunk_overlap_tokens
                if job.chunk_overlap_tokens is not None
                else settings.chunk_overlap_tokens
            ),
            mode=chunk_mode,
            table_namespace=str(job.version_id),
            page_segments=page_segments,
            parent_target=settings.parent_chunk_target_tokens,
            parent_max_tokens=settings.parent_chunk_max_tokens,
            child_target=settings.child_chunk_target_tokens,
            child_max_tokens=settings.child_chunk_max_tokens,
            child_overlap=settings.child_chunk_overlap_tokens,
        )
        chunks: list[Chunk] = []
        parent_id_by_ordinal: dict[int, uuid.UUID] = {}
        for chunk_data in chunk_dicts:
            chunk_id = uuid.uuid5(
                job.version_id, f"{job.pipeline_revision}:{chunk_data['ordinal']}"
            )
            if chunk_data.get("chunk_role") == "parent":
                parent_id_by_ordinal[chunk_data["ordinal"]] = chunk_id
            page_range = range(chunk_data["page_start"], chunk_data["page_end"] + 1)
            source_types = sorted(
                {
                    page_sources[page].value
                    for page in page_range
                    if page in page_sources
                }
            )
            masked, _annotations, _spans = mask_text(chunk_data["text"])
            chunk = Chunk(
                id=chunk_id,
                document_id=job.document_id,
                version_id=job.version_id,
                pipeline_revision=job.pipeline_revision,
                chunker_version=_CHUNKER_VERSION[chunk_mode],
                chunk_role=chunk_data.get("chunk_role", "leaf"),
                parent_chunk_id=(
                    str(parent_id_by_ordinal[chunk_data["parent_ordinal"]])
                    if chunk_data.get("parent_ordinal") is not None
                    else None
                ),
                ordinal=chunk_data["ordinal"],
                page_start=chunk_data["page_start"],
                page_end=chunk_data["page_end"],
                source_types=source_types,
                raw_text=sanitize_text(chunk_data["text"]) or "",
                masked_text=sanitize_text(masked) or "",
                block_type=chunk_data.get("block_type", "text"),
                table_header=sanitize_text(chunk_data.get("table_header")),
                table_id=sanitize_text(chunk_data.get("table_id")),
                source_table_id=sanitize_text(chunk_data.get("table_id")),
                section_title=sanitize_text(chunk_data.get("section_title")),
                table_html=sanitize_text(chunk_data.get("table_html")),
                is_edited=False,
                page_offsets=chunk_data.get("page_offsets") or {},
                token_count=chunk_data["token_count"],
                content_hash=chunk_data["content_hash"],
                embedding_model=settings.qwen_model_id,
                embedding_revision=settings.qwen_revision,
                embedding_dimensions=1024,
                index_visible=False,
            )
            db.add(chunk)
            chunks.append(chunk)

        db.flush()
        for chunk in chunks:
            rebuild_chunk_anchors(db, chunk)

        semantic_chunks = [
            chunk for chunk in chunks if chunk.chunk_role != ChunkRole.CHILD.value
        ]
        summary = summarize(page_qualities, settings.ocr_low_confidence)
        summary["chunk_count"] = len(semantic_chunks)
        db.add(
            QualityReport(
                document_id=job.document_id,
                version_id=job.version_id,
                job_id=job.id,
                pipeline_revision=job.pipeline_revision,
                page_count=summary["page_count"],
                effective_char_count=summary["effective_char_count"],
                chunk_count=summary["chunk_count"],
                ocr_page_ratio=summary["ocr_page_ratio"],
                average_ocr_confidence=summary["average_ocr_confidence"],
                noise_char_count=summary["noise_char_count"],
                low_quality_pages=summary["low_quality_pages"],
                failed_pages=summary["failed_pages"],
            )
        )
        db.commit()

        if not quality_gate(summary, settings.document_min_chars):
            mark_needs_review(
                job.document_id,
                job.version_id,
                job.id,
                "文档有效内容过少，需人工检查",
            )
            return
        if not chunks:
            mark_needs_review(
                job.document_id,
                job.version_id,
                job.id,
                "未生成可检索文本块",
            )
            return

        # 自动归类用 savepoint 隔离：任何约束冲突只回滚这一步，
        # 绝不污染已落库 chunk 所在的事务（否则后续 commit 会 PendingRollbackError）。
        try:
            with db.begin_nested():
                apply_auto_classification(
                    db,
                    document,
                    [chunk.raw_text for chunk in semantic_chunks[:50]],
                    settings,
                )
        except Exception as exc:  # 归类失败不应影响文档处理
            _LOGGER.warning("auto classification failed for %s: %s", job.id, exc)
        db.commit()

        if settings.require_chunk_confirmation:
            # 阶段一结束：chunk 已落库但尚未向量化，等待人工预览/编辑并确认。
            job.status = JobStatus.PENDING_CONFIRMATION
            job.current_stage = JobStage.REVIEW
            job.error_code = None
            job.safe_error_message = None
            job.heartbeat_at = _now()
            db.commit()
            _LOGGER.info(
                "chunks awaiting confirmation for job %s: %s chunks",
                job.id,
                len(chunks),
            )
            return

        _embed_and_publish(job, document, settings, indexer, db)


def finalize_document(job_id: uuid.UUID, settings) -> None:
    """Phase two: embed the (possibly edited) chunks and publish them."""
    indexer = _indexer(settings)
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if not job:
            return
        document = db.get(Document, job.document_id)
        if not document:
            return
        _embed_and_publish(job, document, settings, indexer, db)


def _embed_and_publish(job, document, settings, indexer: QdrantIndexer, db) -> None:
    # 重新读取，确保拿到人工编辑后的最新文本。
    chunks = list(
        db.scalars(
            select(Chunk)
            .where(
                Chunk.version_id == job.version_id,
                Chunk.pipeline_revision == job.pipeline_revision,
            )
            .order_by(Chunk.ordinal)
        )
    )
    indexable = [
        chunk for chunk in chunks if chunk.chunk_role != ChunkRole.PARENT.value
    ]
    if not indexable:
        mark_needs_review(
            job.document_id, job.version_id, job.id, "确认后没有可入库的文本块"
        )
        return

    job.status = JobStatus.EMBEDDING
    job.current_stage = JobStage.EMBEDDING
    job.heartbeat_at = _now()
    db.commit()

    embedding = EmbeddingClient(
        settings.embedding_url,
        settings.embedding_timeout_seconds,
        max_retries=settings.embedding_max_retries,
        retry_backoff=settings.embedding_retry_backoff_seconds,
    )
    try:
        embedding.wait_until_ready(settings.embedding_warmup_timeout_seconds)
        tag_ids = [
            str(tag.id)
            for tag in db.scalars(
                select(Tag)
                .join(DocumentTag, DocumentTag.tag_id == Tag.id)
                .where(DocumentTag.document_id == job.document_id)
            )
        ]
        points: list[dict] = []
        batches = list(range(0, len(indexable), settings.embedding_batch_size))
        for batch_index, start in enumerate(batches, start=1):
            batch = indexable[start : start + settings.embedding_batch_size]
            vectors = embedding.embed(
                [
                    _embedding_text(chunk, settings.table_embedding_max_tokens)
                    for chunk in batch
                ]
            )
            _LOGGER.info(
                "embedding batch %s/%s done for job %s",
                batch_index,
                len(batches),
                job.id,
            )
            job.heartbeat_at = _now()
            db.commit()
            for chunk, vector in zip(batch, vectors, strict=True):
                points.append(
                    {
                        "id": chunk.id,
                        "vector": {"masked_dense": vector},
                        "payload": {
                            "chunk_id": str(chunk.id),
                            "document_id": str(job.document_id),
                            "version_id": str(job.version_id),
                            "pipeline_revision": str(job.pipeline_revision),
                            "category_id": str(document.category_id),
                            "tag_ids": tag_ids,
                            "lifecycle_status": document.lifecycle_status.value,
                            "document_role": document.document_role.value,
                            "standard_no": document.standard_no,
                            "effective_date": _iso(document.effective_date)
                            if document.effective_date
                            else None,
                            "uploaded_at": _iso(document.created_at),
                            "page_start": chunk.page_start,
                            "page_end": chunk.page_end,
                            "index_visible": False,
                            "block_type": chunk.block_type,
                            "chunk_role": chunk.chunk_role,
                            "parent_chunk_id": chunk.parent_chunk_id,
                            "table_id": chunk.table_id,
                            "section_title": chunk.section_title,
                            "masked_text": chunk.raw_text,
                            "raw_text": chunk.raw_text,
                        },
                    }
                )
    finally:
        embedding.close()
    indexer.upsert(points)

    job.current_stage = JobStage.PUBLISHING
    job.heartbeat_at = _now()
    db.commit()
    old_revisions = list(
        db.scalars(
            select(Chunk.pipeline_revision)
            .where(
                Chunk.version_id == job.version_id,
                Chunk.pipeline_revision != job.pipeline_revision,
            )
            .distinct()
        )
    )
    published = publish(
        job.document_id,
        job.version_id,
        job.id,
        job.pipeline_revision,
        job.target_activation_epoch,
        len(chunks),
    )
    if published:
        indexer.set_revision_visible(job.pipeline_revision, True)
        for old_revision in old_revisions:
            indexer.set_revision_visible(old_revision, False)
    else:
        indexer.delete_revision(job.pipeline_revision)


def _indexer(settings) -> QdrantIndexer:
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value(),
        timeout=30,
    )
    return QdrantIndexer(client)


def _mark_failed(
    job_id: uuid.UUID, exc: Exception | None = None, terminal: bool = False
) -> bool:
    """Record a failed attempt and decide whether the task should be retried.

    Returns True when the job still has retry budget left (the caller should
    re-enqueue), False once ``max_attempts`` is exhausted. On the final failure
    the document must leave ``processing`` so the UI does not hang forever.
    """
    reason = _failure_reason(exc)
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if not job:
            return False
        job.attempt_count += 1
        job.error_code = "PROCESSING_FAILED"
        job.safe_error_message = reason
        job.heartbeat_at = _now()
        if terminal or job.attempt_count >= job.max_attempts:
            job.status = JobStatus.FAILED
            job.finished_at = _now()
            document = db.get(Document, job.document_id)
            if document and document.status == DocumentStatus.PROCESSING:
                document.status = DocumentStatus.NEEDS_REVIEW
                document.updated_at = _now()
            if job.version_id:
                version = db.get(DocumentVersion, job.version_id)
                if version and version.status == VersionStatus.PROCESSING:
                    version.status = VersionStatus.FAILED
            db.commit()
            return False
        job.status = JobStatus.QUEUED
        db.commit()
        return True


def _failure_reason(exc: Exception | None) -> str:
    """Translate a worker exception into an actionable, non-sensitive message."""
    text = f"{type(exc).__name__} {exc}".lower() if exc else ""
    if "dependency" in text or "ocr" in text or "paddle" in text:
        return "OCR 识别失败：模型依赖缺失或识别异常，请联系管理员检查 OCR 环境"
    if "embedding" in text or "timeout" in text or "connection" in text:
        return "向量化失败：向量化服务连接超时或不可用，请检查服务状态"
    if "qdrant" in text:
        return "向量索引写入失败：请检查 Qdrant 服务状态"
    if "nul" in text or "0x00" in text:
        return "文档含非法控制字符（NUL），解析阶段已自动清除，请重新处理该文件"
    name = type(exc).__name__ if exc else "UnknownError"
    return f"文档处理失败（{name}），请重试或联系管理员"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()
