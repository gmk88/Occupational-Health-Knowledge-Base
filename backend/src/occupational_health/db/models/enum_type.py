from __future__ import annotations

from enum import Enum
from typing import Type

from sqlalchemy import Enum as SAEnum


def value_enum(enum_cls: Type[Enum], length: int = 32) -> SAEnum:
    """Store StrEnum values, not member names.

    Existing database rows use lowercase values such as ``admin``,
    ``api_client`` and ``searchable``. SQLAlchemy's default stores member
    names such as ``ADMIN``, which makes old rows unreadable.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
