"""Chunk repository — async CRUD + vector search for the chunks table."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from psycopg.sql import SQL
from psycopg.types.json import Jsonb

from nornweave_storage.exceptions import ChunkNotFoundError
from nornweave_storage.mappers import ChunkMapper

if TYPE_CHECKING:
    from psycopg import AsyncConnection

    from nornweave_core.models.entities import Chunk
    from nornweave_core.models.identifiers import ChunkId, DocumentId, DomainId


class ChunkRepository:
    """Async repository for Chunk persistence and vector search against PostgreSQL + pgvector."""

    def __init__(self, conn: AsyncConnection[dict[str, object]]) -> None:
        self._conn = conn

    async def bulk_create(self, chunks: list[Chunk]) -> list[Chunk]:
        """Insert multiple chunks in a single transaction. Returns the inserted chunks."""
        if not chunks:
            return []

        results: list[Chunk] = []
        async with self._conn.cursor() as cur:
            for chunk in chunks:
                row = ChunkMapper.to_row(chunk)
                await cur.execute(
                    SQL("""
                        INSERT INTO chunks
                            (id, document_id, domain_id, content, embedding,
                             embedding_dimensions, embedding_model_name,
                             position, token_count, metadata, created_at)
                        VALUES
                            (%(id)s, %(document_id)s, %(domain_id)s, %(content)s,
                             %(embedding)s, %(embedding_dimensions)s,
                             %(embedding_model_name)s, %(position)s, %(token_count)s,
                             %(metadata)s, %(created_at)s)
                        RETURNING *
                    """),
                    {**row, "metadata": Jsonb(row["metadata"])},
                )
                result = await cur.fetchone()
                if result is not None:
                    results.append(ChunkMapper.from_row(dict(result)))
        return results

    async def get_by_id(self, chunk_id: ChunkId) -> Chunk:
        """Fetch a chunk by its ID. Raises ChunkNotFoundError if missing."""
        async with self._conn.cursor() as cur:
            await cur.execute(
                SQL("SELECT * FROM chunks WHERE id = %(id)s"),
                {"id": str(chunk_id)},
            )
            row = await cur.fetchone()
        if row is None:
            raise ChunkNotFoundError(str(chunk_id))
        return ChunkMapper.from_row(dict(row))

    async def get_by_document_id(self, document_id: DocumentId) -> list[Chunk]:
        """Fetch all chunks for a document, ordered by position ASC."""
        async with self._conn.cursor() as cur:
            await cur.execute(
                SQL(
                    "SELECT * FROM chunks WHERE document_id = %(document_id)s ORDER BY position ASC"
                ),
                {"document_id": str(document_id)},
            )
            rows = await cur.fetchall()
        return [ChunkMapper.from_row(dict(r)) for r in rows]

    async def search_similar(
        self,
        domain_id: DomainId,
        query_embedding: list[float],
        *,
        top_k: int = 10,
        min_similarity: float = 0.0,
    ) -> list[tuple[Chunk, float]]:
        """Find chunks most similar to a query vector using cosine distance.

        Returns (chunk, similarity) pairs in descending similarity order.
        Cosine distance via <=> is in [0, 2]; similarity = 1 - distance.
        """
        embedding_array = np.array(query_embedding, dtype=np.float32)

        async with self._conn.cursor() as cur:
            await cur.execute(
                SQL("""
                    SELECT *, 1 - (embedding <=> %(query)s) AS similarity
                    FROM chunks
                    WHERE domain_id = %(domain_id)s
                      AND 1 - (embedding <=> %(query)s) >= %(min_similarity)s
                    ORDER BY embedding <=> %(query)s
                    LIMIT %(top_k)s
                """),
                {
                    "query": embedding_array,
                    "domain_id": str(domain_id),
                    "min_similarity": min_similarity,
                    "top_k": top_k,
                },
            )
            rows = await cur.fetchall()

        results: list[tuple[Chunk, float]] = []
        for r in rows:
            row_dict = dict(r)
            similarity = float(str(row_dict.pop("similarity")))
            results.append((ChunkMapper.from_row(row_dict), similarity))
        return results

    async def delete_by_document_id(self, document_id: DocumentId) -> int:
        """Delete all chunks for a document. Returns the number of deleted rows."""
        async with self._conn.cursor() as cur:
            await cur.execute(
                SQL("DELETE FROM chunks WHERE document_id = %(document_id)s"),
                {"document_id": str(document_id)},
            )
            return cur.rowcount

    async def count_by_domain(self, domain_id: DomainId) -> int:
        """Return the number of chunks in a domain."""
        async with self._conn.cursor() as cur:
            await cur.execute(
                SQL("SELECT count(*) AS cnt FROM chunks WHERE domain_id = %(domain_id)s"),
                {"domain_id": str(domain_id)},
            )
            row = await cur.fetchone()
        return int(str(row["cnt"])) if row else 0
