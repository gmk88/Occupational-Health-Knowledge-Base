from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.http import models

COLLECTION = "oh_chunks_v1"


def ensure_collection(client: QdrantClient) -> None:
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config={
                "masked_dense": models.VectorParams(
                    size=1024, distance=models.Distance.COSINE
                )
            },
        )
    existing = set(client.get_collection(COLLECTION).payload_schema)
    indexed = {
        "masked_text": models.TextIndexParams(
            type=models.TextIndexType.TEXT,
            tokenizer=models.TokenizerType.MULTILINGUAL,
            lowercase=True,
            phrase_matching=True,
            scoring=models.TextScoringParams(type=models.TextScoringType.BM25),
        ),
        "raw_text": models.TextIndexParams(
            type=models.TextIndexType.TEXT,
            tokenizer=models.TokenizerType.MULTILINGUAL,
            lowercase=True,
            phrase_matching=True,
            scoring=models.TextScoringParams(type=models.TextScoringType.BM25),
        ),
        "chunk_id": models.PayloadSchemaType.UUID,
        "document_id": models.PayloadSchemaType.UUID,
        "version_id": models.PayloadSchemaType.UUID,
        "pipeline_revision": models.PayloadSchemaType.UUID,
        "category_id": models.PayloadSchemaType.KEYWORD,
        "tag_ids": models.PayloadSchemaType.KEYWORD,
        "lifecycle_status": models.PayloadSchemaType.KEYWORD,
        "document_role": models.PayloadSchemaType.KEYWORD,
        "standard_no": models.PayloadSchemaType.KEYWORD,
        "uploaded_at": models.PayloadSchemaType.DATETIME,
        "page_start": models.PayloadSchemaType.INTEGER,
        "page_end": models.PayloadSchemaType.INTEGER,
        "index_visible": models.PayloadSchemaType.BOOL,
        "block_type": models.PayloadSchemaType.KEYWORD,
        "chunk_role": models.PayloadSchemaType.KEYWORD,
        "parent_chunk_id": models.PayloadSchemaType.KEYWORD,
        "table_id": models.PayloadSchemaType.KEYWORD,
        "row_index": models.PayloadSchemaType.INTEGER,
    }
    for field, schema in indexed.items():
        if field not in existing:
            client.create_payload_index(COLLECTION, field, field_schema=schema)
