from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from occupational_health.api.main import create_app
from occupational_health.core.config import Settings
from occupational_health.core.security import MemoryAuthStore
from occupational_health.domain.enums import UserRole
from occupational_health.services.audit.service import MemoryAuditService
from occupational_health.services.api_clients.rate_limit import RateLimitResult


class StubRateLimiter:
    """Tests should not depend on a running Redis."""

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> RateLimitResult:
        return RateLimitResult(True)

    async def allow_async(
        self, key: str, limit: int, window_seconds: int = 60
    ) -> RateLimitResult:
        return RateLimitResult(True)


class StubHealthChecker:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()

    def check(self) -> list[dict]:
        return [
            {
                "name": name,
                "status": "down" if name in self.failures else "up",
                "latency_ms": 1,
            }
            for name in ("postgresql", "redis", "qdrant", "embedding", "storage")
        ]


@pytest.fixture
def auth_store() -> MemoryAuthStore:
    store = MemoryAuthStore()
    store.add_user("admin", "correct-horse-admin", UserRole.ADMIN)
    store.add_user("viewer", "correct-horse-viewer", UserRole.VIEWER)
    return store


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        session_secret="test-only-secret-with-at-least-32-characters",
        cookie_secure=True,
    )


@pytest.fixture
def client(auth_store: MemoryAuthStore, settings: Settings) -> TestClient:
    app = create_app(
        settings=settings,
        auth_store=auth_store,
        audit_service=MemoryAuditService(),
        health_checker=StubHealthChecker(),
        rate_limiter=StubRateLimiter(),
    )
    return TestClient(app, base_url="https://testserver")


def login(
    client: TestClient, username: str = "admin", password: str = "correct-horse-admin"
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"login_name": username, "password": password},
    )
    assert response.status_code == 200, response.text
