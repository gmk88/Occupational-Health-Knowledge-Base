from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from occupational_health.api.dependencies.auth import require_user
from occupational_health.api.schemas.search import SearchRequest
from occupational_health.core.errors import ApiError, success
from occupational_health.core.security import PrincipalData
from occupational_health.domain.enums import UserRole

router = APIRouter(prefix="/search", tags=["Search"])


@router.post("")
def search(
    request: Request,
    payload: SearchRequest,
    principal: PrincipalData = Depends(require_user),
) -> dict:
    if payload.include_raw and principal.role != UserRole.ADMIN:
        raise ApiError(403, "FORBIDDEN", "原文检索仅管理员可用")
    filters = payload.filters.model_dump()
    data = request.app.state.retrieval_service.search(
        principal,
        payload.query,
        payload.mode,
        payload.top_k,
        filters,
        payload.include_raw,
    )
    return success(data)
