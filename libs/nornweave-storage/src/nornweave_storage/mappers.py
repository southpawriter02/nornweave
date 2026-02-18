"""Bidirectional mappers between domain models and database rows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from nornweave_core.models.entities import Chunk, Document
from nornweave_core.models.identifiers import ChunkId, DocumentId, DomainId
from nornweave_core.models.values import EmbeddingVector

if TYPE_CHECKING:
    from datetime import datetime


class DocumentMapper:
    """Maps between Document domain objects and database rows."""

    @staticmethod
    def to_row(doc: Document) -> dict[str, Any]:
        """Convert a Document to a dict suitable for INSERT/UPDATE."""
        return {
            "id": str(doc.id),
            "domain_id": str(doc.domain_id),
            "source_path": doc.source_path,
            "content": doc.content,
            "content_hash": doc.content_hash,
            "metadata": doc.metadata,
            "ingested_at": doc.ingested_at,
            "source_updated_at": doc.source_updated_at,
        }

    @staticmethod
    def from_row(row: dict[str, Any]) -> Document:
        """Reconstruct a Document from a database row."""
        return Document(
            id=DocumentId(row["id"]),
            domain_id=DomainId(row["domain_id"]),
            source_path=row["source_path"],
            content=row["content"],
            content_hash=row["content_hash"],
            metadata=row["metadata"],
            ingested_at=row["ingested_at"],
            source_updated_at=row["source_updated_at"],
        )


class ChunkMapper:
    """Maps between Chunk domain objects and database rows."""

    @staticmethod
    def to_row(chunk: Chunk) -> dict[str, Any]:
        """Convert a Chunk to a dict suitable for INSERT.

        Converts the EmbeddingVector values to a numpy float32 array for pgvector,
        and stores dimension/model info as separate columns.
        """
        return {
            "id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "domain_id": str(chunk.domain_id),
            "content": chunk.content,
            "embedding": np.array(chunk.embedding.values, dtype=np.float32),
            "embedding_dimensions": chunk.embedding.dimensions,
            "embedding_model_name": chunk.embedding.model_name,
            "position": chunk.position,
            "token_count": chunk.token_count,
            "metadata": chunk.metadata,
            "created_at": chunk.created_at,
        }

    @staticmethod
    def from_row(row: dict[str, Any]) -> Chunk:
        """Reconstruct a Chunk from a database row."""
        embedding_array: np.ndarray[Any, np.dtype[np.floating[Any]]] = row["embedding"]
        dimensions: int = row["embedding_dimensions"]
        model_name: str = row["embedding_model_name"]

        dim_value: int = dimensions

        embedding = EmbeddingVector(
            values=embedding_array.tolist(),
            dimensions=dim_value,  # type: ignore[arg-type]
            model_name=model_name,
        )

        created_at: datetime = row["created_at"]

        return Chunk(
            id=ChunkId(row["id"]),
            document_id=DocumentId(row["document_id"]),
            domain_id=DomainId(row["domain_id"]),
            content=row["content"],
            embedding=embedding,
            position=row["position"],
            token_count=row["token_count"],
            metadata=row["metadata"],
            created_at=created_at,
        )
