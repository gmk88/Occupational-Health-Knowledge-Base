from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from occupational_health.core.errors import ApiError
from occupational_health.db.models.content import Chunk, ChunkAnchor, Page
from occupational_health.db.models.documents import (
    Document,
    DocumentFingerprint,
    DocumentVersion,
    StoredFile,
)
from occupational_health.db.models.jobs import JobEvent, ProcessingJob, QualityReport
from occupational_health.db.models.taxonomy import (
    Category,
    DocumentRelation,
    DocumentTag,
    Tag,
)
from occupational_health.db.session import SessionLocal, utcnow
from occupational_health.domain.enums import (
    ChunkMode,
    DocumentRole,
    DocumentStatus,
    JobStage,
    JobStatus,
    JobType,
    LifecycleStatus,
    RelationKind,
    VersionStatus,
)
from occupational_health.services.ingestion.document_validator import validate_document
from occupational_health.storage.files import PrivateFileStorage

logger = logging.getLogger(__name__)

_LIFECYCLE_LABELS = {
    LifecycleStatus.CURRENT.value: "现行",
    LifecycleStatus.REPLACED.value: "已替代",
    LifecycleStatus.ABOLISHED.value: "废止",
    LifecycleStatus.SUPERSEDED.value: "被取代",
    LifecycleStatus.PENDING.value: "待确认",
}
_ROLE_LABELS = {
    DocumentRole.MAIN.value: "主标准",
    DocumentRole.SUPPLEMENT.value: "补充卷",
    DocumentRole.AMENDMENT.value: "修改单",
    DocumentRole.CORRIGENDUM.value: "勘误",
    DocumentRole.OTHER.value: "其他",
}
_DOCUMENT_STATUS_LABELS = {
    DocumentStatus.PROCESSING.value: "处理中",
    DocumentStatus.SEARCHABLE.value: "可检索",
    DocumentStatus.NEEDS_REVIEW.value: "需复核",
    DocumentStatus.DELETED.value: "已删除",
}


class DocumentService:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.storage_root = Path(settings.storage_root)
        self._summary_cache: tuple[float, dict] | None = None

    def _list_meta(self, total: int, page: int, page_size: int) -> dict:
        total_pages = (total + page_size - 1) // page_size if total else 0
        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def upload(
        self,
        file_path: Path,
        filename: str,
        uploader_id: uuid.UUID,
        title: str | None,
        category_id: uuid.UUID | None,
        tags: list[str] | None,
        source: str | None,
        notes: str | None,
        chunk_mode: str = "parent_child",
        chunk_target_tokens: int | None = None,
        chunk_max_tokens: int | None = None,
        chunk_overlap_tokens: int | None = None,
    ) -> dict:
        try:
            mode = ChunkMode(chunk_mode)
        except ValueError as exc:
            raise ApiError(400, "VALIDATION_ERROR", "不支持的切分方式") from exc
        target = chunk_target_tokens or self.settings.chunk_target_tokens
        maximum = chunk_max_tokens or self.settings.chunk_max_tokens
        overlap = (
            chunk_overlap_tokens
            if chunk_overlap_tokens is not None
            else self.settings.chunk_overlap_tokens
        )
        if not 0 <= overlap <= 4096:
            raise ApiError(
                400, "VALIDATION_ERROR", "重叠长度需在 0-4096 tokens 之间"
            )
        # 目标/上限只约束固定大小模式；结构/句子模式只用重叠做前缀复制。
        if mode == ChunkMode.FIXED and not 0 <= overlap < target <= maximum:
            raise ApiError(
                400,
                "VALIDATION_ERROR",
                "切分参数需满足：重叠 < 目标长度 ≤ 最大长度",
            )
        validated = validate_document(
            file_path,
            self.settings.max_file_size_bytes,
            self.settings.max_pages_per_file,
        )
        digest = _sha256(file_path)
        storage = PrivateFileStorage(self.storage_root)
        with file_path.open("rb") as stream:
            storage_key = storage.save(stream, digest, file_path.suffix.lower())
        with SessionLocal() as db:
            existing = db.scalar(
                select(DocumentFingerprint)
                .join(Document, Document.id == DocumentFingerprint.document_id)
                .where(
                    DocumentFingerprint.sha256 == digest,
                    Document.status != DocumentStatus.DELETED,
                )
            )
            if existing:
                latest_job = db.scalar(
                    select(ProcessingJob)
                    .where(ProcessingJob.document_id == existing.document_id)
                    .order_by(ProcessingJob.created_at.desc())
                )
                document = db.get(Document, existing.document_id)
                return {
                    "document_id": str(existing.document_id),
                    "version_id": str(existing.initial_version_id),
                    "job_id": str(latest_job.id) if latest_job else None,
                    "duplicate": True,
                    "status": document.status.value if document else None,
                }
            category = self._resolve_category(db, category_id)
            document = Document(
                title=title or filename,
                category_id=category.id,
                source=source,
                notes=notes,
                uploader_id=uploader_id,
            )
            db.add(document)
            db.flush()
            stored = db.scalar(
                select(StoredFile).where(StoredFile.sha256 == digest)
            )
            if stored is None:
                stored = StoredFile(
                    sha256=digest,
                    storage_key=storage_key,
                    original_filename=filename,
                    size_bytes=file_path.stat().st_size,
                    page_count=validated.page_count,
                )
                db.add(stored)
                db.flush()
            version = DocumentVersion(
                document_id=document.id,
                version_number=1,
                file_id=stored.id,
                content_sha256=digest,
                created_by=uploader_id,
            )
            db.add(version)
            db.flush()
            document.current_version_id = None
            document.activation_epoch = 1
            fingerprint = db.get(DocumentFingerprint, digest)
            if fingerprint is None:
                db.add(
                    DocumentFingerprint(
                        sha256=digest,
                        document_id=document.id,
                        initial_version_id=version.id,
                    )
                )
            else:
                fingerprint.document_id = document.id
                fingerprint.initial_version_id = version.id
                fingerprint.state = "active"
            job = ProcessingJob(
                document_id=document.id,
                version_id=version.id,
                job_type=JobType.UPLOAD,
                chunk_mode=mode.value,
                chunk_target_tokens=target,
                chunk_max_tokens=maximum,
                chunk_overlap_tokens=overlap,
                target_activation_epoch=document.activation_epoch,
                input_fingerprint=digest,
                total_pages=validated.page_count,
                requested_by=uploader_id,
                heartbeat_at=utcnow(),
            )
            db.add(job)
            db.flush()
            db.add(
                JobEvent(
                    job_id=job.id,
                    sequence=1,
                    from_status="",
                    to_status=JobStatus.QUEUED.value,
                    stage="validation",
                    message="已接收上传",
                )
            )
            for name in tags or []:
                self._link_tag(db, document, name)
            db.commit()
            response = {
                "document_id": str(document.id),
                "version_id": str(version.id),
                "job_id": str(job.id),
                "duplicate": False,
                "status": job.status.value,
            }
        self._enqueue(str(response["job_id"]), storage_key)
        return response

    def _enqueue(self, job_id: str, storage_key: str) -> None:
        try:
            from occupational_health.workers.tasks import process_document_task

            result = process_document_task.delay(job_id, storage_key)
            logger.info(
                "document job enqueued",
                extra={"job_id": job_id, "result": result.id},
            )
        except Exception as exc:
            logger.exception("failed to enqueue document job", extra={"job_id": job_id})
            with SessionLocal() as db:
                job = db.get(ProcessingJob, uuid.UUID(job_id))
                if job:
                    job.status = JobStatus.FAILED
                    job.error_code = "ENQUEUE_FAILED"
                    job.safe_error_message = "任务投递失败，请重新上传"
                    job.finished_at = utcnow()
                    db.commit()
            raise ApiError(503, "TASK_ENQUEUE_FAILED", "任务投递失败，请重新上传") from exc

    def _resolve_category(self, db: Session, category_id: uuid.UUID | None) -> Category:
        if category_id:
            category = db.get(Category, category_id)
            if category:
                return category
            raise ApiError(400, "VALIDATION_ERROR", "分类不存在")
        category = db.scalar(select(Category).where(Category.code == "general"))
        if not category:
            category = Category(code="general", name="通用")
            db.add(category)
            db.flush()
        return category

    def _link_tag(self, db: Session, document: Document, name: str) -> None:
        normalized = name.strip().casefold()
        tag = db.scalar(select(Tag).where(Tag.normalized_name == normalized))
        if not tag:
            tag = Tag(name=name.strip(), normalized_name=normalized)
            db.add(tag)
            db.flush()
        db.add(DocumentTag(document_id=document.id, tag_id=tag.id))


    def update_lifecycle(
        self,
        document_id: uuid.UUID,
        *,
        lifecycle_status: str | None = None,
        document_role: str | None = None,
        standard_key: str | None = None,
        standard_no: str | None = None,
        edition_year: int | None = None,
        effective_date: datetime | None = None,
        change_note: str | None = None,
    ) -> dict:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if not document or document.status == DocumentStatus.DELETED:
                raise ApiError(404, "NOT_FOUND", "文档不存在")
            if lifecycle_status is not None:
                try:
                    document.lifecycle_status = LifecycleStatus(lifecycle_status)
                except ValueError as exc:
                    raise ApiError(400, "VALIDATION_ERROR", "无效的生命周期状态") from exc
            if document_role is not None:
                try:
                    document.document_role = DocumentRole(document_role)
                except ValueError as exc:
                    raise ApiError(400, "VALIDATION_ERROR", "无效的文档角色") from exc
            if standard_key is not None:
                document.standard_key = standard_key.strip() or None
            if standard_no is not None:
                document.standard_no = standard_no.strip() or None
            if edition_year is not None:
                document.edition_year = edition_year
            if effective_date is not None:
                document.effective_date = effective_date
            version = (
                db.get(DocumentVersion, document.current_version_id)
                if document.current_version_id
                else None
            )
            if version:
                if standard_no is not None:
                    version.standard_no = document.standard_no
                if edition_year is not None:
                    version.edition_year = edition_year
                if effective_date is not None:
                    version.effective_date = effective_date
                if change_note is not None:
                    version.change_note = change_note
            db.commit()
            return self._document_dict(db, document)

    def list_relations(self, document_id: uuid.UUID) -> list[dict]:
        with SessionLocal() as db:
            rows = list(
                db.scalars(
                    select(DocumentRelation)
                    .where(
                        (DocumentRelation.source_document_id == document_id)
                        | (DocumentRelation.target_document_id == document_id)
                    )
                    .order_by(DocumentRelation.created_at)
                )
            )
            document_ids = {
                row.source_document_id for row in rows
            } | {row.target_document_id for row in rows}
            documents = {
                document.id: document
                for document in db.scalars(
                    select(Document).where(Document.id.in_(document_ids))
                )
            }
            return [
                {
                    "id": str(row.id),
                    "source_document_id": str(row.source_document_id),
                    "target_document_id": str(row.target_document_id),
                    "source_title": documents.get(row.source_document_id).title
                    if row.source_document_id in documents
                    else None,
                    "target_title": documents.get(row.target_document_id).title
                    if row.target_document_id in documents
                    else None,
                    "relation_type": row.relation_type.value,
                    "volume_no": row.volume_no,
                    "note": row.note,
                }
                for row in rows
            ]

    def link_relation(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation_type: str,
        volume_no: str | None = None,
        note: str | None = None,
    ) -> dict:
        if source_id == target_id:
            raise ApiError(400, "VALIDATION_ERROR", "不能将文档关联到自身")
        try:
            kind = RelationKind(relation_type)
        except ValueError as exc:
            raise ApiError(400, "VALIDATION_ERROR", "无效的关系类型") from exc
        with SessionLocal() as db:
            for document_id in (source_id, target_id):
                document = db.get(Document, document_id)
                if not document or document.status == DocumentStatus.DELETED:
                    raise ApiError(404, "NOT_FOUND", "文档不存在")
            relation = db.scalar(
                select(DocumentRelation).where(
                    DocumentRelation.source_document_id == source_id,
                    DocumentRelation.target_document_id == target_id,
                    DocumentRelation.relation_type == kind,
                )
            )
            if relation is None:
                relation = DocumentRelation(
                    id=uuid.uuid4(),
                    source_document_id=source_id,
                    target_document_id=target_id,
                    relation_type=kind,
                    volume_no=volume_no,
                    note=note,
                    created_at=utcnow(),
                )
                db.add(relation)
            else:
                relation.volume_no = volume_no
                relation.note = note
            db.commit()
            return {
                "id": str(relation.id),
                "source_document_id": str(source_id),
                "target_document_id": str(target_id),
                "relation_type": kind.value,
                "volume_no": volume_no,
                "note": note,
            }
    def get_document(self, document_id: uuid.UUID) -> dict:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if not document or document.status == DocumentStatus.DELETED:
                raise ApiError(404, "NOT_FOUND", "文档不存在")
            return self._document_dict(db, document)

    def _document_dict(
        self,
        db: Session,
        document: Document,
        prefetch: tuple[dict, dict, dict, dict] | None = None,
    ) -> dict:
        if prefetch is None:
            category = db.get(Category, document.category_id)
            tags = list(
                db.scalars(
                    select(Tag)
                    .join(DocumentTag)
                    .where(DocumentTag.document_id == document.id)
                )
            )
            version = (
                db.get(DocumentVersion, document.current_version_id)
                if document.current_version_id
                else None
            )
            stored = db.get(StoredFile, version.file_id) if version else None
        else:
            categories, versions, files, tags_by_doc = prefetch
            category = categories.get(document.category_id)
            tags = tags_by_doc.get(document.id, [])
            version = (
                versions.get(document.current_version_id)
                if document.current_version_id
                else None
            )
            stored = files.get(version.file_id) if version else None
        return {
            "id": str(document.id),
            "title": document.title,
            "original_filename": stored.original_filename if stored else None,
            "status": document.status.value,
            "lifecycle_status": document.lifecycle_status.value,
            "document_role": document.document_role.value,
            "standard_key": document.standard_key,
            "standard_no": document.standard_no,
            "edition_year": document.edition_year,
            "effective_date": document.effective_date,
            "category": (
                {
                    "id": str(category.id),
                    "code": category.code,
                    "name": category.name,
                    "active": category.active,
                }
                if category
                else None
            ),
            "tags": [{"id": str(tag.id), "name": tag.name} for tag in tags],
            "source": document.source,
            "notes": document.notes,
            "uploader_id": str(document.uploader_id),
            "current_version": self._version_dict(version) if version else None,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
        }

    def _prefetch_document_relations(
        self,
        db: Session,
        documents: list[Document],
        categories: dict | None = None,
    ) -> tuple[dict, dict, dict, dict]:
        """一次预取分类、版本、文件与标签，避免列表接口逐篇查询。"""
        if not documents:
            return {}, {}, {}, {}
        if categories is None:
            category_ids = {doc.category_id for doc in documents if doc.category_id}
            categories = (
                {
                    row.id: row
                    for row in db.scalars(
                        select(Category).where(Category.id.in_(category_ids))
                    )
                }
                if category_ids
                else {}
            )
        version_ids = {
            doc.current_version_id for doc in documents if doc.current_version_id
        }
        version_files = (
            db.execute(
                select(DocumentVersion, StoredFile)
                .outerjoin(StoredFile, StoredFile.id == DocumentVersion.file_id)
                .where(DocumentVersion.id.in_(version_ids))
            ).all()
            if version_ids
            else []
        )
        versions = {version.id: version for version, _ in version_files}
        files = {
            stored.id: stored for _, stored in version_files if stored is not None
        }
        tag_rows = db.execute(
            select(DocumentTag.document_id, Tag)
            .join(Tag, Tag.id == DocumentTag.tag_id)
            .where(DocumentTag.document_id.in_([doc.id for doc in documents]))
        ).all()
        tags_by_doc: dict[uuid.UUID, list[Tag]] = {}
        for document_id, tag in tag_rows:
            tags_by_doc.setdefault(document_id, []).append(tag)
        return categories, versions, files, tags_by_doc

    def _version_dict(self, version: DocumentVersion) -> dict | None:
        if not version:
            return None
        return {
            "id": str(version.id),
            "version_number": version.version_number,
            "status": version.status.value,
            "content_sha256": version.content_sha256,
            "size_bytes": None,
            "page_count": None,
            "created_at": version.created_at,
            "activated_at": version.activated_at,
        }

    def export_documents(self) -> list[dict]:
        """Return all non-deleted documents as flat rows for spreadsheet export."""
        with SessionLocal() as db:
            documents = list(
                db.scalars(
                    select(Document)
                    .where(Document.status != DocumentStatus.DELETED)
                    .order_by(Document.updated_at.desc())
                )
            )
            categories, versions, files, tags_by_doc = self._prefetch_document_relations(
                db, documents
            )
            rows: list[dict] = []
            for document in documents:
                version = (
                    versions.get(document.current_version_id)
                    if document.current_version_id
                    else None
                )
                stored = files.get(version.file_id) if version else None
                category = categories.get(document.category_id)
                tags = tags_by_doc.get(document.id, [])
                rows.append(
                    {
                        "文档ID": str(document.id),
                        "文档名称": document.title,
                        "原始文件名": stored.original_filename if stored else "",
                        "标准号": document.standard_no or "",
                        "标准主编号": document.standard_key or "",
                        "版本年份": document.edition_year or "",
                        "生命周期状态": _LIFECYCLE_LABELS.get(
                            document.lifecycle_status.value,
                            document.lifecycle_status.value,
                        ),
                        "文档角色": _ROLE_LABELS.get(
                            document.document_role.value,
                            document.document_role.value,
                        ),
                        "场景": category.name if category else "",
                        "标签": "、".join(tag.name for tag in tags),
                        "处理状态": _DOCUMENT_STATUS_LABELS.get(
                            document.status.value, document.status.value
                        ),
                        "版本号": version.version_number if version else "",
                        "页数": stored.page_count if stored else "",
                        "实施日期": (
                            document.effective_date.strftime("%Y-%m-%d")
                            if document.effective_date
                            else ""
                        ),
                        "上传时间": document.created_at.isoformat(timespec="seconds"),
                        "更新时间": document.updated_at.isoformat(timespec="seconds"),
                    }
                )
            return rows

    def list_documents(
        self,
        page: int,
        page_size: int,
        sort: str,
        status: str | None,
        category_id: uuid.UUID | None,
    ) -> tuple[list[dict], dict]:
        with SessionLocal() as db:
            statement = select(Document).where(
                Document.status != DocumentStatus.DELETED
            )
            if status:
                statement = statement.where(Document.status == status)
            if category_id:
                statement = statement.where(Document.category_id == category_id)
            total = db.scalar(select(func.count()).select_from(statement.subquery()))
            column = (
                Document.created_at
                if sort.lstrip("-") == "created_at"
                else Document.updated_at
            )
            statement = (
                statement.order_by(
                    column.asc() if not sort.startswith("-") else column.desc()
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            documents = list(db.scalars(statement))
            prefetch = self._prefetch_document_relations(db, documents)
            items = [
                self._document_dict(db, document, prefetch)
                for document in documents
            ]
            return items, self._list_meta(total or 0, page, page_size)

    def update_metadata(
        self,
        document_id: uuid.UUID,
        title: str | None,
        category_id: uuid.UUID | None,
        tags: list[str] | None,
        source: str | None,
        notes: str | None,
    ) -> dict:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if not document or document.status == DocumentStatus.DELETED:
                raise ApiError(404, "NOT_FOUND", "文档不存在")
            if title is not None:
                document.title = title
            if category_id is not None:
                self._resolve_category(db, category_id)
                document.category_id = category_id
            if source is not None:
                document.source = source
            if notes is not None:
                document.notes = notes
            if tags is not None:
                db.execute(
                    select(DocumentTag).where(DocumentTag.document_id == document.id)
                )
                for row in db.scalars(
                    select(DocumentTag).where(DocumentTag.document_id == document.id)
                ):
                    db.delete(row)
                for name in tags:
                    self._link_tag(db, document, name)
            db.commit()
            return self._document_dict(db, document)

    def get_page(
        self,
        document_id: uuid.UUID,
        page_number: int,
        raw: bool,
        chunk_id: uuid.UUID | None = None,
        include_anchors: bool = False,
    ) -> dict:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if not document or document.status == DocumentStatus.DELETED:
                raise ApiError(404, "NOT_FOUND", "文档不存在")
            version = (
                db.get(DocumentVersion, document.current_version_id)
                if document.current_version_id
                else None
            )
            if not version:
                raise ApiError(404, "NOT_FOUND", "文档尚未处理完成")
            page = db.scalar(
                select(Page).where(
                    Page.version_id == version.id,
                    Page.pipeline_revision == document.active_pipeline_revision,
                    Page.page_number == page_number,
                )
            )
            if not page:
                raise ApiError(404, "NOT_FOUND", "页面不存在")
            text = page.cleaned_text
            anchors: list[dict] = []
            if include_anchors or chunk_id:
                statement = select(ChunkAnchor).where(
                    ChunkAnchor.version_id == version.id,
                    ChunkAnchor.pipeline_revision == document.active_pipeline_revision,
                    ChunkAnchor.page_number == page_number,
                )
                if chunk_id:
                    statement = statement.where(ChunkAnchor.chunk_id == chunk_id)
                for anchor in db.scalars(statement.order_by(ChunkAnchor.id)).all():
                    confidence = anchor.confidence
                    if hasattr(confidence, "as_tuple"):
                        confidence = float(confidence)
                    anchors.append(
                        {
                            "chunk_id": str(anchor.chunk_id),
                            "start_offset": anchor.start_offset,
                            "end_offset": anchor.end_offset,
                            "quote": anchor.quote,
                            "anchor_type": anchor.anchor_type,
                            "match_method": anchor.match_method,
                            "confidence": confidence,
                            "status": anchor.status,
                        }
                    )
            return {
                "document_id": str(document_id),
                "version_number": version.version_number,
                "page_number": page.page_number,
                "source_type": page.source_type.value,
                "view": "raw",
                "text": text,
                "spans": [],
                "quality_warnings": page.layout_warning_codes,
                "anchors": anchors,
                "highlights": [
                    anchor
                    for anchor in anchors
                    if anchor["start_offset"] is not None
                    and anchor["end_offset"] is not None
                ],
            }

    def get_chunk_anchors(
        self, document_id: uuid.UUID, chunk_id: uuid.UUID
    ) -> dict:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            chunk = db.get(Chunk, chunk_id)
            if (
                not document
                or document.status == DocumentStatus.DELETED
                or not chunk
                or chunk.document_id != document_id
            ):
                raise ApiError(404, "NOT_FOUND", "切分块不存在")
            anchors = []
            statement = (
                select(ChunkAnchor)
                .where(ChunkAnchor.chunk_id == chunk_id)
                .order_by(ChunkAnchor.page_number, ChunkAnchor.id)
            )
            for anchor in db.scalars(statement).all():
                confidence = anchor.confidence
                if hasattr(confidence, "as_tuple"):
                    confidence = float(confidence)
                anchors.append(
                    {
                        "chunk_id": str(anchor.chunk_id),
                        "page_number": anchor.page_number,
                        "start_offset": anchor.start_offset,
                        "end_offset": anchor.end_offset,
                        "quote": anchor.quote,
                        "anchor_type": anchor.anchor_type,
                        "match_method": anchor.match_method,
                        "confidence": confidence,
                        "status": anchor.status,
                    }
                )
            return {
                "document_id": str(document_id),
                "chunk_id": str(chunk_id),
                "anchors": anchors,
            }

    def get_quality_report(self, document_id: uuid.UUID) -> dict:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if not document or document.status == DocumentStatus.DELETED:
                raise ApiError(404, "NOT_FOUND", "文档不存在")
            version_id = document.current_version_id
            if not version_id:
                raise ApiError(404, "NOT_FOUND", "尚未生成质量报告")
            report = db.scalar(
                select(QualityReport)
                .where(QualityReport.document_id == document_id)
                .order_by(QualityReport.created_at.desc())
            )
            if not report:
                raise ApiError(404, "NOT_FOUND", "尚未生成质量报告")
            return _quality_dict(report)

    def get_job(self, job_id: uuid.UUID) -> dict:
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            if not job:
                raise ApiError(404, "NOT_FOUND", "任务不存在")
            return _job_dict(job, _job_file_map(db, [job]).get(job.id))

    def retry_job(self, job_id: uuid.UUID) -> dict:
        """Re-queue a failed/cancelled job on its original file."""
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            if not job:
                raise ApiError(404, "NOT_FOUND", "任务不存在")
            if job.status not in (
                JobStatus.FAILED,
                JobStatus.CANCELLED,
                JobStatus.PARTIAL_SUCCESS,
            ):
                raise ApiError(409, "CONFLICT", "仅失败或已取消的任务可以重试")
            version = db.get(DocumentVersion, job.version_id)
            stored = db.get(StoredFile, version.file_id) if version else None
            if not stored:
                raise ApiError(409, "CONFLICT", "原文件不存在，请重新上传")
            document = db.get(Document, job.document_id)
            if document:
                document.status = DocumentStatus.PROCESSING
                job.target_activation_epoch = document.activation_epoch
            if version and version.status == VersionStatus.FAILED:
                version.status = VersionStatus.PROCESSING
            job.status = JobStatus.QUEUED
            job.current_stage = JobStage.VALIDATION
            job.attempt_count = 0
            job.error_code = None
            job.safe_error_message = None
            job.processed_pages = 0
            job.started_at = None
            job.finished_at = None
            job.heartbeat_at = utcnow()
            db.add(
                JobEvent(
                    job_id=job.id,
                    sequence=(db.scalar(
                        select(func.count())
                        .select_from(JobEvent)
                        .where(JobEvent.job_id == job.id)
                    ) or 0) + 1,
                    from_status=JobStatus.FAILED.value,
                    to_status=JobStatus.QUEUED.value,
                    stage=JobStage.VALIDATION.value,
                    message="管理员手动重试",
                )
            )
            db.commit()
            response = _job_dict(job, _job_file_map(db, [job]).get(job.id))
            storage_key = stored.storage_key
        self._enqueue(str(job_id), storage_key)
        return response

    def cancel_job(self, job_id: uuid.UUID) -> dict:
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            if not job:
                raise ApiError(404, "NOT_FOUND", "任务不存在")
            if job.status in (
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            ):
                raise ApiError(409, "CONFLICT", "该任务已结束，无需取消")
            job.status = JobStatus.CANCELLED
            job.finished_at = utcnow()
            document = db.get(Document, job.document_id)
            if document and document.status == DocumentStatus.PROCESSING:
                document.status = DocumentStatus.NEEDS_REVIEW
            db.commit()
            response = _job_dict(job, _job_file_map(db, [job]).get(job.id))
        self._prune_job_history()
        return response

    def _prune_job_history(self) -> None:
        """取消后立刻按保留数收敛任务列表；清理失败不影响取消结果。"""
        try:
            from occupational_health.services.jobs.retention import prune_job_history

            prune_job_history(self.settings.job_history_keep)
        except Exception:  # pragma: no cover - 清理是尽力而为
            pass

    def list_jobs(
        self,
        page: int,
        page_size: int,
        status: str | None,
        document_id: uuid.UUID | None,
        job_ids: list[uuid.UUID] | None = None,
    ) -> tuple[list[dict], dict]:
        with SessionLocal() as db:
            statement = select(ProcessingJob).order_by(ProcessingJob.created_at.desc())
            if status:
                statement = statement.where(ProcessingJob.status == status)
            if document_id:
                statement = statement.where(ProcessingJob.document_id == document_id)
            if job_ids:
                statement = statement.where(ProcessingJob.id.in_(job_ids))
            total = db.scalar(select(func.count()).select_from(statement.subquery()))
            jobs = list(
                db.scalars(statement.offset((page - 1) * page_size).limit(page_size))
            )
            file_map = _job_file_map(db, jobs)
            return [_job_dict(job, file_map.get(job.id)) for job in jobs], self._list_meta(
                total or 0, page, page_size
            )

    def dashboard_summary(self, refresh: bool = False) -> dict:
        ttl = self.settings.dashboard_cache_seconds
        now = time.monotonic()
        if not refresh and ttl > 0 and self._summary_cache is not None:
            expires, cached = self._summary_cache
            if expires > now:
                return cached
        data = self._compute_dashboard_summary()
        self._summary_cache = (now + ttl, data)
        return data

    def _compute_dashboard_summary(self) -> dict:
        with SessionLocal() as db:
            active = Document.status != DocumentStatus.DELETED
            status_counts = {
                status.value: count
                for status, count in db.execute(
                    select(Document.status, func.count())
                    .where(active)
                    .group_by(Document.status)
                ).all()
            }
            total = sum(status_counts.values())
            category_rows = db.execute(
                select(Category, func.count(Document.id))
                .join(Document, Document.category_id == Category.id)
                .where(active)
                .group_by(Category.id)
                .order_by(func.count(Document.id).desc())
            ).all()
            tag_rows = db.execute(
                select(Tag.id, Tag.name, func.count(DocumentTag.document_id))
                .join(DocumentTag, DocumentTag.tag_id == Tag.id)
                .join(Document, Document.id == DocumentTag.document_id)
                .where(active, Tag.merged_into_id.is_(None))
                .group_by(Tag.id, Tag.name)
                .order_by(func.count(DocumentTag.document_id).desc())
                .limit(50)
            ).all()
            recent = list(
                db.scalars(
                    select(Document)
                    .where(active)
                    .order_by(Document.updated_at.desc())
                    .limit(100)
                )
            )
            category_map = {category.id: category for category, _ in category_rows}
            prefetch = self._prefetch_document_relations(
                db, recent, categories=category_map
            )
            recent_documents = [
                self._document_dict(db, document, prefetch) for document in recent
            ]
        return {
            "total": total,
            "status_counts": status_counts,
            "categories": [
                {
                    "id": str(category.id),
                    "code": category.code,
                    "name": category.name,
                    "active": category.active,
                    "count": count,
                }
                for category, count in category_rows
            ],
            "tags": [
                {"id": str(tag_id), "name": name, "count": count}
                for tag_id, name, count in tag_rows
            ],
            "recent_documents": recent_documents,
        }

    def list_categories(self) -> list[dict]:
        with SessionLocal() as db:
            return [
                {
                    "id": str(category.id),
                    "code": category.code,
                    "name": category.name,
                    "active": category.active,
                }
                for category in db.scalars(
                    select(Category)
                    .where(Category.active.is_(True))
                    .order_by(Category.sort_order)
                )
            ]

    def create_category(self, code: str, name: str) -> dict:
        with SessionLocal() as db:
            category = Category(code=code, name=name)
            db.add(category)
            try:
                db.commit()
            except IntegrityError as exc:
                raise ApiError(409, "CONFLICT", "分类 code 或 name 已存在") from exc
            return {
                "id": str(category.id),
                "code": category.code,
                "name": category.name,
                "active": category.active,
            }

    def list_tags(
        self, q: str | None, page: int, page_size: int
    ) -> tuple[list[dict], dict]:
        with SessionLocal() as db:
            statement = select(Tag).where(Tag.merged_into_id.is_(None))
            if q:
                statement = statement.where(Tag.normalized_name.contains(q.casefold()))
            total = db.scalar(select(func.count()).select_from(statement.subquery()))
            tags = list(
                db.scalars(
                    statement.order_by(Tag.created_at)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            return [
                {"id": str(tag.id), "name": tag.name} for tag in tags
            ], self._list_meta(total or 0, page, page_size)

    def create_tag(self, name: str) -> dict:
        with SessionLocal() as db:
            normalized = name.strip().casefold()
            tag = db.scalar(select(Tag).where(Tag.normalized_name == normalized))
            if tag:
                return {"id": str(tag.id), "name": tag.name, "duplicate": True}
            tag = Tag(name=name.strip(), normalized_name=normalized)
            db.add(tag)
            db.commit()
            return {"id": str(tag.id), "name": tag.name, "duplicate": False}


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _quality_dict(report: QualityReport) -> dict:
    return {
        "document_id": str(report.document_id),
        "version_id": str(report.version_id),
        "job_id": str(report.job_id),
        "pipeline_revision": str(report.pipeline_revision),
        "page_count": report.page_count,
        "effective_char_count": report.effective_char_count,
        "chunk_count": report.chunk_count,
        "ocr_page_ratio": float(report.ocr_page_ratio or 0),
        "average_ocr_confidence": (
            float(report.average_ocr_confidence)
            if report.average_ocr_confidence is not None
            else None
        ),
        "noise_char_count": report.noise_char_count,
        "low_quality_pages": report.low_quality_pages,
        "failed_pages": report.failed_pages,
        "processing_duration_ms": report.processing_duration_ms,
        "created_at": report.created_at,
    }


def _job_file_map(
    db: Session, jobs: list[ProcessingJob]
) -> dict[uuid.UUID, tuple[str | None, str | None]]:
    """Resolve the uploaded filename and document title for a batch of jobs."""
    job_ids = [job.id for job in jobs]
    if not job_ids:
        return {}
    rows = db.execute(
        select(ProcessingJob.id, StoredFile.original_filename, Document.title)
        .join(DocumentVersion, DocumentVersion.id == ProcessingJob.version_id)
        .join(StoredFile, StoredFile.id == DocumentVersion.file_id)
        .join(Document, Document.id == ProcessingJob.document_id)
        .where(ProcessingJob.id.in_(job_ids))
    ).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def _job_dict(
    job: ProcessingJob, info: tuple[str | None, str | None] | None = None
) -> dict:
    filename, document_title = info or (None, None)
    return {
        "id": str(job.id),
        "document_id": str(job.document_id),
        "version_id": str(job.version_id) if job.version_id else None,
        "filename": filename,
        "document_title": document_title,
        "job_type": job.job_type.value,
        "status": job.status.value,
        "current_stage": job.current_stage.value,
        "chunk_mode": job.chunk_mode,
        "chunk_target_tokens": job.chunk_target_tokens,
        "chunk_max_tokens": job.chunk_max_tokens,
        "chunk_overlap_tokens": job.chunk_overlap_tokens,
        "pipeline_revision": str(job.pipeline_revision),
        "processed_pages": job.processed_pages,
        "total_pages": job.total_pages,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "heartbeat_at": job.heartbeat_at,
        "retry_of_job_id": str(job.retry_of_job_id) if job.retry_of_job_id else None,
        "error": (
            {"code": job.error_code, "message": job.safe_error_message}
            if job.error_code
            else None
        ),
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }
