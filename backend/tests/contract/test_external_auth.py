from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from occupational_health.api.main import create_app
from occupational_health.core.config import Settings
from occupational_health.core.errors import ApiError
from occupational_health.core.security import MemoryAuthStore, PrincipalData
from occupational_health.domain.enums import ActorType, UserRole
from occupational_health.services.audit.service import MemoryAuditService
from tests.conftest import StubHealthChecker


class FakeApiClientService:
    def limit_for(self, _client_id) -> int:
        return 60

    def authenticate(self, raw_key: str) -> PrincipalData:
        if raw_key == "good-key":
            return PrincipalData(
                uuid.uuid4(),
                "接入方",
                ActorType.API_CLIENT,
                UserRole.SERVICE,
                scopes=["search:read"],
            )
        raise ApiError(401, "API_KEY_EXPIRED", "密钥无效或过期")


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
        retrieval_service=object(),
        management_service=object(),
        api_client_service=FakeApiClientService(),
    )
    return TestClient(app, base_url="https://testserver")


def test_bearer_key_authenticates_and_rejects_invalid(client) -> None:
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer bad-key"}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer good-key"}
        ).status_code
        == 200
    )


def test_service_scope_is_enforced(client) -> None:
    # search:read 不含 documents:write，管理接口应被拒绝。
    response = client.delete(
        "/api/v1/documents/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": "Bearer good-key"},
    )
    assert response.status_code == 403
