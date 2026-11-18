from __future__ import annotations

import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models

from occupational_health.services.indexing.schema import COLLECTION, ensure_collection


class QdrantIndexer:
    def __init__(self, client: QdrantClient) -> None:
        self.client = client

    def upsert(self, points: list[dict]) -> None:
        ensure_collection(self.client)
        self.client.upsert(
            COLLECTION, points=[models.PointStruct(**point) for point in points]
        )

    def set_document_taxonomy(
        self,
        document_id: uuid.UUID,
        pipeline_revision: uuid.UUID,
        category_id: uuid.UUID,
        tag_ids: list[uuid.UUID],
    ) -> None:
        """Update taxonomy payload without re-embedding vectors."""
        self.client.set_payload(
            COLLECTION,
            {
                "category_id": str(category_id),
                "tag_ids": [str(tag_id) for tag_id in tag_ids],
            },
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=str(document_id)),
                    ),
                    models.FieldCondition(
                        key="pipeline_revision",
                        match=models.MatchValue(value=str(pipeline_revision)),
                    ),
                ]
            ),
        )

    def set_revision_visible(self, pipeline_revision: uuid.UUID, visible: bool) -> None:
        self.client.set_payload(
            COLLECTION,
            {"index_visible": visible},
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="pipeline_revision",
                        match=models.MatchValue(value=str(pipeline_revision)),
                    )
                ]
            ),
        )

    def hide_revision(self, pipeline_revision: uuid.UUID) -> None:
        self.client.set_payload(
            COLLECTION,
            {"index_visible": False},
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="pipeline_revision",
                        match=models.MatchValue(value=str(pipeline_revision)),
                    )
                ]
            ),
        )

    def hide_document(self, document_id: uuid.UUID) -> None:
        """Hide all points of a document when its revisions are unknown."""
        self.client.set_payload(
            COLLECTION,
            {"index_visible": False},
            models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=str(document_id)),
                    )
                ]
            ),
        )

    def delete_revision(self, pipeline_revision: uuid.UUID) -> None:
        self.client.delete(
            COLLECTION,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="pipeline_revision",
                            match=models.MatchValue(value=str(pipeline_revision)),
                        )
                    ]
                )
            ),
        )
