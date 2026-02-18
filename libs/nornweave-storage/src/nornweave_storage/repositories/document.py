"""Document repository — async CRUD for the documents table."""

from __future__ import annotations

from typing import TYPE_CHECKING

from psycopg import errors as pg_errors
from psycopg.sql import SQL

from nornweave_storage.exceptions import DocumentNotFoundError, DuplicateDocumentError
from nornweave_storage.mappers import DocumentMapper

if TYPE_CHECKING:
    from psycopg import AsyncConnection

    from nornweave_core.models.entities import Document
    from nornweave_core.models.identifiers import DocumentId, DomainId


class DocumentRepository:
    """Async repository for Document persistence against PostgreSQL."""

    def __init__(self, conn: AsyncConnection[dict[str, object]]) -> None:
        self._conn = conn

    async def create(self, document: Document) -> Document:
        """Insert a new document. Raises DuplicateDocumentError on conflict."""
        row = DocumentMapper.to_row(document)
        try:
            async with self._conn.cursor() as cur:
                await cur.execute(
                    SQL("""
                        INSERT INTO documents
                            (id, domain_id, source_path, content, content_hash,
                             metadata, ingested_at, source_updated_at)
                        VALUES
                            (%(id)s, %(domain_id)s, %(source_path)s, %(content)s,
                             %(content_hash)s, %(metadata)s, %(ingested_at)s,
                             %(source_updated_at)s)
                        RETURNING *
                    """),
                    row,
                )
                result = await cur.fetchone()
        except pg_errors.UniqueViolation:
            raise DuplicateDocumentError(
                domain_id=str(document.domain_id),
                content_hash=document.content_hash,
            ) from None
        if result is None:  # pragma: no cover
            msg = "INSERT RETURNING produced no rows"
            raise RuntimeError(msg)
        return DocumentMapper.from_row(dict(result))

    async def get_by_id(self, document_id: DocumentId) -> Document:
        """Fetch a document by its ID. Raises DocumentNotFoundError if missing."""
        async with self._conn.cursor() as cur:
            await cur.execute(
                SQL("SELECT * FROM documents WHERE id = %(id)s"),
                {"id": str(document_id)},
            )
            row = await cur.fetchone()
        if row is None:
            raise DocumentNotFoundError(str(document_id))
        return DocumentMapper.from_row(dict(row))

    async def get_by_content_hash(self, domain_id: DomainId, content_hash: str) -> Document | None:
        """Look up a document by domain + content hash (dedup check)."""
        async with self._conn.cursor() as cur:
            await cur.execute(
                SQL(
                    "SELECT * FROM documents "
                    "WHERE domain_id = %(domain_id)s AND content_hash = %(content_hash)s"
                ),
                {"domain_id": str(domain_id), "content_hash": content_hash},
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return DocumentMapper.from_row(dict(row))

    async def list_by_domain(
        self, domain_id: DomainId, *, limit: int = 100, offset: int = 0
    ) -> list[Document]:
        """List documents in a domain, ordered by ingested_at DESC."""
        async with self._conn.cursor() as cur:
            await cur.execute(
                SQL(
                    "SELECT * FROM documents WHERE domain_id = %(domain_id)s "
                    "ORDER BY ingested_at DESC LIMIT %(limit)s OFFSET %(offset)s"
                ),
                {"domain_id": str(domain_id), "limit": limit, "offset": offset},
            )
            rows = await cur.fetchall()
        return [DocumentMapper.from_row(dict(r)) for r in rows]

    async def update(self, document: Document) -> Document:
        """Update an existing document. Raises DocumentNotFoundError if missing."""
        row = DocumentMapper.to_row(document)
        async with self._conn.cursor() as cur:
            await cur.execute(
                SQL("""
                    UPDATE documents SET
                        domain_id = %(domain_id)s,
                        source_path = %(source_path)s,
                        content = %(content)s,
                        content_hash = %(content_hash)s,
                        metadata = %(metadata)s,
                        ingested_at = %(ingested_at)s,
                        source_updated_at = %(source_updated_at)s
                    WHERE id = %(id)s
                    RETURNING *
                """),
                row,
            )
            result = await cur.fetchone()
        if result is None:
            raise DocumentNotFoundError(str(document.id))
        return DocumentMapper.from_row(dict(result))

    async def delete(self, document_id: DocumentId) -> None:
        """Delete a document (chunks cascade). Raises DocumentNotFoundError if missing."""
        async with self._conn.cursor() as cur:
            await cur.execute(
                SQL("DELETE FROM documents WHERE id = %(id)s RETURNING id"),
                {"id": str(document_id)},
            )
            result = await cur.fetchone()
        if result is None:
            raise DocumentNotFoundError(str(document_id))

    async def count_by_domain(self, domain_id: DomainId) -> int:
        """Return the number of documents in a domain."""
        async with self._conn.cursor() as cur:
            await cur.execute(
                SQL("SELECT count(*) AS cnt FROM documents WHERE domain_id = %(domain_id)s"),
                {"domain_id": str(domain_id)},
            )
            row = await cur.fetchone()
        return int(str(row["cnt"])) if row else 0
