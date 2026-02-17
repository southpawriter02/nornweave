"""Request models for the NornWeave mesh APIs."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from nornweave_core.models.entities import Document
from nornweave_core.models.enums import AgentStatus, ConflictStrategy
from nornweave_core.models.identifiers import (
    AgentId,
    DomainId,
    QueryId,
    TraceId,
)
from nornweave_core.models.responses import RecallResponse
from nornweave_core.models.values import CoverageGap


class RecallRequest(BaseModel):
    """Sent from the router to a memory agent with query and routing context."""

    model_config = ConfigDict(frozen=True)

    query_id: QueryId
    query_text: str
    original_text: str
    domain_id: DomainId
    top_k: int = Field(default=20, gt=0)
    filters: dict[str, Any] = {}
    trace_id: TraceId
    timeout_ms: int = Field(gt=0)


class IngestRequest(BaseModel):
    """Submitted to a memory agent to add new documents."""

    model_config = ConfigDict(frozen=True)

    documents: list[Document] = Field(min_length=1)
    agent_id: AgentId
    trace_id: TraceId


class QueryRequest(BaseModel):
    """Client-facing query submitted to the router (POST /query)."""

    model_config = ConfigDict(frozen=True)

    query_text: str
    top_k: int = Field(default=20, gt=0)
    domains: list[DomainId] | None = None
    filters: dict[str, Any] = {}
    synthesize: bool = False
    timeout_ms: int = Field(default=30000, gt=0)


class FuseRequest(BaseModel):
    """Sent to the fusion service to execute the six-stage pipeline (POST /fuse)."""

    model_config = ConfigDict(frozen=True)

    query_id: QueryId
    original_text: str
    responses: list[RecallResponse]
    coverage_gaps: list[CoverageGap] = []
    conflict_strategy: ConflictStrategy = ConflictStrategy.RECENCY
    synthesize: bool = False
    trace_id: TraceId


class AgentRegisterRequest(BaseModel):
    """Submitted to the registry to register a new memory agent."""

    model_config = ConfigDict(frozen=True)

    agent_id: AgentId
    base_url: str
    health_port: int = Field(gt=0, lt=65536)


class HeartbeatRequest(BaseModel):
    """Submitted to update an agent's heartbeat (POST /agents/{id}/heartbeat)."""

    model_config = ConfigDict(frozen=True)

    status: AgentStatus
