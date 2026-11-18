from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models

BASE = "http://127.0.0.1:8000/api/v1"
PDF = Path("var/testdata/sample.pdf")


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=120) as client:
        login = client.post(
            "/auth/login", json={"login_name": "admin", "password": "admin123"}
        )
        print("login:", login.status_code)
        if login.status_code != 200:
            print(login.text)
            return 1
        with PDF.open("rb") as stream:
            upload = client.post(
                "/documents",
                files={"file": (PDF.name, stream, "application/pdf")},
                data={"title": "端到端验证：职业接触限值", "tags": "接触限值,苯"},
            )
        print("upload:", upload.status_code, upload.text[:500])
        if upload.status_code != 200:
            return 1
        payload = upload.json()["data"]
        job_id = payload["job_id"]
        document_id = payload["document_id"]
        status = "completed" if payload.get("duplicate") else "queued"
        for _ in range(0 if payload.get("duplicate") else 90):
            time.sleep(2)
            job = client.get(f"/jobs/{job_id}").json()["data"]
            status = job["status"]
            print(
                "job:",
                status,
                job["current_stage"],
                f"{job['processed_pages']}/{job['total_pages']}",
                (job.get("error") or {}).get("message", ""),
            )
            if status in ("completed", "partial_success", "failed", "cancelled"):
                break
        if status != "completed":
            return 1
        document = client.get(f"/documents/{document_id}").json()["data"]
        print("document:", document["status"], document["current_version"])
        quality = client.get(f"/documents/{document_id}/quality-report")
        print("quality:", quality.status_code)
        search = client.post(
            "/search",
            json={"query": "苯的职业接触限值", "mode": "semantic", "top_k": 5},
        )
        result = search.json()["data"]
        print(
            "search:",
            search.status_code,
            "total",
            result["total"],
            "degraded",
            result["degraded"],
            result["degraded_sources"],
        )
        if result["items"]:
            print(
                "first result:",
                result["items"][0]["document_name"].encode("ascii", "backslashreplace").decode(),
                "page",
                result["items"][0]["page_start"],
            )
        points = QdrantClient(
            url="http://127.0.0.1:6333",
            api_key="ohqd_5Mv2kL9sX7aQ4wE8",
        ).count(
            "oh_chunks_v1",
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=document_id),
                    )
                ]
            ),
        )
        print("qdrant points:", points.count)
        return 0 if search.status_code == 200 and points.count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
