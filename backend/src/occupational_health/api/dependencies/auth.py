from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from occupational_health.core.errors import ApiError
from occupational_health.core.security import PrincipalData
from occupational_health.domain.enums import ActorType, UserRole


def require_user(request: Request) -> PrincipalData:
    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        service = request.app.state.api_client_service
        principal = service.authenticate(authorization[7:])
        limiter = getattr(request.app.state, "rate_limiter", None)
        if limiter is not None:
            limit = service.limit_for(principal.id)
            result = limiter.allow(f"api_client:{principal.id}", limit)
            if not result.allowed:
                raise ApiError(
                    429,
                    "RATE_LIMITED",
                    "该接入方已超出每分钟调用额度",
                    retry_after=result.retry_after,
                )
        return principal
    return request.app.state.auth_service.authenticate(
        request.cookies.get("oh_session")
    )


def require_upload_quota(
    request: Request,
    principal: Annotated[PrincipalData, Depends(require_admin)],
) -> PrincipalData:
    """管理员上传也要受限：批量上传按用户/接入方单独计数。"""
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return principal
    settings = request.app.state.settings
    if principal.actor_type == ActorType.API_CLIENT:
        limit = request.app.state.api_client_service.upload_limit_for(principal.id)
        key = f"upload:client:{principal.id}"
    else:
        limit = settings.upload_limit_per_minute
        key = f"upload:user:{principal.id}"
    result = limiter.allow(key, limit)
    if not result.allowed:
        raise ApiError(
            429,
            "RATE_LIMITED",
            "上传过于频繁，请稍后重试",
            retry_after=result.retry_after,
        )
    return principal


def require_admin(
    request: Request,
    principal: Annotated[PrincipalData, Depends(require_user)],
) -> PrincipalData:
    if principal.role == UserRole.ADMIN:
        return principal
    if principal.role == UserRole.SERVICE and "documents:write" in principal.scopes:
        return principal
    request.app.state.audit_service.record(
        ActorType.USER,
        principal.id,
        "auth.forbidden",
        "endpoint",
        request.url.path,
        "denied",
    )
    raise ApiError(403, "FORBIDDEN", "当前账号无权执行管理操作")
