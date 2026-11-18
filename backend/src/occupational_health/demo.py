from __future__ import annotations

import uuid

from occupational_health.api.main import create_app
from occupational_health.core.config import Settings
from occupational_health.core.security import MemoryAuthStore
from occupational_health.domain.enums import UserRole
from occupational_health.services.audit.service import MemoryAuditService

SAMPLE_DOCUMENTS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "title": "工作场所有害因素职业接触限值 第1部分：化学有害因素",
        "original_filename": "GBZ 2.1-2019.pdf",
        "status": "searchable",
        "category": {"id": "c1", "code": "regulation_standard", "name": "法规标准", "active": True},
        "tags": [{"id": "t1", "name": "接触限值"}, {"id": "t2", "name": "化学因素"}],
        "page_count": 120,
        "chunk_count": 96,
        "ocr_page_ratio": 0,
        "average_ocr_confidence": None,
        "processing_duration_ms": 8400,
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "title": "苯（CAS 71-43-2）化学品安全技术说明书",
        "original_filename": "benzene-sds.pdf",
        "status": "searchable",
        "category": {"id": "c2", "code": "chemical_sds", "name": "化学品安全数据", "active": True},
        "tags": [{"id": "t3", "name": "苯"}, {"id": "t4", "name": "SDS"}],
        "page_count": 16,
        "chunk_count": 22,
        "ocr_page_ratio": 0,
        "average_ocr_confidence": None,
        "processing_duration_ms": 1200,
    },
]


class DemoDocumentService:
    def upload(self, *args, **kwargs):
        return {
            "document_id": str(uuid.uuid4()),
            "version_id": str(uuid.uuid4()),
            "job_id": str(uuid.uuid4()),
            "duplicate": False,
            "status": "queued",
        }

    def list_documents(
        self, page=1, page_size=20, sort="-created_at", status=None, category_id=None
    ):
        items = [self.get_document(uuid.UUID(doc["id"])) for doc in SAMPLE_DOCUMENTS]
        return items, {"page": page, "page_size": page_size, "total": len(items), "total_pages": 1}

    def get_document(self, document_id):
        document_id = str(document_id)
        for doc in SAMPLE_DOCUMENTS:
            if doc["id"] == document_id:
                return {
                    "id": doc["id"],
                    "title": doc["title"],
                    "original_filename": doc["original_filename"],
                    "status": doc["status"],
                    "category": doc["category"],
                    "tags": doc["tags"],
                    "source": None,
                    "notes": "演示数据",
                    "uploader_id": "00000000-0000-0000-0000-000000000000",
                    "current_version": {
                        "id": "v1",
                        "version_number": 1,
                        "status": "current",
                        "content_sha256": "a" * 64,
                    },
                    "created_at": "2026-11-12T10:00:00Z",
                    "updated_at": "2026-11-12T10:00:00Z",
                }
        return {
            "id": document_id,
            "title": "示例文档",
            "status": "processing",
            "category": None,
            "tags": [],
            "uploader_id": "0",
            "current_version": None,
        }

    def update_metadata(self, document_id, title, category_id, tags, source, notes):
        return self.get_document(document_id)

    def get_page(self, document_id, page_number, raw):
        document_id = str(document_id)
        if document_id == SAMPLE_DOCUMENTS[0]["id"]:
            text = (
                "职业接触限值采用时间加权平均容许浓度（PC-TWA）和短时间接触容许浓度（PC-STEL）。\n"
                "喷漆岗位苯系物的 PC-TWA 为 6 mg/m³。"
            )
        else:
            text = "苯，CAS 71-43-2，闪点 -11℃，爆炸极限 1.2%～8.0%。\n属确认人类致癌物。"
        return {
            "document_id": document_id,
            "version_number": 1,
            "page_number": page_number,
            "source_type": "text_layer",
            "view": "raw" if raw else "masked",
            "text": text,
            "spans": [],
            "quality_warnings": [],
        }

    def get_quality_report(self, document_id):
        document_id = str(document_id)
        for doc in SAMPLE_DOCUMENTS:
            if doc["id"] == document_id:
                return {
                    "document_id": document_id,
                    "version_id": "v1",
                    "job_id": "j1",
                    "page_count": doc["page_count"],
                    "effective_char_count": doc["page_count"] * 300,
                    "chunk_count": doc["chunk_count"],
                    "ocr_page_ratio": doc["ocr_page_ratio"],
                    "average_ocr_confidence": doc["average_ocr_confidence"],
                    "noise_char_count": 0,
                    "low_quality_pages": [],
                    "failed_pages": [],
                    "processing_duration_ms": doc["processing_duration_ms"],
                    "created_at": "2026-11-12T10:00:00Z",
                }
        return {
            "page_count": 0,
            "effective_char_count": 0,
            "chunk_count": 0,
            "ocr_page_ratio": 0,
            "average_ocr_confidence": None,
            "noise_char_count": 0,
            "low_quality_pages": [],
            "failed_pages": [],
        }

    def list_jobs(self, page=1, page_size=20, status=None, document_id=None):
        job = self.get_job(uuid.UUID("33333333-3333-3333-3333-333333333333"))
        return [job], {"page": page, "page_size": page_size, "total": 1, "total_pages": 1}

    def get_job(self, job_id):
        return {
            "id": str(job_id),
            "document_id": SAMPLE_DOCUMENTS[0]["id"],
            "version_id": "v1",
            "job_type": "upload",
            "status": "completed",
            "current_stage": "cleanup",
            "processed_pages": 120,
            "total_pages": 120,
            "attempt_count": 0,
            "retry_of_job_id": None,
            "error": None,
            "created_at": "2026-11-12T10:00:00Z",
        }

    def list_categories(self):
        return [
            {"id": "c1", "code": "regulation_standard", "name": "法规标准", "active": True},
            {"id": "c2", "code": "chemical_sds", "name": "化学品安全数据", "active": True},
            {"id": "c3", "code": "health_surveillance", "name": "职业健康监护", "active": True},
            {"id": "c4", "code": "training_material", "name": "培训材料", "active": True},
            {"id": "c5", "code": "other", "name": "其他", "active": True},
        ]

    def create_category(self, code, name):
        return {"id": str(uuid.uuid4()), "code": code, "name": name, "active": True}

    def list_tags(self, q=None, page=1, page_size=20):
        tags = [
            {"id": "t1", "name": "接触限值"},
            {"id": "t2", "name": "化学因素"},
            {"id": "t3", "name": "苯"},
            {"id": "t4", "name": "SDS"},
        ]
        return tags, {"page": page, "page_size": page_size, "total": len(tags), "total_pages": 1}

    def create_tag(self, name):
        return {"id": str(uuid.uuid4()), "name": name, "duplicate": False}


class DemoManagementService:
    def cancel_job(self, job_id, actor):
        return {"id": str(job_id), "status": "cancelled"}

    def retry_job(self, job_id, actor):
        return {"id": str(job_id), "status": "queued"}

    def delete_document(self, document_id, actor):
        return {"document_id": str(document_id), "status": "deleted"}

    def reprocess(self, document_id, actor):
        return {"id": str(uuid.uuid4()), "status": "queued"}

    def list_versions(self, document_id):
        return [{"id": "v1", "version_number": 1, "status": "current", "content_sha256": "a" * 64}]

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


class DemoRetrievalService:
    def search(self, principal, query, mode, top_k, filters, include_raw):
        return {
            "items": [
                {
                    "chunk_id": "c-1",
                    "text": "喷漆岗位苯系物的 PC-TWA 为 6 mg/m³，短时间接触容许浓度按标准执行。",
                    "document_id": SAMPLE_DOCUMENTS[0]["id"],
                    "document_name": SAMPLE_DOCUMENTS[0]["title"],
                    "version_number": 1,
                    "page_start": 3,
                    "page_end": 3,
                    "category": SAMPLE_DOCUMENTS[0]["category"],
                    "tags": SAMPLE_DOCUMENTS[0]["tags"],
                    "scores": {"semantic": 0.83, "keyword": 12.4, "rrf": 0.0328},
                    "recall_sources": ["semantic", "keyword"],
                    "highlights": [{"start_offset": 8, "end_offset": 11}],
                },
                {
                    "chunk_id": "c-2",
                    "text": "苯（CAS 71-43-2）为确认人类致癌物，操作时应佩戴防护用品。",
                    "document_id": SAMPLE_DOCUMENTS[1]["id"],
                    "document_name": SAMPLE_DOCUMENTS[1]["title"],
                    "version_number": 1,
                    "page_start": 1,
                    "page_end": 1,
                    "category": SAMPLE_DOCUMENTS[1]["category"],
                    "tags": SAMPLE_DOCUMENTS[1]["tags"],
                    "scores": {"rrf": 0.0164},
                    "recall_sources": ["keyword"],
                    "highlights": [],
                },
            ],
            "total": 2,
            "took_ms": 12,
            "mode": mode,
            "ranking": "RRF(k=60), equal weights",
            "degraded": False,
            "degraded_sources": [],
            "suggestions": [],
        }


class DemoHealthChecker:
    def check(self):
        return [
            {"name": name, "status": "up", "latency_ms": 1}
            for name in ("postgresql", "redis", "qdrant", "embedding", "storage")
        ]


def build_demo_app():
    settings = Settings(
        _env_file=None,
        session_secret="demo-only-secret-with-at-least-32-characters",
        cookie_secure=False,
    )
    store = MemoryAuthStore()
    store.add_user("admin", "admin123", UserRole.ADMIN)
    return create_app(
        settings=settings,
        auth_store=store,
        audit_service=MemoryAuditService(),
        health_checker=DemoHealthChecker(),
        document_service=DemoDocumentService(),
        retrieval_service=DemoRetrievalService(),
        management_service=DemoManagementService(),
    )


def run_demo() -> None:
    import uvicorn

    uvicorn.run(build_demo_app(), host="127.0.0.1", port=8000, log_level="warning")
