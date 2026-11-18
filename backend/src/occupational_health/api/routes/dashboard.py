from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from occupational_health.api.dependencies.auth import require_user
from occupational_health.core.errors import success
from occupational_health.core.security import PrincipalData

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard/summary")
def dashboard_summary(
    request: Request,
    refresh: bool = Query(default=False),
    _principal: PrincipalData = Depends(require_user),
) -> dict:
    return success(
        request.app.state.document_service.dashboard_summary(refresh=refresh)
    )
