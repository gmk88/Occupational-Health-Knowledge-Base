from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from occupational_health.api.dependencies.auth import require_user
from occupational_health.core.errors import ApiError
from occupational_health.core.security import PrincipalData


def require_scope(scope: str):
    def dependency(
        request: Request,
        principal: Annotated[PrincipalData, Depends(require_user)],
    ) -> PrincipalData:
        if principal.role != "service" or scope not in principal.scopes:
            raise ApiError(403, "FORBIDDEN", f"缺少 {scope} 权限")
        return principal

    return dependency
