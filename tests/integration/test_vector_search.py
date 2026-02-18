"""Integration tests for vector similarity search."""

from datetime import UTC, datetime

import pytest

from nornweave_core.models.entities import Chunk, Document
from nornweave_core.models.identifiers import ChunkId, DocumentId, DomainId
from nornweave_core.models.values import EmbeddingVector
from nornweave_storage.repositories.chunk import ChunkRepository
from nornweave_storage.repositories.document import DocumentRepository

pytestmark = pytest.mark.integration


def _make_doc(doc_id: str = "doc-1", domain: str = "code") -> Document:
    now = datetime.now(UTC)
    return Document(
        id=DocumentId(doc_id),
        domain_id=DomainId(domain),
        source_path="src/main.py",
        content="code",
        content_hash=f"hash-{doc_id}",
        ingested_at=now,
        source_updated_at=now,
    )


def _make_chunk(
    chunk_id: str,
    doc_id: str = "doc-1",
    domain: str = "code",
    embedding_values: list[float] | None = None,
    position: int = 0,
) -> Chunk:
    now = datetime.now(UTC)
    values = embedding_values if embedding_values is not None else [0.0] * 768
    return Chunk(
        id=ChunkId(chunk_id),
        document_id=DocumentId(doc_id),
        domain_id=DomainId(domain),
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


def _unit_vector(dim: int, index: int) -> list[float]:
    """Create a unit vector with 1.0 at the given index, zeros elsewhere."""
    v = [0.0] * dim
    v[index] = 1.0
    return v


class TestSearchSimilar:
    async def test_ranked_order(
        self, doc_repo: DocumentRepository, chunk_repo: ChunkRepository
    ) -> None:
        """Chunks closer to the query vector should rank higher."""
        await doc_repo.create(_make_doc())

        # Three chunks with different embedding directions
        c1 = _make_chunk("chunk-1", embedding_values=_unit_vector(768, 0), position=0)
        c2 = _make_chunk("chunk-2", embedding_values=_unit_vector(768, 1), position=1)
        c3 = _make_chunk("chunk-3", embedding_values=_unit_vector(768, 2), position=2)
        await chunk_repo.bulk_create([c1, c2, c3])

        # Query is most similar to chunk-1 (same direction)
        query = _unit_vector(768, 0)
        results = await chunk_repo.search_similar(DomainId("code"), query, top_k=3)

        assert len(results) >= 1
        best_chunk, best_score = results[0]
        assert best_chunk.id == ChunkId("chunk-1")
        assert best_score > 0.9  # near-perfect match

    async def test_top_k_limit(
        self, doc_repo: DocumentRepository, chunk_repo: ChunkRepository
    ) -> None:
        await doc_repo.create(_make_doc())

        chunks = [
            _make_chunk(f"chunk-{i}", embedding_values=_unit_vector(768, i), position=i)
            for i in range(5)
        ]
        await chunk_repo.bulk_create(chunks)

        query = _unit_vector(768, 0)
        results = await chunk_repo.search_similar(DomainId("code"), query, top_k=2)
        assert len(results) == 2

    async def test_min_similarity_filtering(
        self, doc_repo: DocumentRepository, chunk_repo: ChunkRepository
    ) -> None:
        await doc_repo.create(_make_doc())

        # chunk-1 matches, chunk-2 is orthogonal
        c1 = _make_chunk("chunk-1", embedding_values=_unit_vector(768, 0))
        c2 = _make_chunk("chunk-2", embedding_values=_unit_vector(768, 1), position=1)
        await chunk_repo.bulk_create([c1, c2])

        query = _unit_vector(768, 0)
        results = await chunk_repo.search_similar(DomainId("code"), query, min_similarity=0.5)

        # Only chunk-1 should pass the similarity threshold
        chunk_ids = [chunk.id for chunk, _ in results]
        assert ChunkId("chunk-1") in chunk_ids
        assert ChunkId("chunk-2") not in chunk_ids

    async def test_cross_domain_isolation(
        self, doc_repo: DocumentRepository, chunk_repo: ChunkRepository
    ) -> None:
        """Searching in one domain should not return chunks from another."""
        await doc_repo.create(_make_doc("doc-code", domain="code"))
        await doc_repo.create(_make_doc("doc-docs", domain="docs"))

        c_code = _make_chunk(
            "chunk-code",
            doc_id="doc-code",
            domain="code",
            embedding_values=_unit_vector(768, 0),
        )
        c_docs = _make_chunk(
            "chunk-docs",
            doc_id="doc-docs",
            domain="docs",
            embedding_values=_unit_vector(768, 0),
        )
        await chunk_repo.bulk_create([c_code, c_docs])

        query = _unit_vector(768, 0)

        code_results = await chunk_repo.search_similar(DomainId("code"), query)
        docs_results = await chunk_repo.search_similar(DomainId("docs"), query)

        code_ids = {c.id for c, _ in code_results}
        docs_ids = {c.id for c, _ in docs_results}

        assert ChunkId("chunk-code") in code_ids
        assert ChunkId("chunk-docs") not in code_ids
        assert ChunkId("chunk-docs") in docs_ids
        assert ChunkId("chunk-code") not in docs_ids
