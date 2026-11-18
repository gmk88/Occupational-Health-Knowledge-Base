from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OH_", env_file=".env", extra="ignore")

    env: str = "development"
    database_url: str = (
        "postgresql+psycopg://oh_app:replace-me@127.0.0.1:5432/occupational_health"
    )
    redis_url: str = "redis://:replace-me@127.0.0.1:6379/0"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: SecretStr = SecretStr("replace-me")
    storage_root: Path = Path("var/data")
    model_root: Path = Path("var/models")
    # 生产环境把前端构建产物交给后端托管；留空则只提供 API。
    frontend_dist: Path | None = None
    session_secret: SecretStr = SecretStr("development-only-change-before-production")
    session_ttl_minutes: int = Field(default=480, ge=5)
    session_idle_minutes: int = Field(default=60, ge=5)
    cookie_secure: bool = True
    max_file_size_bytes: int = Field(default=104_857_600, ge=1)
    max_pages_per_file: int = Field(default=500, ge=1)
    max_files_per_web_batch: int = Field(default=20, ge=1)
    max_query_characters: int = Field(default=512, ge=1)
    default_top_k: int = Field(default=5, ge=1)
    max_top_k: int = Field(default=5, ge=1)
    chunk_target_tokens: int = Field(default=512, ge=64)
    chunk_max_tokens: int = Field(default=768, ge=128)
    chunk_overlap_tokens: int = Field(default=64, ge=0)
    # 父子块：父块保持语义完整，子块负责检索命中。
    parent_chunk_target_tokens: int = Field(default=768, ge=128)
    parent_chunk_max_tokens: int = Field(default=1200, ge=256)
    child_chunk_target_tokens: int = Field(default=220, ge=64)
    child_chunk_max_tokens: int = Field(default=320, ge=128)
    child_chunk_overlap_tokens: int = Field(default=40, ge=0)
    # 页面文本层达到该字符数即视为可用；仅完全没有文本层时才回退 OCR。
    text_layer_min_chars: int = Field(default=1, ge=0)
    ocr_low_confidence: float = Field(default=0.75, ge=0, le=1)
    document_min_chars: int = Field(default=50, ge=0)
    rate_limit_per_minute: int = Field(default=60, ge=1)
    upload_limit_per_minute: int = Field(default=10, ge=1)
    # 处理任务只保留最近 N 条，0 表示不限制；只清理已到终态的记录。
    job_history_keep: int = Field(default=10, ge=0, le=1000)
    rrf_k: int = Field(default=60, ge=1)
    recall_candidates: int = Field(default=50, ge=1)
    log_retention_days: int = Field(default=180, ge=1)
    qwen_model_id: str = "Qwen/Qwen3-Embedding-0.6B"
    qwen_revision: str = "replace-with-full-40-char-commit-hash"
    qwen_query_instruction: str = (
        "Given an occupational-health query, retrieve relevant passages"
    )
    embedding_url: str = "http://127.0.0.1:8001"
    # auto = 有可用 CUDA 就用显卡，否则回退 CPU；cuda = 强制显卡（不可用时启动失败）；cpu = 强制 CPU。
    embedding_device: Literal["auto", "cuda", "cpu"] = "auto"
    embedding_fp16: bool = True
    embedding_timeout_seconds: float = Field(default=60, gt=0)
    embedding_warmup_timeout_seconds: float = Field(default=300, gt=0)
    embedding_max_retries: int = Field(default=3, ge=0)
    embedding_retry_backoff_seconds: float = Field(default=2.0, gt=0)
    embedding_batch_size: int = Field(default=64, ge=1, le=512)
    pipeline_commit_every: int = Field(default=20, ge=1)
    # 切分完成后暂停，等待人工预览/编辑并确认，才执行向量化与入库。
    require_chunk_confirmation: bool = True
    # 解析完成后按标题/正文规则自动归类并匹配已有标签（不新建标签）。
    auto_tagging_enabled: bool = True
    # 自动分类的最小置信度；低于该值保留原分类（通常为「其他」）。
    auto_tagging_min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    # 表格整表一个 chunk；超大表只在送入嵌入服务时按行截断，落库文本保持完整。
    table_embedding_max_tokens: int = Field(default=8000, ge=256, le=32000)
    # PDF 优先使用独立 venv 中的 MinerU 4.x 解析；失败时回退 PyMuPDF + OCR 链路。
    mineru_enabled: bool = True
    mineru_tier: str = "basic"  # flash / basic / standard / advanced
    mineru_kit_path: Path = Path(".mineru/Scripts/mineru-kit.exe")
    mineru_model_source: str = "modelscope"
    # 每多少页作为一个解析段；0 表示整份一次性解析（旧行为）。
    mineru_segment_pages: int = Field(default=10, ge=0, le=200)
    # 分段结果缓存，任务重试时跳过已解析的段，避免重复跑数分钟的模型推理。
    mineru_segment_cache_enabled: bool = True
    request_timeout_seconds: float = Field(default=30, gt=0)
    # 反向代理与部署：只有来自这些地址的连接才信任 CF-Connecting-IP / X-Forwarded-For。
    trusted_proxy_ips: str = "127.0.0.1,::1"
    slow_request_ms: int = Field(default=1000, ge=0)
    # 数据库连接池；pool_timeout 设小一些，突发时快速失败而不是排队 30 秒。
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_timeout_seconds: int = Field(default=5, ge=1)
    db_pool_recycle_seconds: int = Field(default=1800, ge=60)
    # 检索查询使用更短超时，避免单个慢查询拖住用户请求。
    embedding_query_timeout_seconds: float = Field(default=20, gt=0)
    embedding_query_max_retries: int = Field(default=1, ge=0)
    # 首页汇总缓存秒数；0 表示不缓存。
    dashboard_cache_seconds: int = Field(default=15, ge=0)

    @property
    def trusted_proxy_set(self) -> set[str]:
        return {
            item.strip() for item in self.trusted_proxy_ips.split(",") if item.strip()
        }

    @model_validator(mode="after")
    def validate_constraints(self) -> Settings:
        if not self.default_top_k <= self.max_top_k:
            raise ValueError("default_top_k must not exceed max_top_k")
        if (
            not self.chunk_overlap_tokens
            < self.chunk_target_tokens
            <= self.chunk_max_tokens
        ):
            raise ValueError(
                "chunk overlap must be smaller than target, and target must not exceed max"
            )
        if not (
            self.child_chunk_overlap_tokens
            < self.child_chunk_target_tokens
            <= self.child_chunk_max_tokens
            <= self.parent_chunk_target_tokens
            <= self.parent_chunk_max_tokens
        ):
            raise ValueError("invalid parent-child chunk token constraints")
        if (
            self.env == "production"
            and "development" in self.session_secret.get_secret_value()
        ):
            raise ValueError("production requires a private session secret")
        return self

    def public_limits(self) -> dict:
        return {
            "max_file_size_bytes": self.max_file_size_bytes,
            "max_pages_per_file": self.max_pages_per_file,
            "max_files_per_web_batch": self.max_files_per_web_batch,
            "max_query_characters": self.max_query_characters,
            "default_top_k": self.default_top_k,
            "max_top_k": self.max_top_k,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "upload_limit_per_minute": self.upload_limit_per_minute,
            "supported_media_types": [
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "text/plain",
                "text/markdown",
            ],
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
