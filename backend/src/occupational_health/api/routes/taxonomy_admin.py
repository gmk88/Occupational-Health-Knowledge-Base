from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from occupational_health.api.dependencies.auth import require_admin
from occupational_health.core.errors import success
from occupational_health.core.security import PrincipalData

router = APIRouter(tags=["Taxonomy"])


@router.post("/tags/{tag_id}/merge")
def merge_tag(
    request: Request,
    tag_id: str,
    target_tag_id: str,
    principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        request.app.state.management_service.merge_tags(
            uuid.UUID(tag_id), uuid.UUID(target_tag_id)
        )
    )
