from __future__ import annotations

import uuid

from sqlalchemy import select

from occupational_health.core.security import (
    SessionRecord,
    UserRecord,
    normalize_login,
    utcnow,
)
from occupational_health.db.models.identity import Session, User
from occupational_health.db.session import SessionLocal


class SqlAuthStore:
    def _to_user(self, row: User) -> UserRecord:
        return UserRecord(
            id=row.id,
            login_name=row.login_name,
            display_name=row.display_name,
            password_hash=row.password_hash,
            role=row.role,
            status=row.status,
            failed_login_count=row.failed_login_count,
            locked_until=row.locked_until,
            last_login_at=row.last_login_at,
        )

    def get_user_by_login(self, normalized_login: str) -> UserRecord | None:
        with SessionLocal() as db:
            row = db.scalar(
                select(User).where(User.normalized_login == normalized_login)
            )
            return self._to_user(row) if row else None

    def get_user(self, user_id: uuid.UUID) -> UserRecord | None:
        with SessionLocal() as db:
            row = db.get(User, user_id)
            return self._to_user(row) if row else None

    def save_user(self, user: UserRecord) -> None:
        with SessionLocal() as db:
            row = db.get(User, user.id)
            if not row:
                row = User(
                    id=user.id, normalized_login=normalize_login(user.login_name)
                )
                db.add(row)
            for target, value in {
                "login_name": user.login_name.strip(),
                "normalized_login": normalize_login(user.login_name),
                "display_name": user.display_name,
                "password_hash": user.password_hash,
                "role": user.role,
                "status": user.status,
                "failed_login_count": user.failed_login_count,
                "locked_until": user.locked_until,
                "last_login_at": user.last_login_at,
                "updated_at": utcnow(),
            }.items():
                setattr(row, target, value)
            db.commit()

    def create_session(self, session: SessionRecord) -> None:
        with SessionLocal() as db:
            db.add(Session(**session.__dict__))
            db.commit()

    def _to_session(self, row: Session) -> SessionRecord:
        return SessionRecord(
            id=row.id,
            user_id=row.user_id,
            token_hash=row.token_hash,
            expires_at=row.expires_at,
            idle_expires_at=row.idle_expires_at,
            revoked_at=row.revoked_at,
            last_seen_at=row.last_seen_at,
            user_agent=row.user_agent,
            ip_hash=row.ip_hash,
        )

    def get_session(self, token_hash: str) -> SessionRecord | None:
        with SessionLocal() as db:
            row = db.scalar(select(Session).where(Session.token_hash == token_hash))
            return self._to_session(row) if row else None

    def get_session_with_user(
        self, token_hash: str
    ) -> tuple[SessionRecord, UserRecord | None] | None:
        with SessionLocal() as db:
            row = db.execute(
                select(Session, User)
                .outerjoin(User, User.id == Session.user_id)
                .where(Session.token_hash == token_hash)
            ).first()
            if not row:
                return None
            session_row, user_row = row
            return (
                self._to_session(session_row),
                self._to_user(user_row) if user_row else None,
            )

    def save_session(self, session: SessionRecord) -> None:
        with SessionLocal() as db:
            row = db.get(Session, session.id)
            if row:
                row.idle_expires_at = session.idle_expires_at
                row.revoked_at = session.revoked_at
                row.last_seen_at = session.last_seen_at
                db.commit()

    def revoke_session(self, token_hash: str) -> None:
        with SessionLocal() as db:
            row = db.scalar(select(Session).where(Session.token_hash == token_hash))
            if row:
                row.revoked_at = utcnow()
                db.commit()
