from __future__ import annotations

from pydantic import BaseModel


class JobError(BaseModel):
    code: str | None = None
    message: str | None = None
    failed_pages: list[int] = []
