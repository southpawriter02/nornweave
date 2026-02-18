"""Integration test fixtures — pgvector via testcontainers."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]

from nornweave_storage.config import DatabaseConfig
from nornweave_storage.pool import ConnectionPool
from nornweave_storage.repositories.chunk import ChunkRepository
from nornweave_storage.repositories.document import DocumentRepository

PGVECTOR_IMAGE = "pgvector/pgvector:pg16"


@pytest.fixture(scope="session")
def postgres_container() -> Any:
    """Start a pgvector container for the test session."""
    with PostgresContainer(
        image=PGVECTOR_IMAGE,
        username="test",
        password="test",
        dbname="test_nornweave",
    ) as container:
        yield container


@pytest.fixture(scope="session")
def db_config(postgres_container: Any) -> DatabaseConfig:
    """Build a DatabaseConfig pointing at the test container."""
    host = postgres_container.get_container_host_ip()
    port = int(postgres_container.get_exposed_port(5432))
    return DatabaseConfig(
        host=host,
        port=port,
        user="test",
        password="test",
        name="test_nornweave",
    )


@pytest.fixture(scope="session")
def _run_migrations(db_config: DatabaseConfig) -> None:
    """Run Alembic migrations against the test database."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config()
    alembic_cfg.set_main_option(
        "script_location",
        "libs/nornweave-storage/src/nornweave_storage/migrations",
    )
    alembic_cfg.set_main_option("sqlalchemy.url", db_config.dsn)
    command.upgrade(alembic_cfg, "head")


@pytest.fixture
async def pool(
    db_config: DatabaseConfig,
    _run_migrations: None,
) -> AsyncIterator[ConnectionPool]:
    """Provide an open ConnectionPool for each test."""
    async with ConnectionPool(db_config) as p:
        yield p


@pytest.fixture
async def conn(
    pool: ConnectionPool,
) -> AsyncIterator[AsyncConnection[dict[str, object]]]:
    """Provide a connection and clean up tables after each test."""
    async with pool.connection() as connection:
        yield connection
        # Clean up after each test — truncate in dependency order
        async with connection.cursor() as cur:
            await cur.execute("TRUNCATE chunks, documents CASCADE")


@pytest.fixture
def doc_repo(conn: AsyncConnection[dict[str, object]]) -> DocumentRepository:
    """Provide a DocumentRepository bound to the test connection."""
    return DocumentRepository(conn)


@pytest.fixture
def chunk_repo(conn: AsyncConnection[dict[str, object]]) -> ChunkRepository:
    """Provide a ChunkRepository bound to the test connection."""
    return ChunkRepository(conn)


@pytest.fixture
async def raw_conn(
    db_config: DatabaseConfig,
    _run_migrations: None,
) -> AsyncIterator[AsyncConnection[dict[str, object]]]:
    """Provide a raw psycopg connection (without pool) for verification queries."""
    from pgvector.psycopg import register_vector_async  # type: ignore[import-untyped]

    conn = await AsyncConnection.connect(db_config.dsn, row_factory=dict_row)
    await register_vector_async(conn)
    try:
        yield conn
    finally:
        await conn.close()
