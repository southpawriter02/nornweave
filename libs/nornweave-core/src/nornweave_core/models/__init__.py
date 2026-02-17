"""NornWeave domain model — re-exports all public types."""

from nornweave_core.models.entities import (
    AgentRegistration,
    Chunk,
    Document,
    DomainDescriptor,
)
from nornweave_core.models.enums import (
    AgentStatus,
    ChunkingStrategy,
    ConflictStrategy,
    DomainType,
    IngestStatus,
)
from nornweave_core.models.events import (
    AgentLifecycleEvent,
    IngestionEvent,
)
from nornweave_core.models.identifiers import (
    AgentId,
    ChunkId,
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
from nornweave_core.models.responses import (
    AgentListResponse,
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
    CoverageGap,
    DomainSignal,
    EmbeddingVector,
    RelevanceScore,
    SourceCitation,
    TokenBudget,
)

# Resolve forward reference for AgentListResponse -> AgentRegistration
AgentListResponse.model_rebuild()

__all__ = [
    # Identifiers
    "AgentId",
    "ChunkId",
    "DocumentId",
    "DomainId",
    "QueryId",
    "TraceId",
    # Enums
    "AgentStatus",
    "ChunkingStrategy",
    "ConflictStrategy",
    "DomainType",
    "IngestStatus",
    # Value Objects
    "CoverageGap",
    "DomainSignal",
    "EmbeddingVector",
    "RelevanceScore",
    "SourceCitation",
    "TokenBudget",
    # Entities
    "AgentRegistration",
    "Chunk",
    "Document",
    "DomainDescriptor",
    # Responses
    "AgentListResponse",
    "ConflictRecord",
    "DocumentIngestStatus",
    "ErrorDetail",
    "ErrorResponse",
    "FusionResult",
    "HealthStatus",
    "HeartbeatResponse",
    "IngestResult",
    "RecallItem",
    "RecallResponse",
    "RoutingPlan",
    "RoutingTarget",
    # Requests
    "AgentRegisterRequest",
    "FuseRequest",
    "HeartbeatRequest",
    "IngestRequest",
    "QueryRequest",
    "RecallRequest",
    # Events
    "AgentLifecycleEvent",
    "IngestionEvent",
]
