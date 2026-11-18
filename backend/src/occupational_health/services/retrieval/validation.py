from __future__ import annotations

import re

from occupational_health.core.errors import ApiError
from occupational_health.domain.enums import RetrievalMode

ONLY_SYMBOLS = re.compile(r"^[\W_]+$")


def validate_query(
    query: str, max_characters: int, mode: str, top_k: int, max_top_k: int
) -> tuple[str, RetrievalMode, int]:
    if not query or not query.strip():
        raise ApiError(400, "QUERY_EMPTY", "请输入查询内容")
    stripped = query.strip()
    if len(stripped) > max_characters:
        raise ApiError(
            400,
            "QUERY_TOO_LONG",
            "查询超过长度限制",
            {"max_query_characters": max_characters},
        )
    if ONLY_SYMBOLS.match(stripped):
        raise ApiError(400, "VALIDATION_ERROR", "查询不能只包含特殊符号")
    try:
        resolved_mode = RetrievalMode(mode)
    except ValueError as exc:
        raise ApiError(400, "VALIDATION_ERROR", "检索模式无效") from exc
    if not 1 <= top_k <= max_top_k:
        raise ApiError(400, "VALIDATION_ERROR", "top_k 超出允许范围")
    return stripped, resolved_mode, top_k
