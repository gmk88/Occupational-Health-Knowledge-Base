from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from uuid import uuid4

request_id_context: ContextVar[str] = ContextVar("request_id", default="")
SENSITIVE_KEYS = {
    "password",
    "cookie",
    "authorization",
    "api_key",
    "token",
    "raw_text",
    "query",
}
SENSITIVE_PATTERN = re.compile(r"(?i)(bearer\s+)[^\s,;]+")


class SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        safe = {key: "[redacted]" for key in SENSITIVE_KEYS if key in record.__dict__}
        for key, value in record.__dict__.items():
            if key not in SENSITIVE_KEYS and isinstance(value, str):
                safe[key] = SENSITIVE_PATTERN.sub(r"\1[redacted]", value)
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": SENSITIVE_PATTERN.sub(r"\1[redacted]", record.getMessage()),
            "request_id": getattr(
                record, "request_id", request_id_context.get() or None
            ),
        }
        for key in (
            "actor_id",
            "document_id",
            "job_id",
            "stage",
            "result",
            "method",
            "path",
            "status",
            "duration_ms",
            "client_ip",
        ):
            if key in safe:
                payload[key] = safe[key]
        if record.exc_info:
            payload["exception_type"] = (
                record.exc_info[0].__name__ if record.exc_info[0] else "Unknown"
            )
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # 第三方库的 INFO 日志会淹没真正的慢请求与错误。
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def new_request_id() -> str:
    value = str(uuid4())
    request_id_context.set(value)
    return value
