from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.http import models

from occupational_health.services.indexing.schema import COLLECTION


class KeywordRetriever:
    def __init__(self, qdrant: QdrantClient) -> None:
        self.qdrant = qdrant

    def retrieve(
        self,
        query: str,
        limit: int,
        filter: models.Filter | None,
        include_raw: bool = False,
    ) -> list[tuple[str, float]]:
        combined: dict[str, float] = {}
        fields = ["raw_text"]
        if include_raw and "masked_text" not in fields:
            fields.append("masked_text")
        for field in fields:
            result = self.qdrant.query_points(
                collection_name=COLLECTION,
                query=models.TextQuery(text=query),
                using=field,
                query_filter=filter,
                limit=limit,
                with_payload=False,
            )
            for point in result.points:
                chunk_id = str(point.id)
                combined[chunk_id] = max(
                    combined.get(chunk_id, 0.0), float(point.score)
                )
        return sorted(combined.items(), key=lambda item: -item[1])
