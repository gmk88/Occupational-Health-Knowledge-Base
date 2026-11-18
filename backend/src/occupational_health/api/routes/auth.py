from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from occupational_health.api.dependencies.auth import require_user
from occupational_health.api.schemas.auth import LoginRequest
from occupational_health.core.errors import success
from occupational_health.core.security import PrincipalData

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    principal, raw_token = request.app.state.auth_service.login(
        payload.login_name,
        payload.password,
        request.headers.get("user-agent"),
    )
    settings = request.app.state.settings
    response.set_cookie(
        "oh_session",
        raw_token,
        max_age=settings.session_ttl_minutes * 60,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return success(principal.to_dict())


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    request.app.state.auth_service.logout(request.cookies.get("oh_session"))
    response.delete_cookie(
        "oh_session",
        path="/",
        secure=request.app.state.settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return success(None)


@router.get("/me")
def me(principal: Annotated[PrincipalData, Depends(require_user)]) -> dict:
    return success(principal.to_dict())
