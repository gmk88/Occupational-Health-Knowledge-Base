"""Per-API-client usage aggregates for the access management pages."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import Integer, cast, func, select

from occupational_health.db.models.api_client import APIClient
from occupational_health.db.models.retrieval import SearchAudit
from occupational_health.db.session import SessionLocal, utcnow
from occupational_health.domain.enums import ActorType


def _p95():
    return func.percentile_cont(0.95).within_group(SearchAudit.took_ms.asc())


def client_usage(client_id: uuid.UUID, days: int = 7) -> dict:
    cutoff = utcnow() - timedelta(days=days)
    with SessionLocal() as db:
        base = (
            SearchAudit.actor_id == client_id,
            SearchAudit.actor_type == ActorType.API_CLIENT,
            SearchAudit.created_at >= cutoff,
        )
        summary = db.execute(
            select(
                func.count().label("calls"),
                func.avg(SearchAudit.took_ms).label("avg_ms"),
                _p95().label("p95_ms"),
                func.sum(cast(SearchAudit.degraded, Integer)).label("degraded"),
                func.sum(cast(SearchAudit.result_count > 0, Integer)).label(
                    "hit_calls"
                ),
            ).where(*base)
        ).one()
        daily = db.execute(
            select(
                func.date_trunc("day", SearchAudit.created_at).label("day"),
                func.count().label("calls"),
                func.avg(SearchAudit.took_ms).label("avg_ms"),
            )
            .where(*base)
            .group_by("day")
            .order_by("day")
        ).all()
        modes = db.execute(
            select(SearchAudit.mode, func.count().label("calls"))
            .where(*base)
            .group_by(SearchAudit.mode)
        ).all()

    calls = int(summary.calls or 0)
    return {
        "client_id": str(client_id),
        "days": days,
        "calls": calls,
        "avg_ms": round(float(summary.avg_ms or 0), 1),
        "p95_ms": round(float(summary.p95_ms or 0), 1),
        "degraded": int(summary.degraded or 0),
        "success_rate": round((int(summary.hit_calls or 0) / calls) * 100, 1)
        if calls
        else 0.0,
        "daily": [
            {
                "date": row.day.date().isoformat() if row.day else None,
                "calls": int(row.calls or 0),
                "avg_ms": round(float(row.avg_ms or 0), 1),
            }
            for row in daily
        ],
        "modes": [
            {"mode": row.mode.value if hasattr(row.mode, "value") else str(row.mode),
             "calls": int(row.calls or 0)}
            for row in modes
        ],
    }


def usage_overview(days: int = 7) -> tuple[list[dict], list[dict]]:
    cutoff = utcnow() - timedelta(days=days)
    with SessionLocal() as db:
        clients = list(db.scalars(select(APIClient).order_by(APIClient.created_at)))
        rows = db.execute(
            select(
                SearchAudit.actor_id.label("actor_id"),
                func.count().label("calls"),
                func.avg(SearchAudit.took_ms).label("avg_ms"),
                func.max(SearchAudit.created_at).label("last_call_at"),
            )
            .where(
                SearchAudit.actor_type == ActorType.API_CLIENT,
                SearchAudit.created_at >= cutoff,
            )
            .group_by(SearchAudit.actor_id)
        ).all()
        daily_rows = db.execute(
            select(
                func.date_trunc("day", SearchAudit.created_at).label("day"),
                func.count().label("calls"),
                func.avg(SearchAudit.took_ms).label("avg_ms"),
            )
            .where(
                SearchAudit.actor_type == ActorType.API_CLIENT,
                SearchAudit.created_at >= cutoff,
            )
            .group_by("day")
            .order_by("day")
        ).all()
    stats = {row.actor_id: row for row in rows}
    overview: list[dict] = []
    for client in clients:
        row = stats.get(client.id)
        overview.append(
            {
                "client_id": str(client.id),
                "name": client.name,
                "status": client.status,
                "calls": int(row.calls or 0) if row else 0,
                "avg_ms": round(float(row.avg_ms or 0), 1) if row else 0.0,
                "last_call_at": row.last_call_at if row else None,
                "rate_limit_per_minute": client.rate_limit_per_minute,
            }
        )
    overview.sort(key=lambda item: item["calls"], reverse=True)
    daily = [
        {
            "date": row.day.date().isoformat() if row.day else None,
            "calls": int(row.calls or 0),
            "avg_ms": round(float(row.avg_ms or 0), 1),
        }
        for row in daily_rows
    ]
    return overview, daily
