"""JSON Schema export tests — every model must produce valid JSON Schema."""

import pytest

from nornweave_core.models.entities import (
    AgentRegistration,
    Chunk,
    Document,
    DomainDescriptor,
)
from nornweave_core.models.events import AgentLifecycleEvent, IngestionEvent
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

ALL_MODELS = [
    RelevanceScore,
    EmbeddingVector,
    SourceCitation,
    DomainSignal,
    CoverageGap,
    TokenBudget,
    Document,
    Chunk,
    DomainDescriptor,
    AgentRegistration,
    RecallItem,
    ConflictRecord,
    RecallResponse,
    RoutingTarget,
    RoutingPlan,
    DocumentIngestStatus,
    IngestResult,
    FusionResult,
    HealthStatus,
    ErrorDetail,
    ErrorResponse,
    AgentListResponse,
    HeartbeatResponse,
    RecallRequest,
    IngestRequest,
    QueryRequest,
    FuseRequest,
    AgentRegisterRequest,
    HeartbeatRequest,
    IngestionEvent,
    AgentLifecycleEvent,
]


@pytest.mark.parametrize("model_cls", ALL_MODELS, ids=lambda m: m.__name__)
def test_model_json_schema(model_cls: type) -> None:
    schema = model_cls.model_json_schema()
    assert isinstance(schema, dict)
    assert "properties" in schema or "$defs" in schema
    assert "title" in schema
    assert schema["title"] == model_cls.__name__
