"""Domain enumerations for the NornWeave mesh."""

from enum import StrEnum


class DomainType(StrEnum):
    """Default domain categories for knowledge partitioning."""

    CODE = "CODE"
    DOCUMENTATION = "DOCUMENTATION"
    CONVERSATIONS = "CONVERSATIONS"
    RESEARCH = "RESEARCH"


class AgentStatus(StrEnum):
    """Lifecycle state of a registered memory agent."""

    STARTING = "STARTING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    DRAINING = "DRAINING"
    OFFLINE = "OFFLINE"


class ConflictStrategy(StrEnum):
    """How the fusion layer resolves contradictions between agents."""

    RECENCY = "RECENCY"
    SOURCE_AUTHORITY = "SOURCE_AUTHORITY"
    CONFIDENCE = "CONFIDENCE"
    FLAG = "FLAG"
    RECENCY_THEN_FLAG = "RECENCY_THEN_FLAG"


class ChunkingStrategy(StrEnum):
    """How a memory agent segments documents for storage."""

    SYNTAX_AWARE = "SYNTAX_AWARE"
    HIERARCHICAL_SECTIONS = "HIERARCHICAL_SECTIONS"
    MESSAGE_BOUNDARY = "MESSAGE_BOUNDARY"
    RECURSIVE_CHARACTER = "RECURSIVE_CHARACTER"


class IngestStatus(StrEnum):
    """Outcome of a document ingestion attempt."""

    ACCEPTED = "ACCEPTED"
    INDEXED = "INDEXED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
