from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

_LOGGER = logging.getLogger(__name__)

# 达到上限时只读取剩余 TTL，不再 INCR；被拒绝的请求不会继续推高计数。
_ALLOW_SCRIPT = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
if count >= limit then
  local ttl = redis.call('PTTL', KEYS[1])
  if ttl < 0 then ttl = window_ms end
  return {0, ttl}
end
local value = redis.call('INCR', KEYS[1])
if value == 1 then
  redis.call('PEXPIRE', KEYS[1], window_ms)
end
return {1, redis.call('PTTL', KEYS[1])}
"""


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int = 0


_ALLOWED = RateLimitResult(True)


def _as_result(raw) -> RateLimitResult:
    if bool(int(raw[0])):
        return _ALLOWED
    ttl_ms = max(0, int(raw[1]))
    return RateLimitResult(False, max(1, math.ceil(ttl_ms / 1000)))


class RateLimiter:
    """Redis 固定窗口计数器，窗口从首次请求开始计时，故障时快速放行。"""

    def __init__(self, redis_url: str) -> None:
        common = {
            "decode_responses": True,
            "socket_connect_timeout": 0.25,
            "socket_timeout": 0.5,
            "health_check_interval": 30,
        }
        self.redis = Redis.from_url(redis_url, **common)
        self.async_redis = AsyncRedis.from_url(redis_url, **common)
        self._script = self.redis.register_script(_ALLOW_SCRIPT)
        self._async_script = self.async_redis.register_script(_ALLOW_SCRIPT)
        self._circuit_until = 0.0

    def _circuit_open(self) -> bool:
        return time.monotonic() < self._circuit_until

    def _trip(self, mode: str) -> None:
        now = time.monotonic()
        if now >= self._circuit_until:
            _LOGGER.warning(
                "rate limiter unavailable (%s), failing open for 5 seconds", mode
            )
        self._circuit_until = now + 5.0

    def _reset(self) -> None:
        self._circuit_until = 0.0

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> RateLimitResult:
        if self._circuit_open():
            return _ALLOWED
        try:
            raw = self._script(
                keys=[f"rl2:{key}"],
                args=[limit, window_seconds * 1000],
            )
        except Exception:
            self._trip("sync")
            return _ALLOWED
        self._reset()
        return _as_result(raw)

    async def allow_async(
        self, key: str, limit: int, window_seconds: int = 60
    ) -> RateLimitResult:
        if self._circuit_open():
            return _ALLOWED
        try:
            raw = await self._async_script(
                keys=[f"rl2:{key}"],
                args=[limit, window_seconds * 1000],
            )
        except Exception:
            self._trip("async")
            return _ALLOWED
        self._reset()
        return _as_result(raw)
