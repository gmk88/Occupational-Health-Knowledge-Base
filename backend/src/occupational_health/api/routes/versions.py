from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from occupational_health.api.dependencies.auth import require_admin, require_user
from occupational_health.core.errors import success
from occupational_health.core.security import PrincipalData

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("/{document_id}/versions")
def list_versions(
    request: Request,
    document_id: str,
    _principal: PrincipalData = Depends(require_user),
) -> dict:
    return success(
        request.app.state.management_service.list_versions(uuid.UUID(document_id))
    )


@router.post("/{document_id}/versions/{version_number}/rollback")
def rollback(
    request: Request,
    document_id: str,
    version_number: int,
    principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        request.app.state.management_service.rollback(
            uuid.UUID(document_id), version_number, principal.id
        )
    )
