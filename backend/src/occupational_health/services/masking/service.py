from __future__ import annotations

import hashlib

from occupational_health.services.masking.rules import MaskSpan


def base_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def mask_text(raw: str) -> tuple[str, list[dict], list[MaskSpan]]:
    """Return the source text unchanged.

    The knowledge base publishes standards and regulations, so the stored and
    returned text must remain byte-for-byte identical to the parsed source.
    The masking helpers are kept for historical records and audits, but new
    pipeline runs no longer redact any span.
    """
    return raw, [], []
