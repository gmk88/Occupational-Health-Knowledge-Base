from datetime import datetime

from pydantic import BaseModel, Field

from occupational_health.domain.enums import UserRole


class LoginRequest(BaseModel):
    login_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class Principal(BaseModel):
    id: str
    name: str
    actor_type: str
    role: UserRole
    scopes: list[str] = []
    session_expires_at: datetime | None = None
