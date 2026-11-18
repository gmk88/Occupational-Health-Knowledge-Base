from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from occupational_health.api.dependencies.auth import require_admin
from occupational_health.core.errors import success
from occupational_health.core.security import PrincipalData

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/{document_id}/masking-corrections")
def correct_masking(
    request: Request,
    document_id: str,
    principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        request.app.state.management_service.correct_masking(
            uuid.UUID(document_id), principal.id
        )
    )
