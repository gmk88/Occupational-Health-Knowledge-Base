from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from occupational_health.api.main import create_app
from occupational_health.core.config import Settings
from occupational_health.core.security import MemoryAuthStore
from occupational_health.services.audit.service import MemoryAuditService
from tests.conftest import StubHealthChecker


class FakeManagementService:
    def cancel_job(self, job_id, actor):
        return {"id": str(job_id), "status": "cancelled"}

    def retry_job(self, job_id, actor):
        return {"id": str(job_id), "status": "queued"}

    def delete_document(self, document_id, actor):
        return {"document_id": str(document_id), "status": "deleted"}

    def reprocess(self, document_id, actor):
        return {"id": str(uuid.uuid4()), "status": "queued"}

    def list_versions(self, document_id):
        return []

    def rollback(self, document_id, version_number, actor):
        return {
            "document_id": str(document_id),
            "version_number": version_number,
            "status": "current",
        }

    def correct_masking(self, document_id, actor):
        return {
            "document_id": str(document_id),
            "masking_revision": 1,
            "updated_chunks": 0,
            "status": "published",
        }

    def merge_tags(self, source_tag_id, target_tag_id):
        return {"id": str(target_tag_id), "name": "合并目标"}


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
        management_service=FakeManagementService(),
    )
    return TestClient(app, base_url="https://testserver")


def login_admin(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/login",
        json={"login_name": "admin", "password": "correct-horse-admin"},
    )


def test_management_endpoints_are_admin_only(client) -> None:
    client.post(
        "/api/v1/auth/login",
        json={"login_name": "viewer", "password": "correct-horse-viewer"},
    )
    document_id = str(uuid.uuid4())
    assert client.delete(f"/api/v1/documents/{document_id}").status_code == 403
    assert client.post(f"/api/v1/documents/{document_id}/reprocess").status_code == 403
    assert client.post(f"/api/v1/jobs/{uuid.uuid4()}/cancel").status_code == 403


def test_management_envelopes(client) -> None:
    login_admin(client)
    document_id = str(uuid.uuid4())
    assert client.delete(f"/api/v1/documents/{document_id}").status_code == 200
    assert client.post(f"/api/v1/documents/{document_id}/reprocess").status_code == 200
    assert client.get(f"/api/v1/documents/{document_id}/versions").status_code == 200
    assert (
        client.post(f"/api/v1/documents/{document_id}/versions/1/rollback").status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/documents/{document_id}/masking-corrections").status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/tags/{uuid.uuid4()}/merge?target_tag_id={uuid.uuid4()}"
        ).status_code
        == 200
    )
