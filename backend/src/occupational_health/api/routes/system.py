from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from qdrant_client import QdrantClient
from redis import Redis
from sqlalchemy import text

from occupational_health.api.dependencies.auth import require_user
from occupational_health.core.errors import success
from occupational_health.core.security import PrincipalData
from occupational_health.db.session import engine

router = APIRouter(tags=["System"])


class InfrastructureHealthChecker:
    _CACHE_SECONDS = 5.0

    def __init__(self, settings) -> None:
        self.settings = settings
        self._redis_client = Redis.from_url(
            settings.redis_url, socket_timeout=1, socket_connect_timeout=1
        )
        self._qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key.get_secret_value(),
            timeout=2,
        )
        self._http_client = httpx.Client(timeout=2)
        self._executor = ThreadPoolExecutor(
            max_workers=5, thread_name_prefix="health"
        )
        self._cache: tuple[float, list[dict]] | None = None

    def check(self) -> list[dict]:
        """并发探测各依赖，并在 5 秒内复用结果，避免探针放大负载。"""
        now = time.monotonic()
        if self._cache is not None and self._cache[0] > now:
            return self._cache[1]
        checks = [
            ("postgresql", self._database),
            ("redis", self._redis),
            ("qdrant", self._qdrant),
            ("embedding", self._embedding),
            ("storage", self._storage),
        ]
        results = list(
            self._executor.map(lambda item: self._measure(*item), checks)
        )
        self._cache = (now + self._CACHE_SECONDS, results)
        return results

    def close(self) -> None:
        self._executor.shutdown(wait=False)
        self._redis_client.close()
        self._http_client.close()
        self._qdrant_client.close()

    def _measure(self, name: str, check) -> dict:
        started = time.perf_counter()
        try:
            check()
            status = "up"
        except Exception:
            status = "down"
        return {
            "name": name,
            "status": status,
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }

    def _database(self) -> None:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def _redis(self) -> None:
        self._redis_client.ping()

    def _qdrant(self) -> None:
        self._qdrant_client.get_collections()

    def _embedding(self) -> None:
        response = self._http_client.get(f"{self.settings.embedding_url}/health")
        response.raise_for_status()

    def _storage(self) -> None:
        root = Path(self.settings.storage_root)
        root.mkdir(parents=True, exist_ok=True)
        if not os.access(root, os.W_OK):
            raise PermissionError("storage is not writable")


@router.get("/health/live")
def health_live() -> dict:
    """纯存活探针，不访问任何外部依赖，供启动脚本与 watchdog 使用。"""
    return success({"status": "alive", "version": "1.0.0"})


@router.get("/health")
def health(request: Request) -> JSONResponse:
    dependencies = request.app.state.health_checker.check()
    core_down = any(
        item["name"] in {"postgresql", "qdrant", "storage"} and item["status"] == "down"
        for item in dependencies
    )
    any_down = any(item["status"] == "down" for item in dependencies)
    status = "not_ready" if core_down else "degraded" if any_down else "ready"
    payload = success(
        {"status": status, "version": "1.0.0", "dependencies": dependencies}
    )
    return JSONResponse(status_code=503 if core_down else 200, content=payload)


@router.get("/system/limits")
def limits(
    request: Request,
    _principal: Annotated[PrincipalData, Depends(require_user)],
) -> dict:
    return success(request.app.state.settings.public_limits())
