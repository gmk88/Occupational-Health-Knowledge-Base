from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from occupational_health.core.config import get_settings
from occupational_health.services.embedding.model import Embedder

settings = get_settings()
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
embedder = Embedder(
    settings.qwen_model_id,
    settings.qwen_revision,
    settings.model_root,
    settings.qwen_query_instruction,
    batch_size=settings.embedding_batch_size,
    device_preference=settings.embedding_device,
    fp16=settings.embedding_fp16,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Preload the model at startup so the first request does not pay the load
    # cost (and is not killed by a short timeout during cold start).
    embedder.load()
    yield


app = FastAPI(title="Embedding service", lifespan=lifespan)


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=128)
    query: bool = False


@app.get("/health")
def health() -> dict:
    return {"status": "up", "dimensions": embedder.dimensions, **embedder.device_info}


@app.post("/embed")
def embed(payload: EmbedRequest) -> dict:
    vectors = embedder.encode(payload.texts, query=payload.query)
    return {"vectors": vectors, "dimensions": embedder.dimensions}
