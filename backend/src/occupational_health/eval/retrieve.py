from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from occupational_health.eval.config import EvalConfig
from occupational_health.eval.dataset import EvalCase


@dataclass(slots=True)
class RetrievedContext:
    text: str
    metadata: dict[str, Any]


class RetrievalRunner:
    """Retrieve contexts through the public API, matching production behavior."""

    def __init__(self, config: EvalConfig):
        self.config = config
        self.client = httpx.Client(
            base_url=config.api_url,
            timeout=60,
            follow_redirects=True,
        )

    def __enter__(self) -> RetrievalRunner:
        response = self.client.post(
            "/auth/login",
            json={
                "login_name": self.config.username,
                "password": self.config.password,
            },
        )
        response.raise_for_status()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.client.close()

    def retrieve(self, case: EvalCase) -> list[RetrievedContext]:
        filters: dict[str, Any] = {}
        if case.query_type in {"history", "lifecycle"} or case.allow_historical:
            filters["include_replaced"] = True

        response = self.client.post(
            "/search",
            json={
                "query": case.query,
                "mode": self.config.mode,
                "top_k": self.config.top_k,
                "filters": filters,
            },
        )
        response.raise_for_status()
        envelope = response.json()
        items = (envelope.get("data") or {}).get("items") or []

        contexts: list[RetrievedContext] = []
        for item in items:
            source_location = item.get("source_location") or {}
            primary = source_location.get("primary") or {}
            contexts.append(
                RetrievedContext(
                    text=item.get("text") or "",
                    metadata={
                        "chunk_id": item.get("chunk_id"),
                        "matched_chunk_id": item.get("matched_chunk_id"),
                        "document": item.get("document_name"),
                        "document_id": item.get("document_id"),
                        "page_start": item.get("page_start"),
                        "page_end": item.get("page_end"),
                        "source_page": primary.get("page_number"),
                        "standard_no": item.get("standard_no"),
                        "lifecycle_status": item.get("lifecycle_status"),
                        "document_role": item.get("document_role"),
                        "scores": item.get("scores"),
                        "recall_sources": item.get("recall_sources"),
                    },
                )
            )
        return contexts
