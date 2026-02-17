"""Tests for frozen value objects."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nornweave_core.models.identifiers import AgentId, ChunkId, DocumentId, DomainId
from nornweave_core.models.values import (
    CoverageGap,
    DomainSignal,
    EmbeddingVector,
    RelevanceScore,
    SourceCitation,
    TokenBudget,
)


class TestRelevanceScore:
    def test_valid_score(self) -> None:
        s = RelevanceScore(value=0.85)
        assert s.value == 0.85

    def test_zero(self) -> None:
        s = RelevanceScore(value=0.0)
        assert s.value == 0.0

    def test_one(self) -> None:
        s = RelevanceScore(value=1.0)
        assert s.value == 1.0

    def test_too_low(self) -> None:
        with pytest.raises(ValidationError):
            RelevanceScore(value=-0.1)

    def test_too_high(self) -> None:
        with pytest.raises(ValidationError):
            RelevanceScore(value=1.1)

    def test_frozen(self) -> None:
        s = RelevanceScore(value=0.5)
        with pytest.raises(ValidationError):
            s.value = 0.9  # type: ignore[misc]

    def test_json_round_trip(self) -> None:
        s = RelevanceScore(value=0.42)
        restored = RelevanceScore.model_validate_json(s.model_dump_json())
        assert restored == s


class TestEmbeddingVector:
    def test_valid_384(self) -> None:
        v = EmbeddingVector(values=[0.1] * 384, dimensions=384, model_name="test-model")
        assert len(v.values) == 384
        assert v.dimensions == 384

    def test_valid_768(self) -> None:
        v = EmbeddingVector(values=[0.0] * 768, dimensions=768, model_name="bert")
        assert v.dimensions == 768

    def test_valid_1536(self) -> None:
        v = EmbeddingVector(values=[0.0] * 1536, dimensions=1536, model_name="openai")
        assert v.dimensions == 1536

    def test_dimension_mismatch(self) -> None:
        with pytest.raises(ValidationError, match="Expected 384 values, got 10"):
            EmbeddingVector(values=[0.1] * 10, dimensions=384, model_name="test")

    def test_invalid_dimensions(self) -> None:
        with pytest.raises(ValidationError):
            EmbeddingVector(values=[0.1] * 512, dimensions=512, model_name="test")  # type: ignore[arg-type]

    def test_empty_model_name(self) -> None:
        with pytest.raises(ValidationError):
            EmbeddingVector(values=[0.1] * 384, dimensions=384, model_name="")

    def test_frozen(self) -> None:
        v = EmbeddingVector(values=[0.1] * 384, dimensions=384, model_name="test")
        with pytest.raises(ValidationError):
            v.model_name = "other"  # type: ignore[misc]

    def test_json_round_trip(self) -> None:
        v = EmbeddingVector(values=[0.1] * 384, dimensions=384, model_name="test")
        restored = EmbeddingVector.model_validate_json(v.model_dump_json())
        assert restored == v


class TestSourceCitation:
    def test_valid(self) -> None:
        ts = datetime.now(UTC)
        c = SourceCitation(
            document_id=DocumentId("doc-1"),
            chunk_id=ChunkId("chunk-1"),
            domain_id=DomainId("code"),
            source_path="src/main.py",
            timestamp=ts,
        )
        assert c.document_id == "doc-1"
        assert c.line_range is None

    def test_with_line_range(self) -> None:
        ts = datetime.now(UTC)
        c = SourceCitation(
            document_id=DocumentId("doc-1"),
            chunk_id=ChunkId("chunk-1"),
            domain_id=DomainId("code"),
            source_path="src/main.py",
            line_range=(42, 67),
            timestamp=ts,
        )
        assert c.line_range == (42, 67)

    def test_frozen(self) -> None:
        ts = datetime.now(UTC)
        c = SourceCitation(
            document_id=DocumentId("doc-1"),
            chunk_id=ChunkId("chunk-1"),
            domain_id=DomainId("code"),
            source_path="src/main.py",
            timestamp=ts,
        )
        with pytest.raises(ValidationError):
            c.source_path = "other"  # type: ignore[misc]

    def test_json_round_trip(self) -> None:
        ts = datetime.now(UTC)
        c = SourceCitation(
            document_id=DocumentId("doc-1"),
            chunk_id=ChunkId("chunk-1"),
            domain_id=DomainId("code"),
            source_path="src/main.py",
            line_range=(10, 20),
            timestamp=ts,
        )
        restored = SourceCitation.model_validate_json(c.model_dump_json())
        assert restored == c


class TestDomainSignal:
    def test_valid(self) -> None:
        s = DomainSignal(
            domain_id=DomainId("code"),
            score=RelevanceScore(value=0.9),
            keywords=["payment", "error"],
        )
        assert s.domain_id == "code"
        assert s.score.value == 0.9
        assert s.keywords == ["payment", "error"]

    def test_empty_keywords_default(self) -> None:
        s = DomainSignal(
            domain_id=DomainId("code"),
            score=RelevanceScore(value=0.5),
        )
        assert s.keywords == []

    def test_frozen(self) -> None:
        s = DomainSignal(
            domain_id=DomainId("code"),
            score=RelevanceScore(value=0.5),
        )
        with pytest.raises(ValidationError):
            s.domain_id = DomainId("other")  # type: ignore[misc]


class TestCoverageGap:
    def test_valid(self) -> None:
        g = CoverageGap(
            domain_id=DomainId("code"),
            agent_id=AgentId("code-memory"),
            reason="timeout after 5000ms",
        )
        assert g.reason == "timeout after 5000ms"

    def test_frozen(self) -> None:
        g = CoverageGap(
            domain_id=DomainId("code"),
            agent_id=AgentId("code-memory"),
            reason="timeout",
        )
        with pytest.raises(ValidationError):
            g.reason = "other"  # type: ignore[misc]


class TestTokenBudget:
    def test_valid(self) -> None:
        t = TokenBudget(limit=4096, consumed=1024, model="gpt-4")
        assert t.limit == 4096
        assert t.consumed == 1024

    def test_zero_consumed(self) -> None:
        t = TokenBudget(limit=100, consumed=0, model="tiktoken")
        assert t.consumed == 0

    def test_limit_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            TokenBudget(limit=0, consumed=0, model="tiktoken")

    def test_consumed_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            TokenBudget(limit=100, consumed=-1, model="tiktoken")

    def test_empty_model_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TokenBudget(limit=100, consumed=0, model="")

    def test_frozen(self) -> None:
        t = TokenBudget(limit=100, consumed=0, model="tiktoken")
        with pytest.raises(ValidationError):
            t.limit = 200  # type: ignore[misc]

    def test_json_round_trip(self) -> None:
        t = TokenBudget(limit=4096, consumed=512, model="cl100k_base")
        restored = TokenBudget.model_validate_json(t.model_dump_json())
        assert restored == t
