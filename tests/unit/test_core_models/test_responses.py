"""Tests for response models including RecallItem and ConflictRecord."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from nornweave_core.models.enums import AgentStatus, ConflictStrategy, IngestStatus
from nornweave_core.models.identifiers import (
    AgentId,
    ChunkId,
    DocumentId,
    DomainId,
    QueryId,
    TraceId,
)
from nornweave_core.models.responses import (
    ConflictRecord,
    DocumentIngestStatus,
    ErrorDetail,
    ErrorResponse,
    FusionResult,
    HealthStatus,
    HeartbeatResponse,
    IngestResult,
    RecallItem,
    RecallResponse,
    RoutingPlan,
    RoutingTarget,
)
from nornweave_core.models.values import (
    RelevanceScore,
    SourceCitation,
)


@pytest.fixture
def sample_citation(now: datetime) -> SourceCitation:
    return SourceCitation(
        document_id=DocumentId("doc-1"),
        chunk_id=ChunkId("chunk-1"),
        domain_id=DomainId("code"),
        source_path="src/main.py",
        timestamp=now,
    )


@pytest.fixture
def sample_recall_item(sample_citation: SourceCitation) -> RecallItem:
    return RecallItem(
        chunk_id="chunk-1",
        content="def main(): pass",
        score=RelevanceScore(value=0.9),
        citation=sample_citation,
    )


class TestRecallItem:
    def test_valid(self, sample_recall_item: RecallItem) -> None:
        assert sample_recall_item.content == "def main(): pass"
        assert sample_recall_item.metadata == {}

    def test_with_metadata(self, sample_citation: SourceCitation) -> None:
        item = RecallItem(
            chunk_id="chunk-1",
            content="code",
            score=RelevanceScore(value=0.5),
            citation=sample_citation,
            metadata={"language": "python"},
        )
        assert item.metadata == {"language": "python"}

    def test_frozen(self, sample_recall_item: RecallItem) -> None:
        with pytest.raises(ValidationError):
            sample_recall_item.content = "other"  # type: ignore[misc]

    def test_json_round_trip(self, sample_recall_item: RecallItem) -> None:
        restored = RecallItem.model_validate_json(sample_recall_item.model_dump_json())
        assert restored == sample_recall_item


class TestConflictRecord:
    def test_valid(self, sample_recall_item: RecallItem) -> None:
        item2 = sample_recall_item.model_copy(update={"chunk_id": "chunk-2"})
        cr = ConflictRecord(
            items=[sample_recall_item, item2],
            resolution=ConflictStrategy.RECENCY,
            resolved_to=sample_recall_item,
        )
        assert len(cr.items) == 2
        assert cr.resolved_to is not None

    def test_flagged_no_resolution(self, sample_recall_item: RecallItem) -> None:
        item2 = sample_recall_item.model_copy(update={"chunk_id": "chunk-2"})
        cr = ConflictRecord(
            items=[sample_recall_item, item2],
            resolution=ConflictStrategy.FLAG,
        )
        assert cr.resolved_to is None

    def test_min_two_items(self, sample_recall_item: RecallItem) -> None:
        with pytest.raises(ValidationError):
            ConflictRecord(
                items=[sample_recall_item],
                resolution=ConflictStrategy.RECENCY,
            )

    def test_frozen(self, sample_recall_item: RecallItem) -> None:
        item2 = sample_recall_item.model_copy(update={"chunk_id": "chunk-2"})
        cr = ConflictRecord(
            items=[sample_recall_item, item2],
            resolution=ConflictStrategy.RECENCY,
        )
        with pytest.raises(ValidationError):
            cr.resolution = ConflictStrategy.FLAG  # type: ignore[misc]


class TestRecallResponse:
    def test_valid(
        self,
        query_id: QueryId,
        agent_id: AgentId,
        domain_id: DomainId,
        trace_id: TraceId,
        sample_recall_item: RecallItem,
    ) -> None:
        resp = RecallResponse(
            query_id=query_id,
            agent_id=agent_id,
            domain_id=domain_id,
            items=[sample_recall_item],
            total_searched=100,
            latency_ms=42,
            trace_id=trace_id,
        )
        assert len(resp.items) == 1
        assert resp.total_searched == 100

    def test_empty_items(
        self,
        query_id: QueryId,
        agent_id: AgentId,
        domain_id: DomainId,
        trace_id: TraceId,
    ) -> None:
        resp = RecallResponse(
            query_id=query_id,
            agent_id=agent_id,
            domain_id=domain_id,
            items=[],
            total_searched=50,
            latency_ms=10,
            trace_id=trace_id,
        )
        assert resp.items == []

    def test_frozen(
        self,
        query_id: QueryId,
        agent_id: AgentId,
        domain_id: DomainId,
        trace_id: TraceId,
    ) -> None:
        resp = RecallResponse(
            query_id=query_id,
            agent_id=agent_id,
            domain_id=domain_id,
            total_searched=0,
            latency_ms=0,
            trace_id=trace_id,
        )
        with pytest.raises(ValidationError):
            resp.latency_ms = 999  # type: ignore[misc]


class TestRoutingTarget:
    def test_valid(self) -> None:
        t = RoutingTarget(
            domain_id=DomainId("code"),
            agent_id=AgentId("code-memory"),
            relevance=RelevanceScore(value=0.95),
        )
        assert t.rewritten_query is None

    def test_with_rewrite(self) -> None:
        t = RoutingTarget(
            domain_id=DomainId("code"),
            agent_id=AgentId("code-memory"),
            relevance=RelevanceScore(value=0.8),
            rewritten_query="payment error handling",
        )
        assert t.rewritten_query == "payment error handling"


class TestRoutingPlan:
    def test_valid(self, now: datetime, query_id: QueryId, trace_id: TraceId) -> None:
        target = RoutingTarget(
            domain_id=DomainId("code"),
            agent_id=AgentId("code-memory"),
            relevance=RelevanceScore(value=0.9),
        )
        plan = RoutingPlan(
            query_id=query_id,
            original_text="what changed",
            targets=[target],
            created_at=now,
            trace_id=trace_id,
        )
        assert len(plan.targets) == 1
        assert plan.signals == []

    def test_empty_targets_rejected(
        self, now: datetime, query_id: QueryId, trace_id: TraceId
    ) -> None:
        with pytest.raises(ValidationError):
            RoutingPlan(
                query_id=query_id,
                original_text="query",
                targets=[],
                created_at=now,
                trace_id=trace_id,
            )


class TestDocumentIngestStatus:
    def test_accepted(self) -> None:
        s = DocumentIngestStatus(
            document_id=DocumentId("doc-1"),
            status=IngestStatus.ACCEPTED,
            chunks_created=0,
        )
        assert s.error is None

    def test_failed_with_error(self) -> None:
        s = DocumentIngestStatus(
            document_id=DocumentId("doc-1"),
            status=IngestStatus.FAILED,
            chunks_created=0,
            error="Embedding model timeout",
        )
        assert s.error == "Embedding model timeout"


class TestIngestResult:
    def test_valid(self, agent_id: AgentId, domain_id: DomainId, trace_id: TraceId) -> None:
        status = DocumentIngestStatus(
            document_id=DocumentId("doc-1"),
            status=IngestStatus.ACCEPTED,
            chunks_created=0,
        )
        result = IngestResult(
            agent_id=agent_id,
            domain_id=domain_id,
            results=[status],
            trace_id=trace_id,
        )
        assert len(result.results) == 1

    def test_empty_results_rejected(
        self, agent_id: AgentId, domain_id: DomainId, trace_id: TraceId
    ) -> None:
        with pytest.raises(ValidationError):
            IngestResult(
                agent_id=agent_id,
                domain_id=domain_id,
                results=[],
                trace_id=trace_id,
            )


class TestFusionResult:
    def test_valid(
        self,
        query_id: QueryId,
        domain_id: DomainId,
        trace_id: TraceId,
        sample_recall_item: RecallItem,
    ) -> None:
        result = FusionResult(
            query_id=query_id,
            items=[sample_recall_item],
            domains_queried=[domain_id],
            total_latency_ms=4200,
            trace_id=trace_id,
        )
        assert result.synthesis is None
        assert result.conflicts == []
        assert result.coverage_gaps == []

    def test_empty_domains_rejected(self, query_id: QueryId, trace_id: TraceId) -> None:
        with pytest.raises(ValidationError):
            FusionResult(
                query_id=query_id,
                items=[],
                domains_queried=[],
                total_latency_ms=0,
                trace_id=trace_id,
            )


class TestHealthStatus:
    def test_valid(self) -> None:
        h = HealthStatus(
            service_name="code-memory",
            status=AgentStatus.READY,
            uptime_seconds=3847.2,
            checks={"db": True, "model": True},
        )
        assert h.index_size is None
        assert h.last_ingest_at is None

    def test_with_optional_fields(self, now: datetime) -> None:
        h = HealthStatus(
            service_name="code-memory",
            status=AgentStatus.READY,
            uptime_seconds=100.0,
            index_size=42531,
            last_ingest_at=now,
            checks={"db": True},
        )
        assert h.index_size == 42531


class TestErrorDetail:
    def test_valid(self, now: datetime, trace_id: TraceId) -> None:
        e = ErrorDetail(
            code="AGENT_TIMEOUT",
            message="Agent did not respond",
            trace_id=trace_id,
            timestamp=now,
        )
        assert e.details is None

    def test_with_details(self, now: datetime, trace_id: TraceId) -> None:
        e = ErrorDetail(
            code="AGENT_TIMEOUT",
            message="Agent did not respond",
            details={"agent_id": "code-memory", "timeout_ms": 5000},
            trace_id=trace_id,
            timestamp=now,
        )
        assert e.details is not None


class TestErrorResponse:
    def test_valid(self, now: datetime, trace_id: TraceId) -> None:
        detail = ErrorDetail(
            code="INTERNAL_ERROR",
            message="Something went wrong",
            trace_id=trace_id,
            timestamp=now,
        )
        resp = ErrorResponse(error=detail)
        assert resp.error.code == "INTERNAL_ERROR"


class TestHeartbeatResponse:
    def test_valid(self, now: datetime, agent_id: AgentId) -> None:
        h = HeartbeatResponse(
            agent_id=agent_id,
            status=AgentStatus.READY,
            last_heartbeat_at=now,
        )
        assert h.status == AgentStatus.READY
