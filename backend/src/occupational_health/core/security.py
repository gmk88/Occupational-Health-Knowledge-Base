from __future__ import annotations

import hashlib
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from occupational_health.core.errors import ApiError
from occupational_health.domain.enums import AccountStatus, ActorType, UserRole

password_hasher = PasswordHasher()


def normalize_login(value: str) -> str:
    return value.strip().casefold()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, ValueError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class UserRecord:
    id: uuid.UUID
    login_name: str
    display_name: str
    password_hash: str
    role: UserRole
    status: AccountStatus = AccountStatus.ACTIVE
    failed_login_count: int = 0
    locked_until: datetime | None = None
    last_login_at: datetime | None = None


@dataclass
class SessionRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str
    expires_at: datetime
    idle_expires_at: datetime
    revoked_at: datetime | None = None
    last_seen_at: datetime = field(default_factory=utcnow)
    user_agent: str | None = None
    ip_hash: str | None = None


@dataclass
class PrincipalData:
    id: uuid.UUID
    name: str
    actor_type: ActorType
    role: UserRole
    scopes: list[str] = field(default_factory=list)
    session_expires_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "actor_type": self.actor_type.value,
            "role": self.role.value,
            "scopes": self.scopes,
            "session_expires_at": self.session_expires_at,
        }


class AuthStore(Protocol):
    def get_user_by_login(self, normalized_login: str) -> UserRecord | None: ...
    def get_user(self, user_id: uuid.UUID) -> UserRecord | None: ...
    def save_user(self, user: UserRecord) -> None: ...
    def create_session(self, session: SessionRecord) -> None: ...
    def get_session(self, token_hash: str) -> SessionRecord | None: ...
    def get_session_with_user(
        self, token_hash: str
    ) -> tuple[SessionRecord, UserRecord | None] | None: ...
    def save_session(self, session: SessionRecord) -> None: ...
    def revoke_session(self, token_hash: str) -> None: ...


class MemoryAuthStore:
    def __init__(self) -> None:
        self.users: dict[uuid.UUID, UserRecord] = {}
        self.sessions: dict[str, SessionRecord] = {}
        self._lock = threading.RLock()

    def add_user(self, login_name: str, password: str, role: UserRole) -> UserRecord:
        user = UserRecord(
            id=uuid.uuid4(),
            login_name=login_name.strip(),
            display_name=login_name.strip(),
            password_hash=hash_password(password),
            role=role,
        )
        with self._lock:
            if any(
                normalize_login(item.login_name) == normalize_login(login_name)
                for item in self.users.values()
            ):
                raise ValueError("login already exists")
            self.users[user.id] = user
        return user

    def disable_user(self, login_name: str) -> None:
        user = self.get_user_by_login(normalize_login(login_name))
        if user:
            user.status = AccountStatus.DISABLED
            self.save_user(user)

    def get_user_by_login(self, normalized_login: str) -> UserRecord | None:
        with self._lock:
            return next(
                (
                    u
                    for u in self.users.values()
                    if normalize_login(u.login_name) == normalized_login
                ),
                None,
            )

    def get_user(self, user_id: uuid.UUID) -> UserRecord | None:
        return self.users.get(user_id)

    def save_user(self, user: UserRecord) -> None:
        with self._lock:
            self.users[user.id] = user

    def create_session(self, session: SessionRecord) -> None:
        with self._lock:
            self.sessions[session.token_hash] = session

    def get_session(self, token_hash: str) -> SessionRecord | None:
        return self.sessions.get(token_hash)

    def get_session_with_user(
        self, token_hash: str
    ) -> tuple[SessionRecord, UserRecord | None] | None:
        session = self.sessions.get(token_hash)
        if not session:
            return None
        return session, self.users.get(session.user_id)

    def save_session(self, session: SessionRecord) -> None:
        with self._lock:
            self.sessions[session.token_hash] = session

    def revoke_session(self, token_hash: str) -> None:
        session = self.sessions.get(token_hash)
        if session:
            session.revoked_at = utcnow()
            self.save_session(session)


class AuthService:
    def __init__(self, store: AuthStore, settings, audit_service=None) -> None:
        self.store = store
        self.settings = settings
        self.audit = audit_service

    def login(
        self, login_name: str, password: str, user_agent: str | None = None
    ) -> tuple[PrincipalData, str]:
        user = self.store.get_user_by_login(normalize_login(login_name))
        now = utcnow()
        if user and user.locked_until and user.locked_until > now:
            raise ApiError(401, "UNAUTHORIZED", "账号已临时锁定，请稍后重试")
        if (
            not user
            or user.status != AccountStatus.ACTIVE
            or not verify_password(user.password_hash, password)
        ):
            if user:
                user.failed_login_count += 1
                if user.failed_login_count >= 5:
                    user.status = AccountStatus.LOCKED
                    user.locked_until = now + timedelta(minutes=15)
                self.store.save_user(user)
                self._audit("auth.login_failed", user.id, "denied")
            raise ApiError(401, "UNAUTHORIZED", "账号或密码错误")
        user.failed_login_count = 0
        user.status = AccountStatus.ACTIVE
        user.locked_until = None
        user.last_login_at = now
        self.store.save_user(user)
        raw_token = secrets.token_urlsafe(48)
        session = SessionRecord(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=now + timedelta(minutes=self.settings.session_ttl_minutes),
            idle_expires_at=now + timedelta(minutes=self.settings.session_idle_minutes),
            user_agent=(user_agent or "")[:500] or None,
        )
        self.store.create_session(session)
        self._audit("auth.login", user.id, "success")
        return (
            PrincipalData(
                user.id,
                user.display_name,
                ActorType.USER,
                user.role,
                session_expires_at=session.expires_at,
            ),
            raw_token,
        )

    def authenticate(self, raw_token: str | None) -> PrincipalData:
        if not raw_token:
            raise ApiError(401, "UNAUTHORIZED", "请先登录")
        row = self.store.get_session_with_user(hash_token(raw_token))
        now = utcnow()
        if not row:
            raise ApiError(401, "SESSION_EXPIRED", "会话已过期，请重新登录")
        session, user = row
        if (
            session.revoked_at
            or session.expires_at <= now
            or session.idle_expires_at <= now
        ):
            raise ApiError(401, "SESSION_EXPIRED", "会话已过期，请重新登录")
        if not user or user.status != AccountStatus.ACTIVE:
            raise ApiError(401, "UNAUTHORIZED", "账号不可用，请重新登录")
        # 高频轮询不必每次都写 session 表；只在空闲期过半时续期，
        # 既保持滑动过期语义，又避免每个请求一次数据库写提交。
        refresh_threshold = timedelta(
            minutes=self.settings.session_idle_minutes / 2
        )
        if session.idle_expires_at - now < refresh_threshold:
            session.last_seen_at = now
            session.idle_expires_at = now + timedelta(
                minutes=self.settings.session_idle_minutes
            )
            self.store.save_session(session)
        return PrincipalData(
            user.id,
            user.display_name,
            ActorType.USER,
            user.role,
            session_expires_at=session.expires_at,
        )

    def logout(self, raw_token: str | None) -> None:
        if raw_token:
            self.store.revoke_session(hash_token(raw_token))

    def _audit(self, action: str, actor_id: uuid.UUID, result: str) -> None:
        if self.audit:
            self.audit.record(ActorType.USER, actor_id, action, "session", None, result)
