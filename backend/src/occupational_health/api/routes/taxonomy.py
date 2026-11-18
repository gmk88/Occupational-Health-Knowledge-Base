from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from occupational_health.api.dependencies.auth import require_admin, require_user
from occupational_health.api.schemas.taxonomy import CategoryInput, TagInput
from occupational_health.core.errors import success
from occupational_health.core.security import PrincipalData

router = APIRouter(tags=["Taxonomy"])


@router.get("/categories")
def list_categories(
    request: Request, _principal: PrincipalData = Depends(require_user)
) -> dict:
    return success(request.app.state.document_service.list_categories())


@router.post("/categories", status_code=201)
def create_category(
    request: Request,
    payload: CategoryInput,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        request.app.state.document_service.create_category(payload.code, payload.name)
    )


@router.get("/tags")
def list_tags(
    request: Request,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _principal: PrincipalData = Depends(require_user),
) -> dict:
    items, meta = request.app.state.document_service.list_tags(q, page, page_size)
    return success({"items": items, "meta": meta})


@router.post("/tags", status_code=201)
def create_tag(
    request: Request,
    payload: TagInput,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(request.app.state.document_service.create_tag(payload.name))
