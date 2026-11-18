from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid

from sqlalchemy import select

from occupational_health.core.errors import ApiError
from occupational_health.core.security import PrincipalData
from occupational_health.db.models.api_client import APIClient, APIKey
from occupational_health.db.session import SessionLocal, utcnow
from occupational_health.domain.enums import ActorType, UserRole

ALLOWED_SCOPES = {
    "documents:read",
    "documents:write",
    "search:read",
    "jobs:read",
    "health:read",
}

CLIENT_STATUSES = {"active", "disabled"}

# 每个请求都查库不划算；限额变更后最多延迟一分钟生效。
_LIMIT_CACHE: dict[uuid.UUID, tuple[int, float]] = {}
_UPLOAD_LIMIT_CACHE: dict[uuid.UUID, tuple[int, float]] = {}
_LIMIT_TTL_SECONDS = 60.0


class ApiClientService:
    def create_client(
        self,
        name: str,
        scopes: list[str],
        rate_limit_per_minute: int = 60,
        upload_limit_per_minute: int = 10,
    ) -> tuple[dict, str]:
        invalid = set(scopes) - ALLOWED_SCOPES
        if invalid:
            raise ApiError(
                400, "VALIDATION_ERROR", f"不支持的 scope: {sorted(invalid)}"
            )
        if not scopes:
            raise ApiError(400, "VALIDATION_ERROR", "至少需要一个 scope")
        raw = _new_key()
        with SessionLocal() as db:
            if db.scalar(select(APIClient).where(APIClient.name == name)):
                raise ApiError(409, "CONFLICT", "接入方名称已存在")
            client = APIClient(
                name=name,
                scopes=sorted(scopes),
                rate_limit_per_minute=rate_limit_per_minute,
                upload_limit_per_minute=upload_limit_per_minute,
            )
            db.add(client)
            db.flush()
            db.add(
                APIKey(
                    client_id=client.id,
                    key_prefix=raw[:10],
                    secret_hash=hash_key(raw),
                )
            )
            db.commit()
            detail = _client_detail(db, client)
        return {**detail, "key": raw}, raw

    def list_clients(self) -> list[dict]:
        with SessionLocal() as db:
            clients = list(db.scalars(select(APIClient).order_by(APIClient.created_at)))
            return [_client_detail(db, client) for client in clients]

    def update_client(
        self,
        client_id: uuid.UUID,
        *,
        name: str | None = None,
        status: str | None = None,
        scopes: list[str] | None = None,
        rate_limit_per_minute: int | None = None,
        upload_limit_per_minute: int | None = None,
    ) -> dict:
        with SessionLocal() as db:
            client = _get_client(db, client_id)
            if name is not None:
                name = name.strip()
                if not name:
                    raise ApiError(400, "VALIDATION_ERROR", "名称不能为空")
                exists = db.scalar(select(APIClient).where(APIClient.name == name))
                if exists and exists.id != client.id:
                    raise ApiError(409, "CONFLICT", "接入方名称已存在")
                client.name = name
            if status is not None:
                if status not in CLIENT_STATUSES:
                    raise ApiError(400, "VALIDATION_ERROR", "状态取值不合法")
                client.status = status
            if scopes is not None:
                invalid = set(scopes) - ALLOWED_SCOPES
                if invalid:
                    raise ApiError(
                        400, "VALIDATION_ERROR", f"不支持的 scope: {sorted(invalid)}"
                    )
                if not scopes:
                    raise ApiError(400, "VALIDATION_ERROR", "至少需要一个 scope")
                client.scopes = sorted(scopes)
            if rate_limit_per_minute is not None:
                client.rate_limit_per_minute = rate_limit_per_minute
            if upload_limit_per_minute is not None:
                client.upload_limit_per_minute = upload_limit_per_minute
            client.updated_at = utcnow()
            db.commit()
            _LIMIT_CACHE.pop(client.id, None)
            _UPLOAD_LIMIT_CACHE.pop(client.id, None)
            return _client_detail(db, client)

    def rotate_key(self, client_id: uuid.UUID) -> dict:
        """Issue a new key and revoke the previous active ones."""
        with SessionLocal() as db:
            client = _get_client(db, client_id)
            now = utcnow()
            active = list(
                db.scalars(
                    select(APIKey).where(
                        APIKey.client_id == client.id,
                        APIKey.revoked_at.is_(None),
                    )
                )
            )
            for key in active:
                key.revoked_at = now
            raw = _new_key()
            db.add(
                APIKey(
                    client_id=client.id,
                    key_prefix=raw[:10],
                    secret_hash=hash_key(raw),
                )
            )
            db.commit()
            detail = _client_detail(db, client)
        return {**detail, "key": raw}

    def revoke_key(self, client_id: uuid.UUID, key_id: uuid.UUID) -> dict:
        with SessionLocal() as db:
            client = _get_client(db, client_id)
            key = db.get(APIKey, key_id)
            if not key or key.client_id != client.id:
                raise ApiError(404, "NOT_FOUND", "密钥不存在")
            if key.revoked_at is None:
                key.revoked_at = utcnow()
                db.commit()
            return _client_detail(db, client)

    def limit_for(self, client_id: uuid.UUID) -> int:
        """Per-client requests-per-minute, cached briefly."""
        now = time.monotonic()
        cached = _LIMIT_CACHE.get(client_id)
        if cached and cached[1] > now:
            return cached[0]
        with SessionLocal() as db:
            client = db.get(APIClient, client_id)
            limit = client.rate_limit_per_minute if client else 60
        _LIMIT_CACHE[client_id] = (limit, now + _LIMIT_TTL_SECONDS)
        return limit

    def upload_limit_for(self, client_id: uuid.UUID) -> int:
        """Per-client uploads-per-minute, cached briefly."""
        now = time.monotonic()
        cached = _UPLOAD_LIMIT_CACHE.get(client_id)
        if cached and cached[1] > now:
            return cached[0]
        with SessionLocal() as db:
            client = db.get(APIClient, client_id)
            limit = client.upload_limit_per_minute if client else 10
        _UPLOAD_LIMIT_CACHE[client_id] = (limit, now + _LIMIT_TTL_SECONDS)
        return limit

    def authenticate(self, raw_key: str) -> PrincipalData:
        secret_hash = hash_key(raw_key)
        with SessionLocal() as db:
            row = db.execute(
                select(APIKey, APIClient)
                .join(APIClient, APIClient.id == APIKey.client_id)
                .where(APIKey.secret_hash == secret_hash)
            ).first()
            if not row:
                raise ApiError(401, "API_KEY_EXPIRED", "密钥无效或过期")
            key, client = row
            now = utcnow()
            if key.revoked_at or (key.expires_at and key.expires_at <= now):
                raise ApiError(401, "API_KEY_EXPIRED", "密钥无效或过期")
            if client.status != "active":
                raise ApiError(401, "UNAUTHORIZED", "接入方已停用")
            # 每个请求都写 last_used_at 会造成大量无用提交，最多每分钟一次。
            last_used = key.last_used_at
            if last_used is None or (now - last_used).total_seconds() >= 60:
                key.last_used_at = now
                db.commit()
            return PrincipalData(
                client.id,
                client.name,
                ActorType.API_CLIENT,
                UserRole.SERVICE,
                scopes=list(client.scopes),
            )


def _new_key() -> str:
    return f"oh_{secrets.token_urlsafe(32)}"


def _get_client(db, client_id: uuid.UUID) -> APIClient:
    client = db.get(APIClient, client_id)
    if not client:
        raise ApiError(404, "NOT_FOUND", "接入方不存在")
    return client


def _client_detail(db, client: APIClient) -> dict:
    keys = list(
        db.scalars(
            select(APIKey)
            .where(APIKey.client_id == client.id)
            .order_by(APIKey.created_at)
        )
    )
    active = [key for key in keys if key.revoked_at is None]
    latest = keys[-1] if keys else None
    used = [key.last_used_at for key in keys if key.last_used_at]
    return {
        "id": str(client.id),
        "name": client.name,
        "status": client.status,
        "scopes": list(client.scopes),
        "rate_limit_per_minute": client.rate_limit_per_minute,
        "upload_limit_per_minute": client.upload_limit_per_minute,
        "created_at": client.created_at,
        "updated_at": client.updated_at,
        "key_prefix": latest.key_prefix if latest else None,
        "key_created_at": latest.created_at if latest else None,
        "last_used_at": max(used) if used else None,
        "active_key_count": len(active),
        "keys": [
            {
                "id": str(key.id),
                "key_prefix": key.key_prefix,
                "created_at": key.created_at,
                "expires_at": key.expires_at,
                "revoked_at": key.revoked_at,
                "last_used_at": key.last_used_at,
            }
            for key in keys
        ],
    }


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_key_constant_time(provided: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_key(provided), expected_hash)
