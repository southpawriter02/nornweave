"""Async connection pool wrapper for psycopg3 + pgvector."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Self

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from nornweave_storage.config import DatabaseConfig


async def _configure_connection(conn: AsyncConnection[dict[str, object]]) -> None:
    """Register pgvector types on each new connection."""
    from pgvector.psycopg import register_vector_async  # type: ignore[import-untyped]

    await register_vector_async(conn)


class ConnectionPool:
    """Manages an async psycopg connection pool with pgvector support."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._pool: AsyncConnectionPool[AsyncConnection[dict[str, object]]] | None = None

    async def open(self) -> None:
        """Create and open the connection pool."""
        self._pool = AsyncConnectionPool[AsyncConnection[dict[str, object]]](
            conninfo=self._config.dsn,
            min_size=self._config.min_pool_size,
            max_size=self._config.max_pool_size,
            timeout=self._config.pool_timeout,
            open=False,
            configure=_configure_connection,
            kwargs={"row_factory": dict_row},
        )
        await self._pool.open()

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[AsyncConnection[dict[str, object]]]:
        """Yield an async connection from the pool."""
        if self._pool is None:
            msg = "Connection pool is not open. Call open() first."
            raise RuntimeError(msg)
        async with self._pool.connection() as conn:
            yield conn

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
