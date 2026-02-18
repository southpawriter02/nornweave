"""Repository layer for nornweave-storage."""

from nornweave_storage.repositories.chunk import ChunkRepository
from nornweave_storage.repositories.document import DocumentRepository

__all__ = ["ChunkRepository", "DocumentRepository"]
