from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from occupational_health.api.dependencies.auth import require_admin, require_user
from occupational_health.core.errors import success
from occupational_health.core.security import PrincipalData

router = APIRouter(tags=["Chunk Review"])


class ChunkEdit(BaseModel):
    job_id: str
    text: str = Field(min_length=1, max_length=20_000)


class ChunkMerge(BaseModel):
    chunk_ids: list[str] = Field(min_length=2, max_length=50)


class ChunkUnmerge(BaseModel):
    job_id: str


@router.get("/jobs/{job_id}/chunks")
def list_chunks(
    request: Request,
    job_id: str,
    _principal: PrincipalData = Depends(require_user),
) -> dict:
    return success(
        request.app.state.chunk_review_service.list_chunks(uuid.UUID(job_id))
    )


@router.get("/chunks/{chunk_id}")
def get_chunk(
    request: Request,
    chunk_id: str,
    _principal: PrincipalData = Depends(require_user),
) -> dict:
    return success(
        request.app.state.chunk_review_service.get_chunk(uuid.UUID(chunk_id))
    )


@router.put("/chunks/{chunk_id}")
def update_chunk(
    request: Request,
    chunk_id: str,
    payload: ChunkEdit,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        request.app.state.chunk_review_service.update_chunk(
            uuid.UUID(payload.job_id), uuid.UUID(chunk_id), payload.text
        )
    )


@router.delete("/chunks/{chunk_id}")
def delete_chunk(
    request: Request,
    chunk_id: str,
    job_id: str,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        request.app.state.chunk_review_service.delete_chunk(
            uuid.UUID(job_id), uuid.UUID(chunk_id)
        )
    )


@router.post("/jobs/{job_id}/chunks/merge")
def merge_chunks(
    request: Request,
    job_id: str,
    payload: ChunkMerge,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        request.app.state.chunk_review_service.merge_chunks(
            uuid.UUID(job_id), [uuid.UUID(item) for item in payload.chunk_ids]
        )
    )


@router.post("/chunks/{chunk_id}/unmerge")
def unmerge_chunk(
    request: Request,
    chunk_id: str,
    payload: ChunkUnmerge,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(
        request.app.state.chunk_review_service.unmerge_chunk(
            uuid.UUID(payload.job_id), uuid.UUID(chunk_id)
        )
    )


@router.post("/jobs/{job_id}/confirm")
def confirm_chunks(
    request: Request,
    job_id: str,
    _principal: PrincipalData = Depends(require_admin),
) -> dict:
    return success(request.app.state.chunk_review_service.confirm(uuid.UUID(job_id)))
