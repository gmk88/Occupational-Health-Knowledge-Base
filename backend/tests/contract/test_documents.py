from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from occupational_health.api.main import create_app
from occupational_health.core.security import MemoryAuthStore
from occupational_health.services.audit.service import MemoryAuditService
from tests.conftest import StubHealthChecker


class FakeDocumentService:
    def upload(self, *args, **kwargs):
        return {
            "document_id": str(uuid.uuid4()),
            "version_id": str(uuid.uuid4()),
            "job_id": str(uuid.uuid4()),
            "duplicate": False,
            "status": "queued",
        }

    def list_documents(self, *args, **kwargs):
        return [], {"page": 1, "page_size": 20, "total": 0, "total_pages": 0}

    def get_document(self, document_id):
        return {
            "id": str(document_id),
            "title": "示例",
            "status": "processing",
            "category": None,
            "tags": [],
            "uploader_id": str(uuid.uuid4()),
            "current_version": None,
        }

    def update_metadata(self, document_id, title, category_id, tags, source, notes):
        return self.get_document(document_id)

    def get_page(self, document_id, page_number, raw, chunk_id=None):
        self.last_chunk_id = chunk_id
        return {
            "document_id": str(document_id),
            "version_number": 1,
            "page_number": page_number,
            "source_type": "text_layer",
            "view": "raw" if raw else "masked",
            "text": "脱敏正文" if not raw else "原文",
            "spans": [{"start_offset": 0, "end_offset": 4, "type": "chunk"}]
            if chunk_id
            else [],
            "quality_warnings": [],
        }

    def get_quality_report(self, document_id):
        return {
            "document_id": str(document_id),
            "page_count": 1,
            "effective_char_count": 10,
            "chunk_count": 1,
            "ocr_page_ratio": 0,
            "average_ocr_confidence": None,
            "noise_char_count": 0,
            "low_quality_pages": [],
            "failed_pages": [],
        }

    def list_jobs(self, *args, **kwargs):
        return [], {"page": 1, "page_size": 20, "total": 0, "total_pages": 0}

    def get_job(self, job_id):
        return {
            "id": str(job_id),
            "document_id": str(uuid.uuid4()),
            "version_id": None,
            "job_type": "upload",
            "status": "queued",
            "current_stage": "validation",
            "processed_pages": 0,
            "total_pages": 1,
            "attempt_count": 0,
        }

    def list_categories(self):
        return []

    def create_category(self, code, name):
        return {"id": str(uuid.uuid4()), "code": code, "name": name, "active": True}

    def list_tags(self, *args, **kwargs):
        return [], {"page": 1, "page_size": 20, "total": 0, "total_pages": 0}

    def create_tag(self, name):
        return {"id": str(uuid.uuid4()), "name": name, "duplicate": False}

    def update_lifecycle(self, document_id, **kwargs):
        result = self.get_document(document_id)
        result.update(kwargs)
        return result

    def list_relations(self, document_id):
        return []

    def link_relation(self, source_id, target_id, relation_type, volume_no=None, note=None):
        return {
            "id": str(uuid.uuid4()),
            "source_document_id": str(source_id),
            "target_document_id": str(target_id),
            "relation_type": relation_type,
            "volume_no": volume_no,
            "note": note,
        }


def make_client(store: MemoryAuthStore) -> TestClient:
    from occupational_health.core.config import Settings

    app = create_app(
        settings=Settings(
            _env_file=None,
            session_secret="test-only-secret-with-at-least-32-characters",
            cookie_secure=True,
        ),
        auth_store=store,
        audit_service=MemoryAuditService(),
        health_checker=StubHealthChecker(),
        document_service=FakeDocumentService(),
    )
    return TestClient(app, base_url="https://testserver")


def login(
    client: TestClient, username: str, password: str = "correct-horse-admin"
) -> None:
    client.post(
        "/api/v1/auth/login", json={"login_name": username, "password": password}
    )


@pytest.fixture
def client(auth_store: MemoryAuthStore) -> TestClient:
    return make_client(auth_store)


def test_upload_requires_admin_and_returns_202(client) -> None:
    login(client, "viewer", "correct-horse-viewer")
    response = client.post(
        "/api/v1/documents", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}
    )
    assert response.status_code == 403
    client.post("/api/v1/auth/logout")
    login(client, "admin")
    response = client.post(
        "/api/v1/documents", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}
    )
    assert response.status_code == 200
    assert response.json()["data"]["job_id"]


def test_document_and_quality_and_page_endpoints(client) -> None:
    login(client, "admin")
    document_id = str(uuid.uuid4())
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 200
    assert client.get(f"/api/v1/documents/{document_id}/pages/1").status_code == 200
    assert (
        client.get(f"/api/v1/documents/{document_id}/quality-report").status_code == 200
    )


def test_raw_page_is_admin_only(client) -> None:
    login(client, "viewer", "correct-horse-viewer")
    document_id = str(uuid.uuid4())
    assert (
        client.get(f"/api/v1/documents/{document_id}/pages/1?view=raw").status_code
        == 403
    )


def test_page_endpoint_passes_chunk_id_for_highlight(client) -> None:
    login(client, "viewer", "correct-horse-viewer")
    chunk_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())

    response = client.get(
        f"/api/v1/documents/{document_id}/pages/1?chunk_id={chunk_id}"
    )

    assert response.status_code == 200
    assert response.json()["data"]["spans"] == [
        {"start_offset": 0, "end_offset": 4, "type": "chunk"}
    ]
    assert str(client.app.state.document_service.last_chunk_id) == chunk_id
    assert (
        client.get(
            f"/api/v1/documents/{document_id}/pages/1?chunk_id=not-a-uuid"
        ).status_code
        == 400
    )


def test_taxonomy_and_jobs_envelopes(client) -> None:
    login(client, "admin")
    assert client.get("/api/v1/categories").status_code == 200
    assert (
        client.post(
            "/api/v1/categories", json={"code": "audit", "name": "审计"}
        ).status_code
        == 201
    )
    assert client.get("/api/v1/jobs").status_code == 200
    assert client.get(f"/api/v1/jobs/{uuid.uuid4()}").status_code == 200


def test_lifecycle_patch_accepts_status_and_dates(client) -> None:
    login(client, "admin")
    document_id = str(uuid.uuid4())
    response = client.patch(
        f"/api/v1/documents/{document_id}/lifecycle",
        json={
            "lifecycle_status": "abolished",
            "document_role": "main",
            "standard_no": "GBZ/T 196-2007",
            "edition_year": 2007,
            "effective_date": "2007-05-01",
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["lifecycle_status"] == "abolished"


def test_relation_endpoints_work(client) -> None:
    login(client, "admin")
    document_id = str(uuid.uuid4())
    target_id = str(uuid.uuid4())
    response = client.post(
        f"/api/v1/documents/{document_id}/relations",
        json={
            "target_document_id": target_id,
            "relation_type": "amends",
            "volume_no": "1",
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["relation_type"] == "amends"
    response = client.get(f"/api/v1/documents/{document_id}/relations")
    assert response.status_code == 200