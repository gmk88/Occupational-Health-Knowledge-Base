from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request

from occupational_health.api.dependencies.auth import require_admin, require_user
from occupational_health.core.errors import ApiError, success
from occupational_health.core.security import PrincipalData

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("")
def list_jobs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    document_id: str | None = None,
    ids: str | None = None,
    _principal: PrincipalData = Depends(require_user),
) -> dict:
    job_ids = _parse_job_ids(ids) if ids else None
    items, meta = request.app.state.document_service.list_jobs(
        page,
        page_size,
        status,
        uuid.UUID(document_id) if document_id else None,
        job_ids,
    )
    return success({"items": items, "meta": meta})


def _parse_job_ids(raw: str) -> list[uuid.UUID]:
    """解析逗号分隔的任务 ID，去重并限制数量，非法值直接 400。"""
    seen: list[uuid.UUID] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            parsed = uuid.UUID(item)
        except ValueError as exc:
            raise ApiError(400, "VALIDATION_ERROR", "无效的任务 ID") from exc
        if parsed not in seen:
            seen.append(parsed)
    if len(seen) > 100:
        raise ApiError(400, "VALIDATION_ERROR", "一次最多查询 100 个任务")
    return seen


@router.get("/{job_id}")
def get_job(
    request: Request, job_id: str, _principal: PrincipalData = Depends(require_user)
) -> dict:
    return success(request.app.state.document_service.get_job(uuid.UUID(job_id)))


@router.post("/{job_id}/retry")
def retry_job(
    request: Request,
    job_id: str,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(request.app.state.document_service.retry_job(uuid.UUID(job_id)))


@router.post("/{job_id}/cancel")
def cancel_job(
    request: Request,
    job_id: str,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(request.app.state.document_service.cancel_job(uuid.UUID(job_id)))
