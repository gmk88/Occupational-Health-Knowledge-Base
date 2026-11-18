from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    VIEWER = "viewer"
    SERVICE = "service"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    LOCKED = "locked"


class DocumentStatus(StrEnum):
    PROCESSING = "processing"
    SEARCHABLE = "searchable"
    NEEDS_REVIEW = "needs_review"
    DELETED = "deleted"


class VersionStatus(StrEnum):
    PROCESSING = "processing"
    CURRENT = "current"
    REPLACED = "replaced"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class LifecycleStatus(StrEnum):
    CURRENT = "current"
    REPLACED = "replaced"
    ABOLISHED = "abolished"
    SUPERSEDED = "superseded"
    PENDING = "pending"


class DocumentRole(StrEnum):
    MAIN = "main"
    SUPPLEMENT = "supplement"
    AMENDMENT = "amendment"
    CORRIGENDUM = "corrigendum"
    OTHER = "other"


class RelationKind(StrEnum):
    AMENDS = "amends"
    SUPPLEMENTS = "supplements"
    CORRECTS = "corrects"
    REPLACES = "replaces"
    PART_OF = "part_of"


class PageSource(StrEnum):
    TEXT_LAYER = "text_layer"
    OCR = "ocr"
    MIXED = "mixed"


class PageStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    LOW_QUALITY = "low_quality"
    FAILED = "failed"
    EMPTY = "empty"


class JobType(StrEnum):
    UPLOAD = "upload"
    RETRY = "retry"
    REPROCESS = "reprocess"
    ROLLBACK = "rollback"
    DELETE = "delete"
    MASKING = "masking"
    REBUILD = "rebuild"


class JobStatus(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    PENDING_CONFIRMATION = "pending_confirmation"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStage(StrEnum):
    VALIDATION = "validation"
    EXTRACTION = "extraction"
    MINERU = "mineru"
    OCR = "ocr"
    CLEANING = "cleaning"
    MASKING = "masking"
    CHUNKING = "chunking"
    REVIEW = "review"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    PUBLISHING = "publishing"
    CLEANUP = "cleanup"


class ActorType(StrEnum):
    USER = "user"
    API_CLIENT = "api_client"


class RetrievalMode(StrEnum):
    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


class ChunkMode(StrEnum):
    STRUCTURE = "structure"
    SENTENCE = "sentence"
    FIXED = "fixed"
    PARENT_CHILD = "parent_child"


class ChunkRole(StrEnum):
    LEAF = "leaf"
    PARENT = "parent"
    CHILD = "child"


class SensitiveType(StrEnum):
    NAME = "name"
    ID_NUMBER = "id_number"
    CONTACT = "contact"
    HEALTH_RESULT = "health_result"
    OTHER = "other"
