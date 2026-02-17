"""Tests for typed identifier NewTypes."""

from nornweave_core.models.identifiers import (
    AgentId,
    ChunkId,
    DocumentId,
    DomainId,
    QueryId,
    TraceId,
)


class TestIdentifiers:
    def test_query_id_is_str(self) -> None:
        qid = QueryId("abc-123")
        assert isinstance(qid, str)
        assert qid == "abc-123"

    def test_domain_id_is_str(self) -> None:
        did = DomainId("code")
        assert isinstance(did, str)

    def test_agent_id_is_str(self) -> None:
        aid = AgentId("code-memory")
        assert isinstance(aid, str)

    def test_document_id_is_str(self) -> None:
        did = DocumentId("doc-uuid")
        assert isinstance(did, str)

    def test_chunk_id_is_str(self) -> None:
        cid = ChunkId("chunk-uuid")
        assert isinstance(cid, str)

    def test_trace_id_is_str(self) -> None:
        tid = TraceId("4bf92f3577b34da6")
        assert isinstance(tid, str)

    def test_different_id_types_are_distinct_values(self) -> None:
        q = QueryId("same")
        d = DomainId("same")
        assert q == d  # At runtime, NewType is erased — both are str "same"
