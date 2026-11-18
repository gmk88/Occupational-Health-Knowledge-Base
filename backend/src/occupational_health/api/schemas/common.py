from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ListMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class Envelope(BaseModel):
    code: str
    message: str
    data: Any = None
    request_id: str
