"""Integration tests for ChunkRepository against pgvector."""

from datetime import UTC, datetime

import pytest

from nornweave_core.models.entities import Chunk, Document
from nornweave_core.models.identifiers import ChunkId, DocumentId, DomainId
from nornweave_core.models.values import EmbeddingVector
from nornweave_storage.exceptions import ChunkNotFoundError
from nornweave_storage.repositories.chunk import ChunkRepository
from nornweave_storage.repositories.document import DocumentRepository

pytestmark = pytest.mark.integration


def _make_doc(doc_id: str = "doc-1") -> Document:
    now = datetime.now(UTC)
    return Document(
        id=DocumentId(doc_id),
        domain_id=DomainId("code"),
        source_path="src/main.py",
        content="code",
        content_hash=f"hash-{doc_id}",
        ingested_at=now,
        source_updated_at=now,
    )


def _make_chunk(
    chunk_id: str = "chunk-1",
    doc_id: str = "doc-1",
    position: int = 0,
    embedding_values: list[float] | None = None,
) -> Chunk:
    now = datetime.now(UTC)
    values = embedding_values if embedding_values is not None else [0.1] * 768
    return Chunk(
        id=ChunkId(chunk_id),
        document_id=DocumentId(doc_id),
        domain_id=DomainId("code"),
        content=f"content of {chunk_id}",
        embedding=EmbeddingVector(
            values=values,
            dimensions=768,
            model_name="test-model",
        ),
        position=position,
        token_count=5,
        created_at=now,
    )


class TestBulkCreate:
    async def test_bulk_create(
        self, doc_repo: DocumentRepository, chunk_repo: ChunkRepository
    ) -> None:
        await doc_repo.create(_make_doc())
        chunks = [
            _make_chunk("chunk-1", position=0),
            _make_chunk("chunk-2", position=1),
        ]
        created = await chunk_repo.bulk_create(chunks)
        assert len(created) == 2
        assert created[0].id == ChunkId("chunk-1")
        assert created[1].id == ChunkId("chunk-2")

    async def test_bulk_create_empty(self, chunk_repo: ChunkRepository) -> None:
        result = await chunk_repo.bulk_create([])
        assert result == []


class TestGetById:
    async def test_found(self, doc_repo: DocumentRepository, chunk_repo: ChunkRepository) -> None:
        await doc_repo.create(_make_doc())
        await chunk_repo.bulk_create([_make_chunk()])
        found = await chunk_repo.get_by_id(ChunkId("chunk-1"))
        assert found.id == ChunkId("chunk-1")
        assert found.embedding.dimensions == 768

    async def test_not_found(self, chunk_repo: ChunkRepository) -> None:
        with pytest.raises(ChunkNotFoundError):
            await chunk_repo.get_by_id(ChunkId("nonexistent"))


class TestGetByDocumentId:
    async def test_ordered_by_position(
        self, doc_repo: DocumentRepository, chunk_repo: ChunkRepository
    ) -> None:
        await doc_repo.create(_make_doc())
        # Insert out of order
        chunks = [
            _make_chunk("chunk-2", position=1),
            _make_chunk("chunk-0", position=0),
            _make_chunk("chunk-3", position=2),
        ]
        await chunk_repo.bulk_create(chunks)
        result = await chunk_repo.get_by_document_id(DocumentId("doc-1"))
        assert len(result) == 3
        assert [c.position for c in result] == [0, 1, 2]


class TestDeleteByDocumentId:
    async def test_delete(self, doc_repo: DocumentRepository, chunk_repo: ChunkRepository) -> None:
        await doc_repo.create(_make_doc())
        await chunk_repo.bulk_create([_make_chunk("chunk-1"), _make_chunk("chunk-2", position=1)])
        deleted = await chunk_repo.delete_by_document_id(DocumentId("doc-1"))
        assert deleted == 2
        remaining = await chunk_repo.get_by_document_id(DocumentId("doc-1"))
        assert remaining == []


class TestCountByDomain:
    async def test_count(self, doc_repo: DocumentRepository, chunk_repo: ChunkRepository) -> None:
        await doc_repo.create(_make_doc())
        await chunk_repo.bulk_create([_make_chunk("chunk-1"), _make_chunk("chunk-2", position=1)])
        count = await chunk_repo.count_by_domain(DomainId("code"))
        assert count == 2

    async def test_count_empty(self, chunk_repo: ChunkRepository) -> None:
        count = await chunk_repo.count_by_domain(DomainId("nonexistent"))
        assert count == 0
