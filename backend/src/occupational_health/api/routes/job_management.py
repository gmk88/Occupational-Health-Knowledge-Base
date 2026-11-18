from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from occupational_health.api.dependencies.auth import require_admin
from occupational_health.core.errors import success
from occupational_health.core.security import PrincipalData

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post("/{job_id}/retry")
def retry_job(
    request: Request, job_id: str, principal: PrincipalData = Depends(require_admin)
) -> dict:
    return success(
        request.app.state.management_service.retry_job(uuid.UUID(job_id), principal.id)
    )


@router.post("/{job_id}/cancel")
def cancel_job(
    request: Request, job_id: str, principal: PrincipalData = Depends(require_admin)
) -> dict:
    return success(
        request.app.state.management_service.cancel_job(uuid.UUID(job_id), principal.id)
    )
