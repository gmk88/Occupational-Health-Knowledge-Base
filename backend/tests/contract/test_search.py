from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from occupational_health.api.main import create_app
from occupational_health.core.config import Settings
from occupational_health.core.security import MemoryAuthStore
from occupational_health.services.audit.service import MemoryAuditService
from tests.conftest import StubHealthChecker


class FakeRetrievalService:
    def search(self, principal, query, mode, top_k, filters, include_raw):
        return {
            "items": [],
            "total": 0,
            "took_ms": 1,
            "mode": mode,
            "ranking": "RRF(k=60)",
            "degraded": False,
            "degraded_sources": [],
            "suggestions": [],
        }


@pytest.fixture
def client(auth_store: MemoryAuthStore) -> TestClient:
    app = create_app(
        settings=Settings(
            _env_file=None,
            session_secret="test-only-secret-with-at-least-32-characters",
            cookie_secure=True,
        ),
        auth_store=auth_store,
        audit_service=MemoryAuditService(),
        health_checker=StubHealthChecker(),
        document_service=object(),
        retrieval_service=FakeRetrievalService(),
    )
    return TestClient(app, base_url="https://testserver")


def test_search_returns_envelope(client) -> None:
    client.post(
        "/api/v1/auth/login",
        json={"login_name": "admin", "password": "correct-horse-admin"},
    )
    response = client.post(
        "/api/v1/search", json={"query": "苯系物接触限值", "mode": "hybrid"}
    )
    assert response.status_code == 200
    assert set(response.json()) == {"code", "message", "data", "request_id"}


def test_include_raw_is_admin_only(client) -> None:
    client.post(
        "/api/v1/auth/login",
        json={"login_name": "viewer", "password": "correct-horse-viewer"},
    )
    response = client.post("/api/v1/search", json={"query": "苯", "include_raw": True})
    assert response.status_code == 403
