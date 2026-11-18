from __future__ import annotations

import argparse

from sqlalchemy import select

from occupational_health.core.security import hash_password, normalize_login
from occupational_health.db.models.identity import User
from occupational_health.db.session import SessionLocal
from occupational_health.domain.enums import AccountStatus, UserRole


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the initial administrator account.")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--display-name", default="管理员")
    args = parser.parse_args()
    normalized = normalize_login(args.username)
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.normalized_login == normalized))
        if existing:
            print(f"user already exists: {args.username}")
            return 0
        db.add(
            User(
                login_name=args.username.strip(),
                normalized_login=normalized,
                display_name=args.display_name,
                password_hash=hash_password(args.password),
                role=UserRole.ADMIN,
                status=AccountStatus.ACTIVE,
            )
        )
        db.commit()
    print(f"created administrator: {args.username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
