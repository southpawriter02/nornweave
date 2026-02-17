"""Tests for domain enumerations."""

import pytest

from nornweave_core.models.enums import (
    AgentStatus,
    ChunkingStrategy,
    ConflictStrategy,
    DomainType,
    IngestStatus,
)


class TestDomainType:
    def test_values(self) -> None:
        assert set(DomainType) == {
            DomainType.CODE,
            DomainType.DOCUMENTATION,
            DomainType.CONVERSATIONS,
            DomainType.RESEARCH,
        }

    def test_string_value(self) -> None:
        assert DomainType.CODE == "CODE"
        assert str(DomainType.CODE) == "CODE"

    def test_from_string(self) -> None:
        assert DomainType("CODE") is DomainType.CODE

    def test_invalid_value(self) -> None:
        with pytest.raises(ValueError):
            DomainType("INVALID")


class TestAgentStatus:
    def test_values(self) -> None:
        assert set(AgentStatus) == {
            AgentStatus.STARTING,
            AgentStatus.READY,
            AgentStatus.DEGRADED,
            AgentStatus.DRAINING,
            AgentStatus.OFFLINE,
        }

    def test_string_value(self) -> None:
        assert AgentStatus.READY == "READY"

    def test_from_string(self) -> None:
        assert AgentStatus("DRAINING") is AgentStatus.DRAINING


class TestConflictStrategy:
    def test_values(self) -> None:
        assert set(ConflictStrategy) == {
            ConflictStrategy.RECENCY,
            ConflictStrategy.SOURCE_AUTHORITY,
            ConflictStrategy.CONFIDENCE,
            ConflictStrategy.FLAG,
            ConflictStrategy.RECENCY_THEN_FLAG,
        }

    def test_string_value(self) -> None:
        assert ConflictStrategy.SOURCE_AUTHORITY == "SOURCE_AUTHORITY"


class TestChunkingStrategy:
    def test_values(self) -> None:
        assert set(ChunkingStrategy) == {
            ChunkingStrategy.SYNTAX_AWARE,
            ChunkingStrategy.HIERARCHICAL_SECTIONS,
            ChunkingStrategy.MESSAGE_BOUNDARY,
            ChunkingStrategy.RECURSIVE_CHARACTER,
        }

    def test_string_value(self) -> None:
        assert ChunkingStrategy.SYNTAX_AWARE == "SYNTAX_AWARE"


class TestIngestStatus:
    def test_values(self) -> None:
        assert set(IngestStatus) == {
            IngestStatus.ACCEPTED,
            IngestStatus.INDEXED,
            IngestStatus.REJECTED,
            IngestStatus.FAILED,
        }

    def test_string_value(self) -> None:
        assert IngestStatus.ACCEPTED == "ACCEPTED"
