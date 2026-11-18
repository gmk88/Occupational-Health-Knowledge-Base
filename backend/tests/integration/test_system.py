from __future__ import annotations

from fastapi.testclient import TestClient

from occupational_health.api.main import create_app
from occupational_health.services.audit.service import MemoryAuditService
from tests.conftest import StubHealthChecker, login


def test_health_is_public_and_reports_dependencies(client) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "ready"
    assert len(body["data"]["dependencies"]) == 5
    assert "http" not in response.text
    assert "password" not in response.text.lower()


def test_health_returns_503_without_leaking_internal_addresses(
    auth_store, settings
) -> None:
    app = create_app(
        settings=settings,
        auth_store=auth_store,
        audit_service=MemoryAuditService(),
        health_checker=StubHealthChecker({"postgresql", "qdrant"}),
    )
    client = TestClient(app, base_url="https://testserver")
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["data"]["status"] == "not_ready"
    assert "127.0.0.1" not in response.text
    assert "postgresql+psycopg" not in response.text


def test_limits_require_authentication_and_expose_configured_values(client) -> None:
    assert client.get("/api/v1/system/limits").status_code == 401
    login(client)
    response = client.get("/api/v1/system/limits")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["max_file_size_bytes"] == 104857600
    assert data["max_pages_per_file"] == 500
    assert data["max_files_per_web_batch"] == 20
    assert data["max_query_characters"] == 512
    assert data["default_top_k"] == 5
    assert data["max_top_k"] == 5
