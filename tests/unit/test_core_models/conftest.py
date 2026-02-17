"""Shared fixtures for domain model tests."""

from datetime import UTC, datetime

import pytest

from nornweave_core.models.identifiers import (
    AgentId,
    ChunkId,
    DocumentId,
    DomainId,
    QueryId,
    TraceId,
)


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
def query_id() -> QueryId:
    return QueryId("a3f8d2c1-4b5e-4f6a-8c7d-9e0f1a2b3c4d")


@pytest.fixture
def domain_id() -> DomainId:
    return DomainId("code")


@pytest.fixture
def agent_id() -> AgentId:
    return AgentId("code-memory")


@pytest.fixture
def document_id() -> DocumentId:
    return DocumentId("b7e4a1d9-2c3d-4e5f-6a7b-8c9d0e1f2a3b")


@pytest.fixture
def chunk_id() -> ChunkId:
    return ChunkId("c9f2b3e8-1a2b-3c4d-5e6f-7a8b9c0d1e2f")


@pytest.fixture
def trace_id() -> TraceId:
    return TraceId("4bf92f3577b34da6a3ce929d0e0e4736")
