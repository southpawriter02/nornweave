"""Tests for Kafka event models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from nornweave_core.models.enums import AgentStatus
from nornweave_core.models.events import AgentLifecycleEvent, IngestionEvent
from nornweave_core.models.identifiers import (
    AgentId,
    DocumentId,
    DomainId,
    TraceId,
)


class TestIngestionEvent:
    def test_valid(
        self,
        now: datetime,
        agent_id: AgentId,
        domain_id: DomainId,
        trace_id: TraceId,
    ) -> None:
        event = IngestionEvent(
            agent_id=agent_id,
            domain_id=domain_id,
            document_ids=[DocumentId("doc-1"), DocumentId("doc-2")],
            chunks_created=15,
            timestamp=now,
            trace_id=trace_id,
        )
        assert len(event.document_ids) == 2
        assert event.chunks_created == 15

    def test_empty_document_ids_rejected(
        self,
        now: datetime,
        agent_id: AgentId,
        domain_id: DomainId,
        trace_id: TraceId,
    ) -> None:
        with pytest.raises(ValidationError):
            IngestionEvent(
                agent_id=agent_id,
                domain_id=domain_id,
                document_ids=[],
                chunks_created=1,
                timestamp=now,
                trace_id=trace_id,
            )

    def test_zero_chunks_rejected(
        self,
        now: datetime,
        agent_id: AgentId,
        domain_id: DomainId,
        trace_id: TraceId,
    ) -> None:
        with pytest.raises(ValidationError):
            IngestionEvent(
                agent_id=agent_id,
                domain_id=domain_id,
                document_ids=[DocumentId("doc-1")],
                chunks_created=0,
                timestamp=now,
                trace_id=trace_id,
            )

    def test_frozen(
        self,
        now: datetime,
        agent_id: AgentId,
        domain_id: DomainId,
        trace_id: TraceId,
    ) -> None:
        event = IngestionEvent(
            agent_id=agent_id,
            domain_id=domain_id,
            document_ids=[DocumentId("doc-1")],
            chunks_created=5,
            timestamp=now,
            trace_id=trace_id,
        )
        with pytest.raises(ValidationError):
            event.chunks_created = 10  # type: ignore[misc]

    def test_json_round_trip(
        self,
        now: datetime,
        agent_id: AgentId,
        domain_id: DomainId,
        trace_id: TraceId,
    ) -> None:
        event = IngestionEvent(
            agent_id=agent_id,
            domain_id=domain_id,
            document_ids=[DocumentId("doc-1")],
            chunks_created=3,
            timestamp=now,
            trace_id=trace_id,
        )
        restored = IngestionEvent.model_validate_json(event.model_dump_json())
        assert restored == event


class TestAgentLifecycleEvent:
    def test_valid(self, now: datetime, agent_id: AgentId) -> None:
        event = AgentLifecycleEvent(
            agent_id=agent_id,
            old_status=AgentStatus.STARTING,
            new_status=AgentStatus.READY,
            timestamp=now,
        )
        assert event.old_status == AgentStatus.STARTING
        assert event.new_status == AgentStatus.READY

    def test_frozen(self, now: datetime, agent_id: AgentId) -> None:
        event = AgentLifecycleEvent(
            agent_id=agent_id,
            old_status=AgentStatus.READY,
            new_status=AgentStatus.DRAINING,
            timestamp=now,
        )
        with pytest.raises(ValidationError):
            event.new_status = AgentStatus.OFFLINE  # type: ignore[misc]

    def test_json_round_trip(self, now: datetime, agent_id: AgentId) -> None:
        event = AgentLifecycleEvent(
            agent_id=agent_id,
            old_status=AgentStatus.READY,
            new_status=AgentStatus.OFFLINE,
            timestamp=now,
        )
        restored = AgentLifecycleEvent.model_validate_json(event.model_dump_json())
        assert restored == event
