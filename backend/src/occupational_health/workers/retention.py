from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete

from occupational_health.db.models.operations import AuditLog
from occupational_health.db.models.retrieval import SearchAudit
from occupational_health.db.session import SessionLocal, utcnow


def purge_expired_logs(days: int) -> tuple[int, int]:
    cutoff = utcnow() - timedelta(days=days)
    with SessionLocal() as db:
        audits = db.execute(
            delete(AuditLog).where(AuditLog.created_at < cutoff)
        ).rowcount
        searches = db.execute(
            delete(SearchAudit).where(SearchAudit.created_at < cutoff)
        ).rowcount
        db.commit()
    return audits, searches
