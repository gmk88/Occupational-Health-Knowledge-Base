from __future__ import annotations

import asyncio

from occupational_health.services.api_clients.rate_limit import (
    RateLimitResult,
    RateLimiter,
    _as_result,
)


def test_result_parsing() -> None:
    assert _as_result([1, 60000]) == RateLimitResult(True)
    rejected = _as_result([0, 42050])
    assert rejected.allowed is False
    assert rejected.retry_after == 43
    assert _as_result([0, 0]).retry_after == 1


def _limiter() -> RateLimiter:
    return RateLimiter("redis://127.0.0.1:6399/0")


def test_sync_allow_rejected_does_not_raise() -> None:
    limiter = _limiter()
    limiter._script = lambda keys, args: [0, 15000]  # type: ignore[assignment]
    result = limiter.allow("sess:test", 60)
    assert result.allowed is False
    assert result.retry_after == 15


def test_sync_allow_fails_open_and_trips_circuit() -> None:
    limiter = _limiter()
    calls = {"count": 0}

    def broken(keys, args):
        calls["count"] += 1
        raise ConnectionError("redis down")

    limiter._script = broken  # type: ignore[assignment]
    assert limiter.allow("sess:test", 60).allowed is True
    assert limiter.allow("sess:test", 60).allowed is True
    assert calls["count"] == 1  # 熔断期间不再访问 Redis


def test_async_allow_rejected() -> None:
    limiter = _limiter()

    async def fake(keys, args):
        return [0, 30000]

    limiter._async_script = fake  # type: ignore[assignment]
    result = asyncio.run(limiter.allow_async("ip:1.2.3.4", 10))
    assert result.allowed is False
    assert result.retry_after == 30
