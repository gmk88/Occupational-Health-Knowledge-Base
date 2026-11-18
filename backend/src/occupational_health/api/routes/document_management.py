from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from occupational_health.api.dependencies.auth import require_admin
from occupational_health.core.errors import success
from occupational_health.core.security import PrincipalData

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.delete("/{document_id}")
def delete_document(
    request: Request,
    document_id: str,
    principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        request.app.state.management_service.delete_document(
            uuid.UUID(document_id), principal.id
        )
    )


@router.post("/{document_id}/reprocess")
def reprocess_document(
    request: Request,
    document_id: str,
    principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        request.app.state.management_service.reprocess(
            uuid.UUID(document_id), principal.id
        )
    )
