from __future__ import annotations

import hashlib

from occupational_health.services.masking.rules import (
    MaskSpan,
    apply_spans,
    detect_spans,
)


def base_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def mask_text(raw: str) -> tuple[str, list[dict], list[MaskSpan]]:
    spans = detect_spans(raw)
    masked = apply_spans(raw, spans)
    annotations = [
        {
            "start_offset": span.start,
            "end_offset": span.end,
            "base_text_hash": base_text_hash(raw),
            "sensitive_type": span.sensitive_type.value,
            "replacement": span.replacement,
        }
        for span in spans
    ]
    return masked, annotations, spans
