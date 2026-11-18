from __future__ import annotations

from pydantic import BaseModel, Field


class CategoryInput(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,50}$")
    name: str = Field(min_length=1, max_length=100)


class TagInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
