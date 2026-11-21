from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request, Response, UploadFile

from occupational_health.api.dependencies.auth import (
    require_admin,
    require_upload_quota,
    require_user,
)
from occupational_health.api.schemas.documents import (
    DocumentLifecyclePatch,
    DocumentPatch,
    DocumentRelationCreate,
)
from occupational_health.core.errors import ApiError, success
from occupational_health.core.security import PrincipalData
from occupational_health.domain.enums import UserRole

router = APIRouter(prefix="/documents", tags=["Documents"])

_COPY_CHUNK_BYTES = 1024 * 1024


def _copy_upload(file: UploadFile, destination: Path, max_bytes: int) -> int:
    """分块落盘并同步校验大小，避免整文件读入内存。"""
    written = 0
    source = file.file
    source.seek(0)
    with destination.open("wb") as target:
        while True:
            chunk = source.read(_COPY_CHUNK_BYTES)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                limit_mb = max_bytes // (1024 * 1024)
                raise ApiError(
                    413,
                    "FILE_TOO_LARGE",
                    f"文件超过 {limit_mb} MB 限制",
                )
            target.write(chunk)
    return written


def _service(request: Request):
    return request.app.state.document_service


def _uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ApiError(400, "VALIDATION_ERROR", "无效的 UUID") from exc


def _datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApiError(400, "VALIDATION_ERROR", "无效的日期时间") from exc


@router.post("")
def upload_document(
    request: Request,
    file: UploadFile,
    # 前端以 multipart/form-data 提交，这些字段必须声明为 Form，
    # 否则 FastAPI 会按查询参数解析，切分参数会被静默忽略。
    title: str | None = Form(default=None),
    category_id: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    source: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    chunk_mode: str = Form(default="parent_child"),
    chunk_target_tokens: int | None = Form(default=None, ge=64, le=8192),
    chunk_max_tokens: int | None = Form(default=None, ge=128, le=16384),
    chunk_overlap_tokens: int | None = Form(default=None, ge=0, le=4096),
    _principal: PrincipalData = Depends(require_upload_quota),
) -> dict:
    settings = request.app.state.settings
    suffix = Path(file.filename or "upload.pdf").suffix.lower() or ".pdf"
    temporary = Path(settings.storage_root) / "tmp" / f"{uuid.uuid4().hex}{suffix}"
    temporary.parent.mkdir(parents=True, exist_ok=True)
    try:
        _copy_upload(file, temporary, settings.max_file_size_bytes)
        result = _service(request).upload(
            temporary,
            file.filename or "upload.pdf",
            _principal.id,
            title,
            _uuid(category_id),
            _split_tags(tags),
            source,
            notes,
            chunk_mode,
            chunk_target_tokens,
            chunk_max_tokens,
            chunk_overlap_tokens,
        )
        return success(result)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            # 临时文件清理失败不影响上传结果（PyMuPDF 在 Windows 上可能延迟释放句柄）。
            pass


def _split_tags(tags: str | None) -> list[str]:
    if not tags:
        return []
    # 中文逗号也要支持，否则「苯，噪声」会被当成一个标签。
    return [
        item.strip() for item in re.split(r"[,，]", tags) if item.strip()
    ][:50]


@router.post("/auto-classify")
def auto_classify(
    request: Request,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    """Backfill category and tags for documents indexed before auto-tagging."""
    from occupational_health.services.documents.auto_tagging import backfill_documents

    return success(backfill_documents(request.app.state.settings))


@router.get("")
def list_documents(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="-created_at"),
    status: str | None = None,
    category_id: str | None = None,
    _principal: PrincipalData = Depends(require_user),
) -> dict:
    items, meta = _service(request).list_documents(
        page, page_size, sort, status, _uuid(category_id)
    )
    return success({"items": items, "meta": meta})


@router.get("/export")
def export_documents(
    request: Request,
    _principal: PrincipalData = Depends(require_user),
) -> Response:
    """Export the complete document catalog as an Excel-friendly UTF-8 CSV."""
    rows = _service(request).export_documents()
    fieldnames = list(rows[0].keys()) if rows else [
        "文档ID",
        "文档名称",
        "原始文件名",
        "标准号",
        "标准主编号",
        "版本年份",
        "生命周期状态",
        "文档角色",
        "场景",
        "标签",
        "处理状态",
        "版本号",
        "页数",
        "实施日期",
        "上传时间",
        "更新时间",
    ]
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    filename = f"documents-{stamp}.csv"
    display_name = f"职业健康知识库文档清单-{stamp}.csv"
    return Response(
        content=buffer.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"; '
                f"filename*=UTF-8''{quote(display_name)}"
            ),
            "Cache-Control": "no-store",
        },
    )


@router.get("/{document_id}")
def get_document(
    request: Request,
    document_id: str,
    _principal: PrincipalData = Depends(require_user),
) -> dict:
    return success(_service(request).get_document(uuid.UUID(document_id)))


@router.patch("/{document_id}")
def update_document(
    request: Request,
    document_id: str,
    payload: DocumentPatch,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        _service(request).update_metadata(
            uuid.UUID(document_id),
            payload.title,
            _uuid(payload.category_id),
            payload.tags,
            payload.source,
            payload.notes,
        )
    )


@router.patch("/{document_id}/lifecycle")
def update_lifecycle(
    request: Request,
    document_id: str,
    payload: DocumentLifecyclePatch,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        _service(request).update_lifecycle(
            uuid.UUID(document_id),
            lifecycle_status=payload.lifecycle_status,
            document_role=payload.document_role,
            standard_key=payload.standard_key,
            standard_no=payload.standard_no,
            edition_year=payload.edition_year,
            effective_date=_datetime(payload.effective_date),
            change_note=payload.change_note,
        )
    )


@router.get("/{document_id}/relations")
def list_relations(
    request: Request,
    document_id: str,
    _principal: PrincipalData = Depends(require_user),
) -> dict:
    return success(_service(request).list_relations(uuid.UUID(document_id)))


@router.post("/{document_id}/relations")
def link_relation(
    request: Request,
    document_id: str,
    payload: DocumentRelationCreate,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    target_id = _uuid(payload.target_document_id)
    if not target_id:
        raise ApiError(400, "VALIDATION_ERROR", "目标文档不能为空")
    return success(
        _service(request).link_relation(
            uuid.UUID(document_id),
            target_id,
            payload.relation_type,
            payload.volume_no,
            payload.note,
        )
    )


@router.get("/{document_id}/pages/{page_number}")
def get_page(
    request: Request,
    document_id: str,
    page_number: int,
    view: str = "masked",
    chunk_id: str | None = None,
    principal: PrincipalData = Depends(require_user),
) -> dict:
    raw = view == "raw"
    if raw and principal.role != UserRole.ADMIN:
        raise ApiError(403, "FORBIDDEN", "原文仅管理员可查看")
    return success(
        _service(request).get_page(
            uuid.UUID(document_id), page_number, raw, _uuid(chunk_id)
        )
    )


@router.get("/{document_id}/quality-report")
def quality_report(
    request: Request,
    document_id: str,
    _principal: PrincipalData = Depends(require_user),
) -> dict:
    return success(_service(request).get_quality_report(uuid.UUID(document_id)))
