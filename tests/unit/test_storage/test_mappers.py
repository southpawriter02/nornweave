"""Tests for Document and Chunk mappers."""

from datetime import UTC, datetime
from typing import Any

import numpy as np

from nornweave_core.models.entities import Chunk, Document
from nornweave_core.models.identifiers import ChunkId, DocumentId, DomainId
from nornweave_core.models.values import EmbeddingVector
from nornweave_storage.mappers import ChunkMapper, DocumentMapper


class TestDocumentMapper:
    def _make_document(self, now: datetime) -> Document:
        return Document(
            id=DocumentId("doc-1"),
            domain_id=DomainId("code"),
            source_path="src/main.py",
            content="def main(): pass",
            content_hash="abc123",
            metadata={"language": "python"},
            ingested_at=now,
            source_updated_at=now,
        )

    def test_to_row(self) -> None:
        now = datetime.now(UTC)
        doc = self._make_document(now)
        row = DocumentMapper.to_row(doc)

        assert row["id"] == "doc-1"
        assert row["domain_id"] == "code"
        assert row["source_path"] == "src/main.py"
        assert row["content"] == "def main(): pass"
        assert row["content_hash"] == "abc123"
        assert row["metadata"] == {"language": "python"}
        assert row["ingested_at"] == now
        assert row["source_updated_at"] == now

    def test_from_row(self) -> None:
        now = datetime.now(UTC)
        row: dict[str, Any] = {
            "id": "doc-1",
            "domain_id": "code",
            "source_path": "src/main.py",
            "content": "def main(): pass",
            "content_hash": "abc123",
            "metadata": {"language": "python"},
            "ingested_at": now,
            "source_updated_at": now,
        }
        doc = DocumentMapper.from_row(row)

        assert doc.id == DocumentId("doc-1")
        assert doc.domain_id == DomainId("code")
        assert doc.source_path == "src/main.py"
        assert doc.content == "def main(): pass"
        assert doc.content_hash == "abc123"
        assert doc.metadata == {"language": "python"}

    def test_round_trip(self) -> None:
        now = datetime.now(UTC)
        original = self._make_document(now)
        row = DocumentMapper.to_row(original)
        restored = DocumentMapper.from_row(row)

        assert restored.id == original.id
        assert restored.domain_id == original.domain_id
        assert restored.source_path == original.source_path
        assert restored.content == original.content
        assert restored.content_hash == original.content_hash
        assert restored.metadata == original.metadata

    def test_empty_metadata(self) -> None:
        now = datetime.now(UTC)
        doc = Document(
            id=DocumentId("doc-2"),
            domain_id=DomainId("docs"),
            source_path="README.md",
            content="# Hello",
            content_hash="def456",
            ingested_at=now,
            source_updated_at=now,
        )
        row = DocumentMapper.to_row(doc)
        assert row["metadata"] == {}
        restored = DocumentMapper.from_row(row)
        assert restored.metadata == {}


class TestChunkMapper:
    def _make_chunk(self, now: datetime) -> Chunk:
        return Chunk(
            id=ChunkId("chunk-1"),
            document_id=DocumentId("doc-1"),
            domain_id=DomainId("code"),
            content="def main(): pass",
            embedding=EmbeddingVector(
                values=[0.1] * 768,
                dimensions=768,
                model_name="test-model",
            ),
            position=0,
            token_count=5,
            metadata={"start_line": 1},
            created_at=now,
        )

    def test_to_row_embedding_is_numpy(self) -> None:
        now = datetime.now(UTC)
        chunk = self._make_chunk(now)
        row = ChunkMapper.to_row(chunk)

        assert isinstance(row["embedding"], np.ndarray)
        assert row["embedding"].dtype == np.float32
        assert len(row["embedding"]) == 768

    def test_to_row_fields(self) -> None:
        now = datetime.now(UTC)
        chunk = self._make_chunk(now)
        row = ChunkMapper.to_row(chunk)

        assert row["id"] == "chunk-1"
        assert row["document_id"] == "doc-1"
        assert row["domain_id"] == "code"
        assert row["embedding_dimensions"] == 768
        assert row["embedding_model_name"] == "test-model"
        assert row["position"] == 0
        assert row["token_count"] == 5
        assert row["metadata"] == {"start_line": 1}

    def test_from_row(self) -> None:
        now = datetime.now(UTC)
        row: dict[str, Any] = {
            "id": "chunk-1",
            "document_id": "doc-1",
            "domain_id": "code",
            "content": "def main(): pass",
            "embedding": np.array([0.1] * 768, dtype=np.float32),
            "embedding_dimensions": 768,
            "embedding_model_name": "test-model",
            "position": 0,
            "token_count": 5,
            "metadata": {"start_line": 1},
            "created_at": now,
        }
        chunk = ChunkMapper.from_row(row)

        assert chunk.id == ChunkId("chunk-1")
        assert chunk.document_id == DocumentId("doc-1")
        assert chunk.embedding.dimensions == 768
        assert chunk.embedding.model_name == "test-model"
        assert len(chunk.embedding.values) == 768

    def test_round_trip(self) -> None:
        now = datetime.now(UTC)
        original = self._make_chunk(now)
        row = ChunkMapper.to_row(original)

        # Simulate DB return — from_row expects numpy array
        restored = ChunkMapper.from_row(row)

        assert restored.id == original.id
        assert restored.document_id == original.document_id
        assert restored.domain_id == original.domain_id
        assert restored.content == original.content
        assert restored.position == original.position
        assert restored.token_count == original.token_count
        assert restored.embedding.dimensions == original.embedding.dimensions
        assert restored.embedding.model_name == original.embedding.model_name

    def test_384_dimensions(self) -> None:
        now = datetime.now(UTC)
        chunk = Chunk(
            id=ChunkId("chunk-384"),
            document_id=DocumentId("doc-1"),
            domain_id=DomainId("code"),
            content="small model",
            embedding=EmbeddingVector(
                values=[0.2] * 384,
                dimensions=384,
                model_name="small-model",
            ),
            position=0,
            token_count=2,
            created_at=now,
        )
        row = ChunkMapper.to_row(chunk)
        assert row["embedding_dimensions"] == 384
        assert len(row["embedding"]) == 384

        restored = ChunkMapper.from_row(row)
        assert restored.embedding.dimensions == 384

    def test_1536_dimensions(self) -> None:
        now = datetime.now(UTC)
        chunk = Chunk(
            id=ChunkId("chunk-1536"),
            document_id=DocumentId("doc-1"),
            domain_id=DomainId("code"),
            content="large model",
            embedding=EmbeddingVector(
                values=[0.3] * 1536,
                dimensions=1536,
                model_name="large-model",
            ),
            position=0,
            token_count=2,
            created_at=now,
        )
        row = ChunkMapper.to_row(chunk)
        assert row["embedding_dimensions"] == 1536
        assert len(row["embedding"]) == 1536

        restored = ChunkMapper.from_row(row)
        assert restored.embedding.dimensions == 1536
