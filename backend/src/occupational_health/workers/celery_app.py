from __future__ import annotations

from celery import Celery

import occupational_health.db.models  # noqa: F401
from occupational_health.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "occupational_health",
    broker=settings.redis_url,
    include=["occupational_health.workers.tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
    task_default_retry_delay=3,
    task_max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    task_default_queue="celery",
    # 向量化不能排在批量解析后面：确认后的任务走独立队列，
    # 由专门的 worker 消费，和上传解析并行。
    task_routes={"finalize_document": {"queue": "embedding"}},
)
