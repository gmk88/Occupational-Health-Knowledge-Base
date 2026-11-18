"""SQLAlchemy ORM models.

Import every module here so ``Base.metadata`` always contains all tables.
Several models declare foreign keys to tables defined in other modules; if
those modules are not imported, SQLAlchemy cannot resolve the dependency when
a worker first flushes a session.
"""

from occupational_health.db.models import (  # noqa: F401
    api_client,
    content,
    documents,
    identity,
    jobs,
    operations,
    retrieval,
    taxonomy,
)

__all__ = [
    "api_client",
    "content",
    "documents",
    "identity",
    "jobs",
    "operations",
    "retrieval",
    "taxonomy",
]
