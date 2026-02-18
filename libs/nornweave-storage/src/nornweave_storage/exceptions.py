"""Storage error hierarchy for nornweave-storage."""


class StorageError(Exception):
    """Base exception for all storage-related errors."""


class StorageConnectionError(StorageError):
    """Failed to establish or maintain a database connection."""


class DocumentNotFoundError(StorageError):
    """Requested document does not exist."""

    def __init__(self, document_id: str) -> None:
        super().__init__(f"Document not found: {document_id}")
        self.document_id = document_id


class ChunkNotFoundError(StorageError):
    """Requested chunk does not exist."""

    def __init__(self, chunk_id: str) -> None:
        super().__init__(f"Chunk not found: {chunk_id}")
        self.chunk_id = chunk_id


class DuplicateDocumentError(StorageError):
    """A document with the same domain_id + content_hash already exists."""

    def __init__(self, domain_id: str, content_hash: str) -> None:
        super().__init__(f"Duplicate document in domain {domain_id!r} with hash {content_hash!r}")
        self.domain_id = domain_id
        self.content_hash = content_hash


class IntegrityError(StorageError):
    """A database integrity constraint was violated."""
