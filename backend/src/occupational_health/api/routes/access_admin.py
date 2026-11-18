"""Access management: API clients, keys, accounts and usage."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from occupational_health.api.dependencies.auth import require_admin
from occupational_health.core.errors import success
from occupational_health.core.security import PrincipalData
from occupational_health.domain.enums import AccountStatus, UserRole
from occupational_health.services.analytics.usage import client_usage, usage_overview
from occupational_health.services.api_clients.service import ALLOWED_SCOPES
from occupational_health.services.identity.users import UserAdminService

router = APIRouter(prefix="/access", tags=["Access"])


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=lambda: ["search:read"])
    rate_limit_per_minute: int = Field(default=60, ge=1, le=6000)
    upload_limit_per_minute: int = Field(default=0, ge=0, le=600)


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    status: Literal["active", "disabled"] | None = None
    scopes: list[str] | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=6000)
    upload_limit_per_minute: int | None = Field(default=None, ge=0, le=600)


class UserCreate(BaseModel):
    login_name: str = Field(min_length=2, max_length=100)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    role: Literal["admin", "viewer"] = "viewer"


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Literal["admin", "viewer"] | None = None
    status: Literal["active", "disabled"] | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=200)


@router.get("/clients")
def list_clients(
    request: Request, _principal: PrincipalData = Depends(require_admin)
) -> dict:
    return success(request.app.state.api_client_service.list_clients())


@router.post("/clients")
def create_client(
    request: Request,
    payload: ClientCreate,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    detail, _raw = request.app.state.api_client_service.create_client(
        payload.name,
        payload.scopes,
        payload.rate_limit_per_minute,
        payload.upload_limit_per_minute,
    )
    return success(detail)


@router.patch("/clients/{client_id}")
def update_client(
    request: Request,
    client_id: str,
    payload: ClientUpdate,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        request.app.state.api_client_service.update_client(
            uuid.UUID(client_id),
            name=payload.name,
            status=payload.status,
            scopes=payload.scopes,
            rate_limit_per_minute=payload.rate_limit_per_minute,
            upload_limit_per_minute=payload.upload_limit_per_minute,
        )
    )


@router.post("/clients/{client_id}/keys")
def rotate_key(
    request: Request,
    client_id: str,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        request.app.state.api_client_service.rotate_key(uuid.UUID(client_id))
    )


@router.delete("/clients/{client_id}/keys/{key_id}")
def revoke_key(
    request: Request,
    client_id: str,
    key_id: str,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        request.app.state.api_client_service.revoke_key(
            uuid.UUID(client_id), uuid.UUID(key_id)
        )
    )


@router.get("/clients/{client_id}/usage")
def get_client_usage(
    client_id: str,
    days: int = Query(default=7, ge=1, le=90),
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(client_usage(uuid.UUID(client_id), days))


@router.get("/usage")
def get_usage(
    days: int = Query(default=7, ge=1, le=90),
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    clients, daily = usage_overview(days)
    return success({"days": days, "clients": clients, "daily": daily})


@router.get("/scopes")
def list_scopes(_principal: PrincipalData = Depends(require_admin)) -> dict:
    return success(sorted(ALLOWED_SCOPES))


@router.get("/users")
def list_users(_principal: PrincipalData = Depends(require_admin)) -> dict:
    return success(UserAdminService().list_users())


@router.post("/users")
def create_user(
    payload: UserCreate, _principal: PrincipalData = Depends(require_admin)
) -> dict:
    return success(
        UserAdminService().create_user(
            payload.login_name,
            payload.display_name,
            payload.password,
            UserRole(payload.role),
        )
    )


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    payload: UserUpdate,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        UserAdminService().update_user(
            uuid.UUID(user_id),
            display_name=payload.display_name,
            role=UserRole(payload.role) if payload.role else None,
            status=AccountStatus(payload.status) if payload.status else None,
        )
    )


@router.post("/users/{user_id}/password")
def reset_password(
    user_id: str,
    payload: PasswordReset,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        UserAdminService().reset_password(uuid.UUID(user_id), payload.password)
    )
