from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from occupational_health.api.middleware.client_ip import resolve_client_ip
from occupational_health.api.middleware.rate_limit import RateLimitMiddleware
from occupational_health.api.middleware.security import SecurityHeadersMiddleware
from occupational_health.api.routes import (
    access_admin,
    auth,
    chunk_review,
    dashboard,
    document_management,
    documents,
    job_management,
    jobs,
    masking,
    search,
    system,
    taxonomy,
    taxonomy_admin,
    versions,
)
from occupational_health.core.config import Settings, get_settings
from occupational_health.core.errors import register_exception_handlers
from occupational_health.core.logging import (
    configure_logging,
    new_request_id,
    request_id_context,
)
from occupational_health.core.security import AuthService
from occupational_health.db.repositories.auth import SqlAuthStore
from occupational_health.services.api_clients.rate_limit import RateLimiter
from occupational_health.services.api_clients.service import ApiClientService
from occupational_health.services.audit.service import AuditService
from occupational_health.services.documents.chunk_review import ChunkReviewService
from occupational_health.services.documents.management import ManagementService
from occupational_health.services.documents.service import DocumentService
from occupational_health.services.retrieval.service import RetrievalService

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    auth_store=None,
    audit_service=None,
    health_checker=None,
    document_service=None,
    retrieval_service=None,
    management_service=None,
    api_client_service=None,
    chunk_review_service=None,
    rate_limiter=None,
) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()
    app = FastAPI(
        title="职业健康知识库 API",
        version="1.0.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.audit_service = audit_service or AuditService()
    store = auth_store or SqlAuthStore()
    app.state.auth_service = AuthService(store, settings, app.state.audit_service)
    app.state.health_checker = health_checker or system.InfrastructureHealthChecker(
        settings
    )
    app.state.document_service = document_service or DocumentService(settings)
    app.state.retrieval_service = retrieval_service or _default_retrieval(
        settings, app.state.document_service
    )
    app.state.management_service = management_service or ManagementService()
    app.state.api_client_service = api_client_service or ApiClientService()
    app.state.chunk_review_service = chunk_review_service or ChunkReviewService()

    limiter = rate_limiter or RateLimiter(settings.redis_url)
    app.state.rate_limiter = limiter

    # 后添加的中间件在更外层：RequestID -> SecurityHeaders -> RateLimit。
    # 这样 429 也会带上安全响应头，且 request_id 始终可用。
    app.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
        default_limit=settings.rate_limit_per_minute,
        trusted_proxies=settings.trusted_proxy_set,
    )
    app.add_middleware(SecurityHeadersMiddleware)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        token = request_id_context.set(
            request.headers.get("x-request-id") or new_request_id()
        )
        started = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id_context.get()
            return response
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            if duration_ms >= settings.slow_request_ms:
                logger.warning(
                    "slow request",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code
                        if response is not None
                        else 500,
                        "duration_ms": round(duration_ms),
                        "client_ip": resolve_client_ip(
                            request, settings.trusted_proxy_set
                        ),
                        "request_id": request_id_context.get(),
                    },
                )
            request_id_context.reset(token)

    register_exception_handlers(app)
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(system.router, prefix="/api/v1")
    app.include_router(dashboard.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(jobs.router, prefix="/api/v1")
    app.include_router(chunk_review.router, prefix="/api/v1")
    app.include_router(taxonomy.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(document_management.router, prefix="/api/v1")
    app.include_router(job_management.router, prefix="/api/v1")
    app.include_router(versions.router, prefix="/api/v1")
    app.include_router(masking.router, prefix="/api/v1")
    app.include_router(taxonomy_admin.router, prefix="/api/v1")
    app.include_router(access_admin.router, prefix="/api/v1")

    # MCP 客户端把基地址配成 https://域名/mcp，末尾补斜杠避免 404。
    from contextlib import asynccontextmanager

    from starlette.responses import RedirectResponse

    from occupational_health.mcp.server import mcp_app

    mcp_application, mcp_sessions = mcp_app()

    @asynccontextmanager
    async def lifespan(_app):
        # 启动前校验前端产物，缺失时直接中止，避免整站静默 404。
        configured_dist = settings.frontend_dist
        if configured_dist is not None:
            index_path = Path(configured_dist).resolve() / "index.html"
            if not index_path.is_file():
                raise RuntimeError(
                    f"OH_FRONTEND_DIST 指向 {index_path.parent}，但缺少 index.html。"
                    " 请先在 frontend 目录执行 npm run build。"
                )
        # streamable HTTP 会话语义要求显式启动任务组。
        async with mcp_sessions.run():
            yield
        embedding = getattr(
            getattr(_app.state.retrieval_service, "semantic", None), "embedding", None
        )
        close = getattr(embedding, "close", None)
        if close is not None:
            close()
        health_checker = _app.state.health_checker
        close_health = getattr(health_checker, "close", None)
        if close_health is not None:
            close_health()

    app.router.lifespan_context = lifespan

    @app.get("/mcp", include_in_schema=False)
    def mcp_redirect() -> RedirectResponse:
        return RedirectResponse("/mcp/", status_code=307)

    app.mount("/mcp", mcp_application)

    # 生产环境由后端直接托管前端构建产物，公网只需要暴露一个端口。
    dist = Path(settings.frontend_dist) if settings.frontend_dist else None
    if dist is not None:
        dist = dist.resolve()
        index_file = dist / "index.html"
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str) -> FileResponse:
            if full_path.startswith(("api/", "mcp")):
                raise HTTPException(status_code=404, detail="Not Found")
            candidate = (dist / full_path).resolve() if full_path else dist
            if (
                full_path
                and candidate.is_file()
                and (candidate == dist or dist in candidate.parents)
            ):
                return FileResponse(candidate)
            return FileResponse(index_file)

    return app


def _default_retrieval(settings: Settings, document_service) -> RetrievalService:
    from qdrant_client import QdrantClient

    from occupational_health.services.embedding.client import EmbeddingClient
    from occupational_health.services.retrieval.audit import RetrievalAuditService
    from occupational_health.services.retrieval.keyword import KeywordRetriever
    from occupational_health.services.retrieval.semantic import SemanticRetriever

    qdrant = QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value()
    )
    embedding = EmbeddingClient(
        settings.embedding_url,
        settings.embedding_timeout_seconds,
        max_retries=settings.embedding_max_retries,
        retry_backoff=settings.embedding_retry_backoff_seconds,
        query_timeout=settings.embedding_query_timeout_seconds,
        query_max_retries=settings.embedding_query_max_retries,
    )
    return RetrievalService(
        settings,
        semantic=SemanticRetriever(embedding, qdrant),
        keyword=KeywordRetriever(qdrant),
        document_service=document_service,
        audit=RetrievalAuditService(),
    )


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "occupational_health.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1,::1",
    )
