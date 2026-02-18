"""Integration tests for DocumentRepository against pgvector."""

from datetime import UTC, datetime

import pytest

from nornweave_core.models.entities import Document
from nornweave_core.models.identifiers import DocumentId, DomainId
from nornweave_storage.exceptions import DocumentNotFoundError, DuplicateDocumentError
from nornweave_storage.repositories.document import DocumentRepository

pytestmark = pytest.mark.integration


def _make_doc(
    doc_id: str = "doc-1",
    domain: str = "code",
    content: str = "def main(): pass",
    content_hash: str = "hash-1",
) -> Document:
    now = datetime.now(UTC)
    return Document(
        id=DocumentId(doc_id),
        domain_id=DomainId(domain),
        source_path="src/main.py",
        content=content,
        content_hash=content_hash,
        ingested_at=now,
        source_updated_at=now,
    )


class TestCreate:
    async def test_create_and_return(self, doc_repo: DocumentRepository) -> None:
        doc = _make_doc()
        created = await doc_repo.create(doc)
        assert created.id == doc.id
        assert created.content == doc.content

    async def test_duplicate_raises(self, doc_repo: DocumentRepository) -> None:
        doc1 = _make_doc()
        await doc_repo.create(doc1)
        doc2 = _make_doc(doc_id="doc-2")  # same domain + hash
        with pytest.raises(DuplicateDocumentError):
            await doc_repo.create(doc2)


class TestGetById:
    async def test_found(self, doc_repo: DocumentRepository) -> None:
        doc = _make_doc()
        await doc_repo.create(doc)
        found = await doc_repo.get_by_id(DocumentId("doc-1"))
        assert found.id == DocumentId("doc-1")

    async def test_not_found(self, doc_repo: DocumentRepository) -> None:
        with pytest.raises(DocumentNotFoundError):
            await doc_repo.get_by_id(DocumentId("nonexistent"))


class TestGetByContentHash:
    async def test_found(self, doc_repo: DocumentRepository) -> None:
        doc = _make_doc()
        await doc_repo.create(doc)
        found = await doc_repo.get_by_content_hash(DomainId("code"), "hash-1")
        assert found is not None
        assert found.id == DocumentId("doc-1")

    async def test_not_found(self, doc_repo: DocumentRepository) -> None:
        result = await doc_repo.get_by_content_hash(DomainId("code"), "no-such-hash")
        assert result is None


class TestListByDomain:
    async def test_list(self, doc_repo: DocumentRepository) -> None:
        await doc_repo.create(_make_doc("doc-1", content_hash="h1"))
        await doc_repo.create(_make_doc("doc-2", content_hash="h2"))
        docs = await doc_repo.list_by_domain(DomainId("code"))
        assert len(docs) == 2

    async def test_list_empty_domain(self, doc_repo: DocumentRepository) -> None:
        docs = await doc_repo.list_by_domain(DomainId("nonexistent"))
        assert docs == []

    async def test_list_with_limit(self, doc_repo: DocumentRepository) -> None:
        await doc_repo.create(_make_doc("doc-1", content_hash="h1"))
        await doc_repo.create(_make_doc("doc-2", content_hash="h2"))
        docs = await doc_repo.list_by_domain(DomainId("code"), limit=1)
        assert len(docs) == 1


class TestUpdate:
    async def test_update(self, doc_repo: DocumentRepository) -> None:
        doc = _make_doc()
        await doc_repo.create(doc)
        updated_doc = doc.model_copy(update={"content": "new content", "content_hash": "hash-2"})
        result = await doc_repo.update(updated_doc)
        assert result.content == "new content"

    async def test_update_not_found(self, doc_repo: DocumentRepository) -> None:
        doc = _make_doc(doc_id="nonexistent")
        with pytest.raises(DocumentNotFoundError):
            await doc_repo.update(doc)


class TestDelete:
    async def test_delete(self, doc_repo: DocumentRepository) -> None:
        doc = _make_doc()
        await doc_repo.create(doc)
        await doc_repo.delete(DocumentId("doc-1"))
        with pytest.raises(DocumentNotFoundError):
            await doc_repo.get_by_id(DocumentId("doc-1"))

    async def test_delete_not_found(self, doc_repo: DocumentRepository) -> None:
        with pytest.raises(DocumentNotFoundError):
            await doc_repo.delete(DocumentId("nonexistent"))


class TestCountByDomain:
    async def test_count(self, doc_repo: DocumentRepository) -> None:
        await doc_repo.create(_make_doc("doc-1", content_hash="h1"))
        await doc_repo.create(_make_doc("doc-2", content_hash="h2"))
        count = await doc_repo.count_by_domain(DomainId("code"))
        assert count == 2

    async def test_count_empty(self, doc_repo: DocumentRepository) -> None:
        count = await doc_repo.count_by_domain(DomainId("nonexistent"))
        assert count == 0
