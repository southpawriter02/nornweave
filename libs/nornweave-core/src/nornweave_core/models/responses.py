"""Response models and shared types (RecallItem, ConflictRecord) for the NornWeave mesh."""

from typing import TYPE_CHECKING, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from nornweave_core.models.enums import AgentStatus, ConflictStrategy, IngestStatus
from nornweave_core.models.identifiers import (
    AgentId,
    DocumentId,
    DomainId,
    QueryId,
    TraceId,
)
from nornweave_core.models.values import (
    CoverageGap,
    DomainSignal,
    RelevanceScore,
    SourceCitation,
)

if TYPE_CHECKING:
    from nornweave_core.models.entities import AgentRegistration


class RecallItem(BaseModel):
    """A single result from a memory agent — the atomic unit of information."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str  # ChunkId (NewType over str)
    content: str
    score: RelevanceScore
    citation: SourceCitation
    metadata: dict[str, Any] = {}


class ConflictRecord(BaseModel):
    """A record of contradictory information detected during fusion."""

    model_config = ConfigDict(frozen=True)

    items: list[RecallItem] = Field(min_length=2)
    resolution: ConflictStrategy
    resolved_to: RecallItem | None = None


class RecallResponse(BaseModel):
    """Returned by a memory agent with ranked results and metadata."""

    model_config = ConfigDict(frozen=True)

    query_id: QueryId
    agent_id: AgentId
    domain_id: DomainId
    items: list[RecallItem] = []
    total_searched: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    trace_id: TraceId


class RoutingTarget(BaseModel):
    """A single entry in a routing plan — pairs a domain with an optional query rewrite."""

    model_config = ConfigDict(frozen=True)

    domain_id: DomainId
    agent_id: AgentId
    relevance: RelevanceScore
    rewritten_query: str | None = None


class RoutingPlan(BaseModel):
    """The output of the router agent describing which domains receive the query."""

    model_config = ConfigDict(frozen=True)

    query_id: QueryId
    original_text: str
    targets: list[RoutingTarget] = Field(min_length=1)
    signals: list[DomainSignal] = []
    created_at: AwareDatetime
    trace_id: TraceId


class DocumentIngestStatus(BaseModel):
    """Per-document outcome of an ingestion attempt."""

    model_config = ConfigDict(frozen=True)

    document_id: DocumentId
    status: IngestStatus
    chunks_created: int = Field(ge=0)
    error: str | None = None


class IngestResult(BaseModel):
    """Returned by a memory agent after processing an ingestion request."""

    model_config = ConfigDict(frozen=True)

    agent_id: AgentId
    domain_id: DomainId
    results: list[DocumentIngestStatus] = Field(min_length=1)
    trace_id: TraceId


class FusionResult(BaseModel):
    """The final output of the response fusion pipeline."""

    model_config = ConfigDict(frozen=True)

    query_id: QueryId
    items: list[RecallItem] = []
    synthesis: str | None = None
    conflicts: list[ConflictRecord] = []
    coverage_gaps: list[CoverageGap] = []
    domains_queried: list[DomainId] = Field(min_length=1)
    total_latency_ms: int = Field(ge=0)
    trace_id: TraceId


class HealthStatus(BaseModel):
    """Returned by every service's /health and /ready endpoints."""

    model_config = ConfigDict(frozen=True)

    service_name: str
    status: AgentStatus
    uptime_seconds: float = Field(ge=0)
    index_size: int | None = None
    last_ingest_at: AwareDatetime | None = None
    checks: dict[str, bool]


class ErrorDetail(BaseModel):
    """Machine-readable error information."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    details: dict[str, Any] | None = None
    trace_id: TraceId
    timestamp: AwareDatetime


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    model_config = ConfigDict(frozen=True)

    error: ErrorDetail


class AgentListResponse(BaseModel):
    """Response for GET /agents listing all registered agents."""

    model_config = ConfigDict(frozen=True)

    agents: list["AgentRegistration"]
    total: int = Field(ge=0)


class HeartbeatResponse(BaseModel):
    """Response for POST /agents/{agent_id}/heartbeat."""

    model_config = ConfigDict(frozen=True)

    agent_id: AgentId
    status: AgentStatus
    last_heartbeat_at: AwareDatetime
