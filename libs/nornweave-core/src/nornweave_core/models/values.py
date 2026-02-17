"""Frozen value objects for the NornWeave domain model."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from nornweave_core.models.identifiers import (
    AgentId,
    ChunkId,
    DocumentId,
    DomainId,
)


class RelevanceScore(BaseModel):
    """A bounded floating-point score (0.0–1.0) representing query relevance."""

    model_config = ConfigDict(frozen=True)

    value: float = Field(ge=0.0, le=1.0)


class EmbeddingVector(BaseModel):
    """A dense vector representation of a chunk or query."""

    model_config = ConfigDict(frozen=True)

    values: list[float]
    dimensions: Literal[384, 768, 1536]
    model_name: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_dimensions(self) -> "EmbeddingVector":
        if len(self.values) != self.dimensions:
            msg = f"Expected {self.dimensions} values, got {len(self.values)}"
            raise ValueError(msg)
        return self


class SourceCitation(BaseModel):
    """Provenance metadata for a recall item."""

    model_config = ConfigDict(frozen=True)

    document_id: DocumentId
    chunk_id: ChunkId
    domain_id: DomainId
    source_path: str
    line_range: tuple[int, int] | None = None
    timestamp: AwareDatetime


class DomainSignal(BaseModel):
    """A routing signal extracted from a query by the router."""

    model_config = ConfigDict(frozen=True)

    domain_id: DomainId
    score: RelevanceScore
    keywords: list[str] = []


class CoverageGap(BaseModel):
    """Annotation indicating a domain could not contribute to a fused response."""

    model_config = ConfigDict(frozen=True)

    domain_id: DomainId
    agent_id: AgentId
    reason: str


class TokenBudget(BaseModel):
    """Token accounting for query analysis and response generation."""

    model_config = ConfigDict(frozen=True)

    limit: int = Field(gt=0)
    consumed: int = Field(ge=0)
    model: str = Field(min_length=1)
