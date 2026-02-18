"""End-to-end workflow: ingest doc → create chunks → search → retrieve parent doc."""

from datetime import UTC, datetime

import pytest

from nornweave_core.models.entities import Chunk, Document
from nornweave_core.models.identifiers import ChunkId, DocumentId, DomainId
from nornweave_core.models.values import EmbeddingVector
from nornweave_storage.repositories.chunk import ChunkRepository
from nornweave_storage.repositories.document import DocumentRepository

pytestmark = pytest.mark.integration


def _unit_vector(dim: int, index: int) -> list[float]:
    """Create a unit vector with 1.0 at the given index."""
    v = [0.0] * dim
    v[index] = 1.0
    return v


class TestIngestSearchRetrieve:
    async def test_full_workflow(
        self, doc_repo: DocumentRepository, chunk_repo: ChunkRepository
    ) -> None:
        """Milestone test: insert doc → chunk → search → verify match → get parent doc."""
        now = datetime.now(UTC)

        # 1. Ingest a document
        doc = Document(
            id=DocumentId("doc-payment"),
            domain_id=DomainId("code"),
            source_path="src/payment.py",
            content="class PaymentProcessor:\n    def charge(self, amount): ...",
            content_hash="payment-hash-001",
            metadata={"language": "python"},
            ingested_at=now,
            source_updated_at=now,
        )
        created_doc = await doc_repo.create(doc)
        assert created_doc.id == DocumentId("doc-payment")

        # 2. Create chunks with embeddings
        chunks = [
            Chunk(
                id=ChunkId("chunk-pay-0"),
                document_id=DocumentId("doc-payment"),
                domain_id=DomainId("code"),
                content="class PaymentProcessor:",
                embedding=EmbeddingVector(
                    values=_unit_vector(768, 0),
                    dimensions=768,
                    model_name="test-model",
                ),
                position=0,
                token_count=3,
                created_at=now,
            ),
            Chunk(
                id=ChunkId("chunk-pay-1"),
                document_id=DocumentId("doc-payment"),
                domain_id=DomainId("code"),
                content="def charge(self, amount): ...",
                embedding=EmbeddingVector(
                    values=_unit_vector(768, 1),
                    dimensions=768,
                    model_name="test-model",
                ),
                position=1,
                token_count=6,
                created_at=now,
            ),
        ]
        created_chunks = await chunk_repo.bulk_create(chunks)
        assert len(created_chunks) == 2

        # 3. Search with a query vector similar to chunk-pay-0
        query = _unit_vector(768, 0)
        results = await chunk_repo.search_similar(DomainId("code"), query, top_k=5)

        # 4. Verify the best match is chunk-pay-0
        assert len(results) >= 1
        best_chunk, similarity = results[0]
        assert best_chunk.id == ChunkId("chunk-pay-0")
        assert similarity > 0.9

        # 5. Retrieve the parent document from the best match
        parent = await doc_repo.get_by_id(best_chunk.document_id)
        assert parent.id == DocumentId("doc-payment")
        assert parent.source_path == "src/payment.py"
        assert "PaymentProcessor" in parent.content
