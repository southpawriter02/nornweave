"""Tests for request models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from nornweave_core.models.entities import Document
from nornweave_core.models.enums import AgentStatus, ConflictStrategy
from nornweave_core.models.identifiers import (
    AgentId,
    DocumentId,
    DomainId,
    QueryId,
    TraceId,
)
from nornweave_core.models.requests import (
    AgentRegisterRequest,
    FuseRequest,
    HeartbeatRequest,
    IngestRequest,
    QueryRequest,
    RecallRequest,
)
from nornweave_core.models.responses import RecallResponse
from nornweave_core.models.values import CoverageGap


class TestRecallRequest:
    def test_valid(self, query_id: QueryId, domain_id: DomainId, trace_id: TraceId) -> None:
        req = RecallRequest(
            query_id=query_id,
            query_text="payment error",
            original_text="what changed in payments",
            domain_id=domain_id,
            trace_id=trace_id,
            timeout_ms=5000,
        )
        assert req.top_k == 20  # default
        assert req.filters == {}

    def test_custom_top_k(self, query_id: QueryId, domain_id: DomainId, trace_id: TraceId) -> None:
        req = RecallRequest(
            query_id=query_id,
            query_text="query",
            original_text="query",
            domain_id=domain_id,
            top_k=5,
            trace_id=trace_id,
            timeout_ms=3000,
        )
        assert req.top_k == 5

    def test_zero_top_k_rejected(
        self, query_id: QueryId, domain_id: DomainId, trace_id: TraceId
    ) -> None:
        with pytest.raises(ValidationError):
            RecallRequest(
                query_id=query_id,
                query_text="query",
                original_text="query",
                domain_id=domain_id,
                top_k=0,
                trace_id=trace_id,
                timeout_ms=5000,
            )

    def test_zero_timeout_rejected(
        self, query_id: QueryId, domain_id: DomainId, trace_id: TraceId
    ) -> None:
        with pytest.raises(ValidationError):
            RecallRequest(
                query_id=query_id,
                query_text="query",
                original_text="query",
                domain_id=domain_id,
                trace_id=trace_id,
                timeout_ms=0,
            )

    def test_frozen(self, query_id: QueryId, domain_id: DomainId, trace_id: TraceId) -> None:
        req = RecallRequest(
            query_id=query_id,
            query_text="query",
            original_text="query",
            domain_id=domain_id,
            trace_id=trace_id,
            timeout_ms=5000,
        )
        with pytest.raises(ValidationError):
            req.top_k = 10  # type: ignore[misc]

    def test_json_round_trip(
        self, query_id: QueryId, domain_id: DomainId, trace_id: TraceId
    ) -> None:
        req = RecallRequest(
            query_id=query_id,
            query_text="query",
            original_text="query",
            domain_id=domain_id,
            trace_id=trace_id,
            timeout_ms=5000,
        )
        restored = RecallRequest.model_validate_json(req.model_dump_json())
        assert restored == req


class TestIngestRequest:
    def test_valid(self, now: datetime, agent_id: AgentId, trace_id: TraceId) -> None:
        doc = Document(
            id=DocumentId("doc-1"),
            domain_id=DomainId("code"),
            source_path="src/main.py",
            content="code",
            content_hash="hash",
            ingested_at=now,
            source_updated_at=now,
        )
        req = IngestRequest(documents=[doc], agent_id=agent_id, trace_id=trace_id)
        assert len(req.documents) == 1

    def test_empty_documents_rejected(self, agent_id: AgentId, trace_id: TraceId) -> None:
        with pytest.raises(ValidationError):
            IngestRequest(documents=[], agent_id=agent_id, trace_id=trace_id)


class TestQueryRequest:
    def test_defaults(self) -> None:
        req = QueryRequest(query_text="what changed")
        assert req.top_k == 20
        assert req.domains is None
        assert req.filters == {}
        assert req.synthesize is False
        assert req.timeout_ms == 30000

    def test_custom_values(self) -> None:
        req = QueryRequest(
            query_text="payment changes",
            top_k=5,
            domains=[DomainId("code"), DomainId("docs")],
            synthesize=True,
            timeout_ms=10000,
        )
        assert req.top_k == 5
        assert req.domains is not None
        assert len(req.domains) == 2
        assert req.synthesize is True


class TestFuseRequest:
    def test_valid(self, query_id: QueryId, trace_id: TraceId) -> None:
        resp = RecallResponse(
            query_id=query_id,
            agent_id=AgentId("code-memory"),
            domain_id=DomainId("code"),
            total_searched=100,
            latency_ms=200,
            trace_id=trace_id,
        )
        req = FuseRequest(
            query_id=query_id,
            original_text="what changed",
            responses=[resp],
            trace_id=trace_id,
        )
        assert req.conflict_strategy == ConflictStrategy.RECENCY
        assert req.synthesize is False
        assert req.coverage_gaps == []

    def test_with_coverage_gaps(self, query_id: QueryId, trace_id: TraceId) -> None:
        resp = RecallResponse(
            query_id=query_id,
            agent_id=AgentId("code-memory"),
            domain_id=DomainId("code"),
            total_searched=100,
            latency_ms=200,
            trace_id=trace_id,
        )
        gap = CoverageGap(
            domain_id=DomainId("docs"),
            agent_id=AgentId("docs-memory"),
            reason="timeout",
        )
        req = FuseRequest(
            query_id=query_id,
            original_text="what changed",
            responses=[resp],
            coverage_gaps=[gap],
            trace_id=trace_id,
        )
        assert len(req.coverage_gaps) == 1


class TestAgentRegisterRequest:
    def test_valid(self) -> None:
        req = AgentRegisterRequest(
            agent_id=AgentId("code-memory"),
            base_url="http://code-memory:8081",
            health_port=8081,
        )
        assert req.base_url == "http://code-memory:8081"

    def test_invalid_port(self) -> None:
        with pytest.raises(ValidationError):
            AgentRegisterRequest(
                agent_id=AgentId("code-memory"),
                base_url="http://localhost:0",
                health_port=0,
            )

    def test_port_too_high(self) -> None:
        with pytest.raises(ValidationError):
            AgentRegisterRequest(
                agent_id=AgentId("code-memory"),
                base_url="http://localhost:70000",
                health_port=70000,
            )


class TestHeartbeatRequest:
    def test_valid(self) -> None:
        req = HeartbeatRequest(status=AgentStatus.READY)
        assert req.status == AgentStatus.READY

    def test_frozen(self) -> None:
        req = HeartbeatRequest(status=AgentStatus.READY)
        with pytest.raises(ValidationError):
            req.status = AgentStatus.OFFLINE  # type: ignore[misc]
