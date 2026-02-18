"""NornWeave Storage — Storage backend abstractions."""

__version__ = "0.0.2"

from nornweave_storage.config import DatabaseConfig
from nornweave_storage.exceptions import (
    ChunkNotFoundError,
    DocumentNotFoundError,
    DuplicateDocumentError,
    IntegrityError,
    StorageConnectionError,
    StorageError,
)
from nornweave_storage.pool import ConnectionPool
from nornweave_storage.repositories.chunk import ChunkRepository
from nornweave_storage.repositories.document import DocumentRepository

__all__ = [
    "ChunkNotFoundError",
    "ChunkRepository",
    "StorageConnectionError",
    "ConnectionPool",
    "DatabaseConfig",
    "DocumentNotFoundError",
    "DocumentRepository",
    "DuplicateDocumentError",
    "IntegrityError",
    "StorageError",
]
