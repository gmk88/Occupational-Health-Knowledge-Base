from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.http import models

from occupational_health.services.embedding.client import EmbeddingClient
from occupational_health.services.indexing.schema import COLLECTION


class SemanticRetriever:
    def __init__(self, embedding: EmbeddingClient, qdrant: QdrantClient) -> None:
        self.embedding = embedding
        self.qdrant = qdrant

    def retrieve(
        self, query: str, limit: int, filter: models.Filter | None
    ) -> list[tuple[str, float]]:
        vector = self.embedding.embed([query], query=True)[0]
        result = self.qdrant.query_points(
            collection_name=COLLECTION,
            query=vector,
            using="masked_dense",
            query_filter=filter,
            limit=limit,
            with_payload=False,
        )
        return [(str(point.id), float(point.score)) for point in result.points]
