"""Kafka event types for cross-agent coordination."""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from nornweave_core.models.enums import AgentStatus
from nornweave_core.models.identifiers import (
    AgentId,
    DocumentId,
    DomainId,
    TraceId,
)


class IngestionEvent(BaseModel):
    """Published by a memory agent after successfully indexing new documents."""

    model_config = ConfigDict(frozen=True)

    agent_id: AgentId
    domain_id: DomainId
    document_ids: list[DocumentId] = Field(min_length=1)
    chunks_created: int = Field(gt=0)
    timestamp: AwareDatetime
    trace_id: TraceId


class AgentLifecycleEvent(BaseModel):
    """Published when an agent's status changes."""

    model_config = ConfigDict(frozen=True)

    agent_id: AgentId
    old_status: AgentStatus
    new_status: AgentStatus
    timestamp: AwareDatetime
