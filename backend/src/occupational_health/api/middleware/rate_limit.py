from __future__ import annotations

import hashlib

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from occupational_health.api.middleware.client_ip import resolve_client_ip
from occupational_health.core.errors import ApiError, error_response
from occupational_health.services.api_clients.rate_limit import RateLimiter

_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/health",
        "/api/v1/health/live",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
    }
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        limiter: RateLimiter,
        default_limit: int,
        trusted_proxies: set[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.limiter = limiter
        self.default_limit = default_limit
        self.trusted_proxies = trusted_proxies or set()

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # 静态资源与 SPA 页面不计入 API 额度；/mcp 仍需鉴权与计数。
        if path in _EXEMPT_PATHS or path.startswith("/assets/"):
            return await call_next(request)
        if not path.startswith("/api/") and not path.startswith("/mcp"):
            return await call_next(request)
        # Bearer 请求交给按接入方限额（各自 rate_limit_per_minute），
        # 这里只兜底会话与匿名访客，避免两套阈值互相打架。
        if request.headers.get("authorization"):
            return await call_next(request)
        result = await self.limiter.allow_async(
            self._identity(request), self.default_limit
        )
        if result.allowed:
            return await call_next(request)
        return error_response(
            ApiError(
                429,
                "RATE_LIMITED",
                "请求过于频繁，请稍后重试",
                retry_after=result.retry_after,
            )
        )

    def _identity(self, request: Request) -> str:
        cookie = request.cookies.get("oh_session")
        if cookie:
            digest = hashlib.sha256(cookie.encode("utf-8")).hexdigest()[:24]
            return f"sess:{digest}"
        return f"ip:{resolve_client_ip(request, self.trusted_proxies)}"
