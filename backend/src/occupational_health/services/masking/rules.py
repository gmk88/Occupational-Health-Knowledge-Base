from __future__ import annotations

import re
from dataclasses import dataclass

from occupational_health.domain.enums import SensitiveType

ID_NUMBER = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
NAME_PATTERNS = re.compile(r"(姓名|名字)[:：]\s*([\u4e00-\u9fa5]{2,4})")
HEALTH_RESULT = re.compile(
    r"(?:体检结论|体检结果|健康检查结论|职业健康检查结论)[:：]\s*([^\n；;。]{1,30})"
)


@dataclass(frozen=True)
class MaskSpan:
    start: int
    end: int
    sensitive_type: SensitiveType
    replacement: str


REPLACEMENTS = {
    SensitiveType.NAME: "[姓名]",
    SensitiveType.ID_NUMBER: "[身份证号]",
    SensitiveType.CONTACT: "[联系方式]",
    SensitiveType.HEALTH_RESULT: "[体检结论]",
}


def detect_spans(text: str) -> list[MaskSpan]:
    spans: list[MaskSpan] = []
    for match in ID_NUMBER.finditer(text):
        spans.append(
            MaskSpan(
                match.start(),
                match.end(),
                SensitiveType.ID_NUMBER,
                REPLACEMENTS[SensitiveType.ID_NUMBER],
            )
        )
    for match in PHONE.finditer(text):
        spans.append(
            MaskSpan(
                match.start(),
                match.end(),
                SensitiveType.CONTACT,
                REPLACEMENTS[SensitiveType.CONTACT],
            )
        )
    for match in NAME_PATTERNS.finditer(text):
        start = match.start(2)
        end = match.end(2)
        spans.append(
            MaskSpan(start, end, SensitiveType.NAME, REPLACEMENTS[SensitiveType.NAME])
        )
    for match in HEALTH_RESULT.finditer(text):
        start = match.start(1)
        end = match.end(1)
        spans.append(
            MaskSpan(
                start,
                end,
                SensitiveType.HEALTH_RESULT,
                REPLACEMENTS[SensitiveType.HEALTH_RESULT],
            )
        )
    return _dedupe_overlapping(spans)


def apply_spans(text: str, spans: list[MaskSpan]) -> str:
    result = text
    for span in sorted(spans, key=lambda item: item.end, reverse=True):
        result = result[: span.start] + span.replacement + result[span.end :]
    return result


def _dedupe_overlapping(spans: list[MaskSpan]) -> list[MaskSpan]:
    spans = sorted(spans, key=lambda item: (item.start, item.end))
    accepted: list[MaskSpan] = []
    for span in spans:
        if accepted and span.start < accepted[-1].end:
            continue
        accepted.append(span)
    return accepted
