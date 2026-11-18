"""Administrative user management.

Only admins can reach these operations; the service additionally guarantees the
platform never loses its last active administrator.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update

from occupational_health.core.errors import ApiError
from occupational_health.core.security import hash_password, normalize_login
from occupational_health.db.models.identity import Session, User
from occupational_health.db.session import SessionLocal, utcnow
from occupational_health.domain.enums import AccountStatus, UserRole

MANAGEABLE_ROLES = {UserRole.ADMIN, UserRole.VIEWER}


class UserAdminService:
    def list_users(self) -> list[dict]:
        with SessionLocal() as db:
            rows = list(db.scalars(select(User).order_by(User.created_at)))
            return [_user_dict(row) for row in rows]

    def create_user(
        self,
        login_name: str,
        display_name: str,
        password: str,
        role: UserRole = UserRole.VIEWER,
    ) -> dict:
        login = login_name.strip()
        if not login:
            raise ApiError(400, "VALIDATION_ERROR", "登录名不能为空")
        if role not in MANAGEABLE_ROLES:
            raise ApiError(400, "VALIDATION_ERROR", "只能创建管理员或只读账号")
        normalized = normalize_login(login)
        with SessionLocal() as db:
            exists = db.scalar(
                select(User).where(User.normalized_login == normalized)
            )
            if exists:
                raise ApiError(409, "CONFLICT", "登录名已存在")
            row = User(
                login_name=login,
                normalized_login=normalized,
                display_name=(display_name or login).strip(),
                password_hash=hash_password(password),
                role=role,
                status=AccountStatus.ACTIVE,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return _user_dict(row)

    def update_user(
        self,
        user_id: uuid.UUID,
        *,
        display_name: str | None = None,
        role: UserRole | None = None,
        status: AccountStatus | None = None,
    ) -> dict:
        with SessionLocal() as db:
            row = _get_user(db, user_id)
            losing_admin = row.role == UserRole.ADMIN and (
                (role is not None and role != UserRole.ADMIN)
                or (status is not None and status != AccountStatus.ACTIVE)
            )
            if losing_admin and _active_admin_count(db) <= 1:
                raise ApiError(
                    409, "LAST_ADMIN", "至少保留一个启用状态的管理员账号"
                )
            if display_name is not None:
                name = display_name.strip()
                if not name:
                    raise ApiError(400, "VALIDATION_ERROR", "显示名称不能为空")
                row.display_name = name
            if role is not None:
                if role not in MANAGEABLE_ROLES:
                    raise ApiError(400, "VALIDATION_ERROR", "角色取值不合法")
                row.role = role
            if status is not None:
                if status not in {AccountStatus.ACTIVE, AccountStatus.DISABLED}:
                    raise ApiError(400, "VALIDATION_ERROR", "状态取值不合法")
                row.status = status
                if status == AccountStatus.DISABLED:
                    _revoke_sessions(db, row.id)
            row.updated_at = utcnow()
            db.commit()
            db.refresh(row)
            return _user_dict(row)

    def reset_password(self, user_id: uuid.UUID, password: str) -> dict:
        if len(password) < 8:
            raise ApiError(400, "VALIDATION_ERROR", "密码至少 8 位")
        with SessionLocal() as db:
            row = _get_user(db, user_id)
            row.password_hash = hash_password(password)
            row.failed_login_count = 0
            row.locked_until = None
            if row.status == AccountStatus.LOCKED:
                row.status = AccountStatus.ACTIVE
            row.updated_at = utcnow()
            _revoke_sessions(db, row.id)
            db.commit()
            return {"id": str(row.id), "updated": True}


def _get_user(db, user_id: uuid.UUID) -> User:
    row = db.get(User, user_id)
    if not row:
        raise ApiError(404, "NOT_FOUND", "账号不存在")
    return row


def _active_admin_count(db) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN, User.status == AccountStatus.ACTIVE)
        )
        or 0
    )


def _revoke_sessions(db, user_id: uuid.UUID) -> None:
    db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


def _user_dict(row: User) -> dict:
    return {
        "id": str(row.id),
        "login_name": row.login_name,
        "display_name": row.display_name,
        "role": row.role.value,
        "status": row.status.value,
        "last_login_at": row.last_login_at,
        "created_at": row.created_at,
    }
