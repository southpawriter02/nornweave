"""Typed identifiers — NewType wrappers over str to prevent stringly-typed bugs."""

from typing import NewType

QueryId = NewType("QueryId", str)
DomainId = NewType("DomainId", str)
AgentId = NewType("AgentId", str)
DocumentId = NewType("DocumentId", str)
ChunkId = NewType("ChunkId", str)
TraceId = NewType("TraceId", str)
