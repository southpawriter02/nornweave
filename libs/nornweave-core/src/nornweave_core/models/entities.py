"""Core entities for the NornWeave domain model."""

from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from nornweave_core.models.enums import AgentStatus, ChunkingStrategy
from nornweave_core.models.identifiers import (
    AgentId,
    ChunkId,
    DocumentId,
    DomainId,
)
from nornweave_core.models.values import EmbeddingVector


class Document(BaseModel):
    """A source document as ingested by a memory agent (pre-chunking)."""

    id: DocumentId
    domain_id: DomainId
    source_path: str
    content: str
    content_hash: str
    metadata: dict[str, Any] = {}
    ingested_at: AwareDatetime
    source_updated_at: AwareDatetime


class Chunk(BaseModel):
    """A segment of a document stored with its embedding — the unit of retrieval."""

    id: ChunkId
    document_id: DocumentId
    domain_id: DomainId
    content: str = Field(min_length=1)
    embedding: EmbeddingVector
    position: int = Field(ge=0)
    token_count: int = Field(gt=0)
    metadata: dict[str, Any] = {}
    created_at: AwareDatetime


class DomainDescriptor(BaseModel):
    """Machine-readable description of a registered domain."""

    model_config = ConfigDict(frozen=True)

    domain_id: DomainId
    name: str
    description: str
    chunking_strategy: ChunkingStrategy
    embedding_model: str
    embedding_dimensions: int
    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    last_ingestion_at: AwareDatetime | None = None


class AgentRegistration(BaseModel):
    """A record of a memory agent in the service registry."""

    agent_id: AgentId
    domain: DomainDescriptor
    base_url: str
    status: AgentStatus = AgentStatus.STARTING
    registered_at: AwareDatetime
    last_heartbeat_at: AwareDatetime
    health_port: int = Field(gt=0, lt=65536)
