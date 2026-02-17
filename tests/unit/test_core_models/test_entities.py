"""Tests for core entities (Document, Chunk, DomainDescriptor, AgentRegistration)."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from nornweave_core.models.entities import (
    AgentRegistration,
    Chunk,
    Document,
    DomainDescriptor,
)
from nornweave_core.models.enums import AgentStatus, ChunkingStrategy
from nornweave_core.models.identifiers import (
    AgentId,
    ChunkId,
    DocumentId,
    DomainId,
)
from nornweave_core.models.values import EmbeddingVector


@pytest.fixture
def sample_document(now: datetime, document_id: DocumentId, domain_id: DomainId) -> Document:
    return Document(
        id=document_id,
        domain_id=domain_id,
        source_path="src/main.py",
        content="def main(): pass",
        content_hash="abc123def456",
        ingested_at=now,
        source_updated_at=now,
    )


@pytest.fixture
def sample_embedding() -> EmbeddingVector:
    return EmbeddingVector(values=[0.1] * 384, dimensions=384, model_name="test-model")


@pytest.fixture
def sample_descriptor(domain_id: DomainId) -> DomainDescriptor:
    return DomainDescriptor(
        domain_id=domain_id,
        name="Source Code",
        description="Application source code",
        chunking_strategy=ChunkingStrategy.SYNTAX_AWARE,
        embedding_model="codebert",
        embedding_dimensions=768,
        document_count=100,
        chunk_count=5000,
    )


class TestDocument:
    def test_valid(self, sample_document: Document) -> None:
        assert sample_document.source_path == "src/main.py"
        assert sample_document.metadata == {}

    def test_with_metadata(self, now: datetime) -> None:
        doc = Document(
            id=DocumentId("doc-1"),
            domain_id=DomainId("code"),
            source_path="src/main.py",
            content="code",
            content_hash="hash",
            metadata={"language": "python"},
            ingested_at=now,
            source_updated_at=now,
        )
        assert doc.metadata == {"language": "python"}

    def test_mutable(self, sample_document: Document) -> None:
        sample_document.source_path = "src/other.py"
        assert sample_document.source_path == "src/other.py"

    def test_json_round_trip(self, sample_document: Document) -> None:
        restored = Document.model_validate_json(sample_document.model_dump_json())
        assert restored == sample_document


class TestChunk:
    def test_valid(
        self,
        now: datetime,
        chunk_id: ChunkId,
        document_id: DocumentId,
        domain_id: DomainId,
        sample_embedding: EmbeddingVector,
    ) -> None:
        c = Chunk(
            id=chunk_id,
            document_id=document_id,
            domain_id=domain_id,
            content="some code",
            embedding=sample_embedding,
            position=0,
            token_count=5,
            created_at=now,
        )
        assert c.position == 0
        assert c.token_count == 5

    def test_empty_content_rejected(
        self,
        now: datetime,
        chunk_id: ChunkId,
        document_id: DocumentId,
        domain_id: DomainId,
        sample_embedding: EmbeddingVector,
    ) -> None:
        with pytest.raises(ValidationError):
            Chunk(
                id=chunk_id,
                document_id=document_id,
                domain_id=domain_id,
                content="",
                embedding=sample_embedding,
                position=0,
                token_count=1,
                created_at=now,
            )

    def test_zero_token_count_rejected(
        self,
        now: datetime,
        chunk_id: ChunkId,
        document_id: DocumentId,
        domain_id: DomainId,
        sample_embedding: EmbeddingVector,
    ) -> None:
        with pytest.raises(ValidationError):
            Chunk(
                id=chunk_id,
                document_id=document_id,
                domain_id=domain_id,
                content="code",
                embedding=sample_embedding,
                position=0,
                token_count=0,
                created_at=now,
            )

    def test_negative_position_rejected(
        self,
        now: datetime,
        chunk_id: ChunkId,
        document_id: DocumentId,
        domain_id: DomainId,
        sample_embedding: EmbeddingVector,
    ) -> None:
        with pytest.raises(ValidationError):
            Chunk(
                id=chunk_id,
                document_id=document_id,
                domain_id=domain_id,
                content="code",
                embedding=sample_embedding,
                position=-1,
                token_count=1,
                created_at=now,
            )

    def test_mutable(
        self,
        now: datetime,
        chunk_id: ChunkId,
        document_id: DocumentId,
        domain_id: DomainId,
        sample_embedding: EmbeddingVector,
    ) -> None:
        c = Chunk(
            id=chunk_id,
            document_id=document_id,
            domain_id=domain_id,
            content="old",
            embedding=sample_embedding,
            position=0,
            token_count=1,
            created_at=now,
        )
        c.content = "new"
        assert c.content == "new"


class TestDomainDescriptor:
    def test_valid(self, sample_descriptor: DomainDescriptor) -> None:
        assert sample_descriptor.name == "Source Code"
        assert sample_descriptor.last_ingestion_at is None

    def test_with_last_ingestion(self, now: datetime, domain_id: DomainId) -> None:
        d = DomainDescriptor(
            domain_id=domain_id,
            name="Code",
            description="desc",
            chunking_strategy=ChunkingStrategy.SYNTAX_AWARE,
            embedding_model="model",
            embedding_dimensions=768,
            document_count=0,
            chunk_count=0,
            last_ingestion_at=now,
        )
        assert d.last_ingestion_at == now

    def test_frozen(self, sample_descriptor: DomainDescriptor) -> None:
        with pytest.raises(ValidationError):
            sample_descriptor.name = "Other"  # type: ignore[misc]

    def test_negative_counts_rejected(self, domain_id: DomainId) -> None:
        with pytest.raises(ValidationError):
            DomainDescriptor(
                domain_id=domain_id,
                name="Code",
                description="desc",
                chunking_strategy=ChunkingStrategy.SYNTAX_AWARE,
                embedding_model="model",
                embedding_dimensions=768,
                document_count=-1,
                chunk_count=0,
            )

    def test_json_round_trip(self, sample_descriptor: DomainDescriptor) -> None:
        restored = DomainDescriptor.model_validate_json(sample_descriptor.model_dump_json())
        assert restored == sample_descriptor


class TestAgentRegistration:
    def test_valid(
        self,
        now: datetime,
        agent_id: AgentId,
        sample_descriptor: DomainDescriptor,
    ) -> None:
        reg = AgentRegistration(
            agent_id=agent_id,
            domain=sample_descriptor,
            base_url="http://code-memory:8081",
            registered_at=now,
            last_heartbeat_at=now,
            health_port=8081,
        )
        assert reg.status == AgentStatus.STARTING
        assert reg.health_port == 8081

    def test_default_status_is_starting(
        self,
        now: datetime,
        agent_id: AgentId,
        sample_descriptor: DomainDescriptor,
    ) -> None:
        reg = AgentRegistration(
            agent_id=agent_id,
            domain=sample_descriptor,
            base_url="http://localhost:8081",
            registered_at=now,
            last_heartbeat_at=now,
            health_port=8081,
        )
        assert reg.status == AgentStatus.STARTING

    def test_mutable(
        self,
        now: datetime,
        agent_id: AgentId,
        sample_descriptor: DomainDescriptor,
    ) -> None:
        reg = AgentRegistration(
            agent_id=agent_id,
            domain=sample_descriptor,
            base_url="http://localhost:8081",
            registered_at=now,
            last_heartbeat_at=now,
            health_port=8081,
        )
        reg.status = AgentStatus.READY
        assert reg.status == AgentStatus.READY

    def test_invalid_port(
        self,
        now: datetime,
        agent_id: AgentId,
        sample_descriptor: DomainDescriptor,
    ) -> None:
        with pytest.raises(ValidationError):
            AgentRegistration(
                agent_id=agent_id,
                domain=sample_descriptor,
                base_url="http://localhost:0",
                registered_at=now,
                last_heartbeat_at=now,
                health_port=0,
            )

    def test_json_round_trip(
        self,
        now: datetime,
        agent_id: AgentId,
        sample_descriptor: DomainDescriptor,
    ) -> None:
        reg = AgentRegistration(
            agent_id=agent_id,
            domain=sample_descriptor,
            base_url="http://code-memory:8081",
            registered_at=now,
            last_heartbeat_at=now,
            health_port=8081,
        )
        restored = AgentRegistration.model_validate_json(reg.model_dump_json())
        assert restored == reg
