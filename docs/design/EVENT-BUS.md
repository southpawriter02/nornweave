# NornWeave — Event Bus & Cross-Agent Communication

> Design specification for asynchronous inter-service communication via Kafka. Covers topic architecture, event schemas, producer/consumer patterns, ordering guarantees, error handling, and observability. References the [Domain Model](DOMAIN-MODEL.md) for event types and [Service Contracts](SERVICE-CONTRACTS.md) for the synchronous API surface.

---

## Table of Contents

- [Communication Model](#communication-model)
- [Kafka Cluster Configuration](#kafka-cluster-configuration)
- [Topic Architecture](#topic-architecture)
  - [nornweave.ingestion.events](#nornweaveingestionevents)
  - [nornweave.agent.lifecycle](#nornweaveagentlifecycle)
  - [nornweave.routing.feedback](#nornwaveroutingfeedback)
  - [nornweave.dlq](#nornweavedlq)
- [Event Schemas](#event-schemas)
  - [Envelope Format](#envelope-format)
  - [IngestionEvent](#ingestionevent)
  - [AgentLifecycleEvent](#agentlifecycleevent)
  - [RoutingFeedbackEvent](#routingfeedbackevent)
- [Producer Patterns](#producer-patterns)
- [Consumer Patterns](#consumer-patterns)
- [Exactly-Once Semantics](#exactly-once-semantics)
- [Error Handling & Dead Letter Queue](#error-handling--dead-letter-queue)
- [Observability](#observability)
- [Communication Flow Diagrams](#communication-flow-diagrams)
- [Configuration](#configuration)
- [Internal Architecture](#internal-architecture)

---

## Communication Model

NornWeave uses two communication channels:

| Channel          | Technology | Use Case                                     | Coupling  |
| ---------------- | ---------- | -------------------------------------------- | --------- |
| **Synchronous**  | HTTP/JSON  | Query pipeline (router → agents → fusion)    | Temporal  |
| **Asynchronous** | Kafka      | State changes, notifications, feedback loops | Decoupled |

**When to use which:**

```
Is the caller blocked until the receiver responds?
  │
  YES ──▶ HTTP  (recall, ingest, fuse, health, describe)
  │
  NO  ──▶ Kafka (ingestion completed, agent status changed, routing feedback)
```

**Design rule:** The query pipeline (the hot path) is entirely synchronous. Kafka handles everything that can happen asynchronously: lifecycle notifications, index-update advisories, and feedback loops for adaptive routing.

---

## Kafka Cluster Configuration

**Development (Docker Compose):**

Single-broker Kafka via the `bitnami/kafka` image (KRaft mode, no ZooKeeper).

```yaml
# docker-compose.yml (excerpt)
kafka:
  image: bitnami/kafka:3.7
  environment:
    KAFKA_CFG_NODE_ID: 0
    KAFKA_CFG_PROCESS_ROLES: broker,controller
    KAFKA_CFG_CONTROLLER_QUORUM_VOTERS: "0@kafka:9093"
    KAFKA_CFG_LISTENERS: "PLAINTEXT://:9092,CONTROLLER://:9093"
    KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP: "PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT"
    KAFKA_CFG_INTER_BROKER_LISTENER_NAME: PLAINTEXT
    KAFKA_CFG_CONTROLLER_LISTENER_NAMES: CONTROLLER
    KAFKA_CFG_AUTO_CREATE_TOPICS_ENABLE: "false"
  ports:
    - "9092:9092"
```

**Production:** Multi-broker cluster (minimum 3 brokers for `replication-factor=3`). Configuration is deployment-specific and outside the scope of this spec.

**Topic creation (init script):**

```bash
#!/usr/bin/env bash
# scripts/create-topics.sh

KAFKA_BROKER="${KAFKA_BOOTSTRAP:-kafka:9092}"

kafka-topics.sh --bootstrap-server "$KAFKA_BROKER" --create \
  --topic nornweave.ingestion.events \
  --partitions 4 \
  --replication-factor 1 \
  --config retention.ms=604800000 \
  --config cleanup.policy=delete

kafka-topics.sh --bootstrap-server "$KAFKA_BROKER" --create \
  --topic nornweave.agent.lifecycle \
  --partitions 1 \
  --replication-factor 1 \
  --config retention.ms=259200000 \
  --config cleanup.policy=delete

kafka-topics.sh --bootstrap-server "$KAFKA_BROKER" --create \
  --topic nornweave.routing.feedback \
  --partitions 4 \
  --replication-factor 1 \
  --config retention.ms=604800000 \
  --config cleanup.policy=delete

kafka-topics.sh --bootstrap-server "$KAFKA_BROKER" --create \
  --topic nornweave.dlq \
  --partitions 1 \
  --replication-factor 1 \
  --config retention.ms=2592000000 \
  --config cleanup.policy=delete
```

---

## Topic Architecture

### Overview

| Topic                        | Partitions | Retention | Partition Key  | Producers      | Consumers        |
| ---------------------------- | ---------- | --------- | -------------- | -------------- | ---------------- |
| `nornweave.ingestion.events` | 4          | 7 days    | `domain_id`    | Memory Agents  | Registry, Router |
| `nornweave.agent.lifecycle`  | 1          | 3 days    | `agent_id`     | Memory Agents  | Registry, Router |
| `nornweave.routing.feedback` | 4          | 7 days    | `query_id`     | Fusion Service | Router           |
| `nornweave.dlq`              | 1          | 30 days   | original topic | All consumers  | Ops / alerting   |

### nornweave.ingestion.events

**Purpose:** Notify the system that a memory agent has finished indexing new documents. Advisory in nature; consumers use this for cache invalidation and statistics, not for correctness.

**Partition key:** `domain_id` — ensures all events for a given domain land on the same partition, preserving per-domain ordering.

**Producers:** Every memory agent, after step 6 of the ingestion pipeline.

**Consumers:**

| Consumer         | Reaction                                                            |
| ---------------- | ------------------------------------------------------------------- |
| Service Registry | Update `AgentRegistration.domain.document_count` and `chunk_count`  |
| Router           | Refresh cached `DomainDescriptor` (optional, accelerates discovery) |

### nornweave.agent.lifecycle

**Purpose:** Broadcast agent status transitions. The registry is the authoritative consumer; the router uses these for rapid cache invalidation.

**Partition key:** `agent_id` — ensures all lifecycle events for one agent are ordered on the same partition.

**Partitions:** 1. Lifecycle events are low-volume and order matters globally (e.g., the registry needs to process `STARTING → READY → DEGRADED` in sequence). A single partition guarantees total order.

**Producers:** Every memory agent, on status transitions.

**Consumers:**

| Consumer         | Reaction                                                 |
| ---------------- | -------------------------------------------------------- |
| Service Registry | Update `AgentRegistration.status`, publish health alerts |
| Router           | Immediately add/remove agent from routing candidates     |

### nornweave.routing.feedback

**Purpose:** Carry query-outcome signals from the fusion service back to the router for adaptive routing (future enhancement). This topic exists from day one so the schema is stable when adaptive routing is implemented.

**Partition key:** `query_id` — groups all feedback for a query together.

**Producers:** Fusion service, after producing each `FusionResult`.

**Consumers:**

| Consumer | Reaction                                                                    |
| -------- | --------------------------------------------------------------------------- |
| Router   | Aggregate signals to tune classification weights (future: adaptive routing) |

**Initial implementation:** The router consumes these events but discards them. The fusion service publishes them. This establishes the contract without requiring the adaptive logic.

### nornweave.dlq

**Purpose:** Dead letter queue for events that failed processing after exhausting retries. Human-readable for debugging; alerts fire on new messages.

**Partition key:** The original topic name (e.g., `nornweave.ingestion.events`).

**Producers:** Any consumer that fails to process an event after max retries.

**Consumers:** Operations team (manual inspection, replay).

---

## Event Schemas

### Envelope Format

Every event on every topic is wrapped in a standard envelope. This ensures consistent metadata for tracing, debugging, and schema evolution.

```json
{
  "event_id": "e1f2a3b4-5c6d-7e8f-9a0b-1c2d3e4f5a6b",
  "event_type": "ingestion.completed",
  "event_version": "1.0",
  "source_service": "code-memory",
  "timestamp": "2026-02-16T07:17:20Z",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "payload": { "..." }
}
```

| Field            | Type     | Description                                       |
| ---------------- | -------- | ------------------------------------------------- |
| `event_id`       | UUID v4  | Unique per event, for idempotency detection       |
| `event_type`     | `string` | Dot-delimited event type (see below)              |
| `event_version`  | `string` | Schema version for this event type                |
| `source_service` | `string` | The service that produced this event              |
| `timestamp`      | ISO 8601 | When the event was produced (UTC)                 |
| `trace_id`       | `string` | W3C Trace Context ID, propagated from the request |
| `payload`        | `object` | Event-specific data (see individual schemas)      |

**Event type registry:**

| `event_type`           | Topic                        | Payload Type           |
| ---------------------- | ---------------------------- | ---------------------- |
| `ingestion.completed`  | `nornweave.ingestion.events` | `IngestionEvent`       |
| `agent.status_changed` | `nornweave.agent.lifecycle`  | `AgentLifecycleEvent`  |
| `routing.feedback`     | `nornweave.routing.feedback` | `RoutingFeedbackEvent` |

### IngestionEvent

Published after a memory agent successfully indexes one or more documents.

```json
{
  "event_id": "...",
  "event_type": "ingestion.completed",
  "event_version": "1.0",
  "source_service": "code-memory",
  "timestamp": "2026-02-16T07:17:20Z",
  "trace_id": "...",
  "payload": {
    "agent_id": "code-memory",
    "domain_id": "code",
    "document_ids": [
      "b7e4a1d9-2c3d-4e5f-6a7b-8c9d0e1f2a3b",
      "c8f3b2e0-3d4e-5f6a-7b8c-9d0e1f2a3b4c"
    ],
    "chunks_created": 47,
    "timestamp": "2026-02-16T07:17:20Z",
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
  }
}
```

### AgentLifecycleEvent

Published when an agent transitions between lifecycle states.

```json
{
  "event_id": "...",
  "event_type": "agent.status_changed",
  "event_version": "1.0",
  "source_service": "code-memory",
  "timestamp": "2026-02-16T07:17:20Z",
  "trace_id": "...",
  "payload": {
    "agent_id": "code-memory",
    "old_status": "STARTING",
    "new_status": "READY",
    "timestamp": "2026-02-16T07:17:20Z"
  }
}
```

**Valid transitions:**

```
STARTING ──▶ READY
STARTING ──▶ OFFLINE       (fatal startup error)
READY    ──▶ DEGRADED
READY    ──▶ DRAINING
DEGRADED ──▶ READY          (recovery)
DEGRADED ──▶ DRAINING
DRAINING ──▶ OFFLINE
```

Invalid transitions (e.g., `OFFLINE → READY`) are rejected by the producer. A restarting agent emits `STARTING` as a fresh lifecycle.

### RoutingFeedbackEvent

Published by the fusion service after producing a `FusionResult`. Carries signals about which domains contributed useful results and which didn't.

```json
{
  "event_id": "...",
  "event_type": "routing.feedback",
  "event_version": "1.0",
  "source_service": "fusion",
  "timestamp": "2026-02-16T07:17:20Z",
  "trace_id": "...",
  "payload": {
    "query_id": "d4e5f6a7-8b9c-0d1e-2f3a-4b5c6d7e8f9a",
    "domains_queried": ["code", "documentation", "conversations"],
    "domain_outcomes": [
      {
        "domain_id": "code",
        "items_contributed": 3,
        "avg_rank_position": 1.7,
        "useful": true
      },
      {
        "domain_id": "documentation",
        "items_contributed": 2,
        "avg_rank_position": 3.5,
        "useful": true
      },
      {
        "domain_id": "conversations",
        "items_contributed": 0,
        "avg_rank_position": null,
        "useful": false
      }
    ],
    "coverage_gaps": ["conversations"],
    "conflict_count": 1,
    "total_latency_ms": 4200
  }
}
```

**`domain_outcomes` fields:**

| Field               | Type          | Description                                              |
| ------------------- | ------------- | -------------------------------------------------------- |
| `domain_id`         | `DomainId`    | The domain                                               |
| `items_contributed` | `int`         | How many items from this domain survived to final result |
| `avg_rank_position` | `float\|null` | Average position in the final ranked list (1-indexed)    |
| `useful`            | `bool`        | Whether this domain contributed at least 1 item          |

**Future use:** The router aggregates these over time to learn which domains tend to be useful for which query patterns, enabling adaptive threshold tuning.

---

## Producer Patterns

All producers use `aiokafka.AIOKafkaProducer` for non-blocking event publishing.

### Fire-and-Forget (Default)

Events are advisory. If Kafka is temporarily unreachable, the producing service logs a warning and continues. No event loss should block the synchronous pipeline.

```python
from aiokafka import AIOKafkaProducer
import json

class EventPublisher:
    def __init__(self, bootstrap_servers: str):
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",              # Wait for all ISRs (durability)
            retries=3,               # Retry transient failures
            retry_backoff_ms=100,
            max_request_size=1_048_576,  # 1 MB max event size
        )

    async def publish(self, topic: str, key: str, envelope: dict) -> None:
        try:
            await self._producer.send_and_wait(topic, key=key, value=envelope)
        except Exception as exc:
            logger.warning(
                "Failed to publish event to %s: %s (event_id=%s)",
                topic, exc, envelope.get("event_id"),
            )
            # Do NOT re-raise. The sync pipeline must not fail due to Kafka.
```

### At-Least-Once (Routing Feedback)

Routing feedback events are more valuable over time (they feed the adaptive learning loop). These use `acks="all"` and 3 retries, but still don't block the caller on failure.

---

## Consumer Patterns

All consumers use `aiokafka.AIOKafkaConsumer` with consumer groups for parallel processing.

### Consumer Group Design

| Consumer Group           | Topics Consumed                                           | Instances            |
| ------------------------ | --------------------------------------------------------- | -------------------- |
| `nornweave-registry`     | `ingestion.events`, `agent.lifecycle`                     | 1                    |
| `nornweave-router`       | `ingestion.events`, `agent.lifecycle`, `routing.feedback` | 1 per router replica |
| `nornweave-dlq-alerting` | `dlq`                                                     | 1                    |

### Consumer Loop

```python
from aiokafka import AIOKafkaConsumer

class EventConsumer:
    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str],
        handlers: dict[str, Callable],
    ):
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,    # Manual commit after processing
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )
        self._handlers = handlers

    async def run(self) -> None:
        await self._consumer.start()
        try:
            async for message in self._consumer:
                envelope = message.value
                event_type = envelope.get("event_type")
                handler = self._handlers.get(event_type)

                if handler is None:
                    logger.warning("Unknown event type: %s", event_type)
                    await self._consumer.commit()
                    continue

                try:
                    await handler(envelope["payload"], envelope)
                    await self._consumer.commit()
                except Exception as exc:
                    await self._handle_failure(message, envelope, exc)
        finally:
            await self._consumer.stop()
```

### Idempotent Consumers

Every consumer must be idempotent. Kafka guarantees at-least-once delivery, which means duplicate events are possible.

**Idempotency strategy:** Track processed `event_id` values in a set (in-memory with a TTL of 1 hour). Skip events whose `event_id` has already been seen.

```python
from cachetools import TTLCache

class IdempotencyGuard:
    def __init__(self, ttl_seconds: int = 3600):
        self._seen = TTLCache(maxsize=10_000, ttl=ttl_seconds)

    def is_duplicate(self, event_id: str) -> bool:
        if event_id in self._seen:
            return True
        self._seen[event_id] = True
        return False
```

---

## Exactly-Once Semantics

NornWeave does **not** require exactly-once processing. The system is designed around at-least-once delivery with idempotent consumers.

**Why not exactly-once?**

| Factor                | Exactly-Once                        | At-Least-Once + Idempotency     |
| --------------------- | ----------------------------------- | ------------------------------- |
| Complexity            | Transactional producers + consumers | Simple `event_id` dedup         |
| Performance           | Kafka transactions add latency      | No transaction overhead         |
| Failure modes         | Complex rollback semantics          | Occasional duplicate (harmless) |
| NornWeave event types | All events are advisory/idempotent  | Natural fit                     |

Every event in the system is either:

- **Idempotent by nature** (ingestion events: processing the same event twice updates the same counter to the same value)
- **Last-write-wins** (lifecycle events: the latest status is always correct regardless of how many times it's applied)

---

## Error Handling & Dead Letter Queue

### Retry Policy

| Attempt | Delay     | Action                                 |
| ------- | --------- | -------------------------------------- |
| 1       | Immediate | Retry processing                       |
| 2       | 1 second  | Retry with backoff                     |
| 3       | 5 seconds | Final retry                            |
| —       | —         | Publish to DLQ, commit offset, move on |

### DLQ Event Format

Failed events are wrapped with failure context before publishing to `nornweave.dlq`:

```json
{
  "original_topic": "nornweave.ingestion.events",
  "original_partition": 2,
  "original_offset": 14827,
  "original_event": { "...full envelope..." },
  "failure": {
    "consumer_group": "nornweave-registry",
    "error_type": "ValueError",
    "error_message": "Invalid domain_id: 'foo-bar' is not a registered domain",
    "stack_trace": "Traceback (most recent call last):\n  ...",
    "attempts": 3,
    "first_failure_at": "2026-02-16T07:10:00Z",
    "last_failure_at": "2026-02-16T07:10:06Z"
  }
}
```

### DLQ Alerting

A lightweight consumer on the `nornweave.dlq` topic fires alerts:

| Condition                  | Alert Level | Channel        |
| -------------------------- | ----------- | -------------- |
| Any DLQ message            | WARNING     | Structured log |
| > 5 DLQ messages in 1 hour | ERROR       | Structured log |

### Manual Replay

DLQ events can be replayed by re-publishing the `original_event` to the `original_topic`:

```bash
# Replay a single DLQ event (manual ops tool)
python -m nornweave_ops.replay_dlq --event-id <event_id>
```

---

## Observability

### Structured Log Events

Every event publish and consume is logged with structured context:

```json
{
  "logger": "nornweave.events",
  "level": "INFO",
  "message": "Event published",
  "event_id": "e1f2a3b4-...",
  "event_type": "ingestion.completed",
  "topic": "nornweave.ingestion.events",
  "partition": 2,
  "offset": 14827,
  "trace_id": "4bf92f3577b34da6...",
  "source_service": "code-memory",
  "latency_ms": 12
}
```

### Metrics (OpenTelemetry)

| Metric                                   | Type      | Labels                           | Description                          |
| ---------------------------------------- | --------- | -------------------------------- | ------------------------------------ |
| `nornweave_events_published_total`       | Counter   | `topic`, `event_type`, `service` | Total events published               |
| `nornweave_events_consumed_total`        | Counter   | `topic`, `event_type`, `group`   | Total events consumed                |
| `nornweave_events_publish_latency_ms`    | Histogram | `topic`                          | Time to publish (producer ack)       |
| `nornweave_events_processing_latency_ms` | Histogram | `topic`, `group`                 | Time to process a consumed event     |
| `nornweave_events_dlq_total`             | Counter   | `original_topic`, `error_type`   | Events sent to DLQ                   |
| `nornweave_consumer_lag`                 | Gauge     | `topic`, `group`, `partition`    | Consumer group lag (messages behind) |

### Trace Propagation

The `trace_id` in the event envelope is the same trace ID from the originating HTTP request. This creates an unbroken trace from `POST /query` → agent recall → fusion → ingestion event → registry update.

```
POST /query (trace: abc123)
  ├── POST /recall to code-memory (trace: abc123)
  │     └── IngestionEvent published (trace: abc123)
  │           └── Registry consumes (trace: abc123)
  ├── POST /recall to docs-memory (trace: abc123)
  └── POST /fuse (trace: abc123)
        └── RoutingFeedbackEvent published (trace: abc123)
```

---

## Communication Flow Diagrams

### Query Pipeline (Synchronous)

```
Client                Router              Code Agent         Docs Agent         Fusion
  │                     │                     │                  │                 │
  │  POST /query        │                     │                  │                 │
  │────────────────────▶│                     │                  │                 │
  │                     │  POST /recall       │                  │                 │
  │                     │────────────────────▶│                  │                 │
  │                     │  POST /recall       │                  │                 │
  │                     │─────────────────────────────────────▶│                 │
  │                     │                     │                  │                 │
  │                     │  RecallResponse     │                  │                 │
  │                     │◀────────────────────│                  │                 │
  │                     │  RecallResponse     │                  │                 │
  │                     │◀─────────────────────────────────────│                 │
  │                     │                     │                  │                 │
  │                     │  POST /fuse         │                  │                 │
  │                     │──────────────────────────────────────────────────────▶│
  │                     │  FusionResult       │                  │                 │
  │                     │◀──────────────────────────────────────────────────────│
  │  FusionResult       │                     │                  │                 │
  │◀────────────────────│                     │                  │                 │
```

### Event Flows (Asynchronous)

```
Code Agent              Kafka                    Registry              Router
     │                     │                        │                     │
     │  IngestionEvent     │                        │                     │
     │────────────────────▶│                        │                     │
     │                     │  ingestion.events      │                     │
     │                     │───────────────────────▶│                     │
     │                     │  ingestion.events      │                     │
     │                     │────────────────────────────────────────────▶│
     │                     │                        │                     │
     │  LifecycleEvent     │                        │                     │
     │  (READY)            │                        │                     │
     │────────────────────▶│                        │                     │
     │                     │  agent.lifecycle       │                     │
     │                     │───────────────────────▶│                     │
     │                     │  agent.lifecycle       │                     │
     │                     │────────────────────────────────────────────▶│
     │                     │                        │                     │
     │                     │                        │                     │

Fusion                  Kafka                    Router
     │                     │                        │
     │  FeedbackEvent      │                        │
     │────────────────────▶│                        │
     │                     │  routing.feedback      │
     │                     │───────────────────────▶│  (store for
     │                     │                        │   adaptive routing)
```

### Agent Startup Sequence

```
Agent                   PostgreSQL          Kafka                Registry
  │                        │                  │                     │
  │  Connect               │                  │                     │
  │───────────────────────▶│                  │                     │
  │  OK                    │                  │                     │
  │◀───────────────────────│                  │                     │
  │                        │                  │                     │
  │  Load models           │                  │                     │
  │  (embedding, reranker) │                  │                     │
  │                        │                  │                     │
  │  AgentLifecycleEvent   │                  │                     │
  │  (STARTING→READY)      │                  │                     │
  │────────────────────────────────────────▶│                     │
  │                        │                  │  lifecycle event    │
  │                        │                  │───────────────────▶│
  │                        │                  │                     │
  │  POST /agents/register │                  │                     │
  │───────────────────────────────────────────────────────────────▶│
  │  201 Created           │                  │                     │
  │◀───────────────────────────────────────────────────────────────│
  │                        │                  │                     │
  │  Begin heartbeat loop  │                  │                     │
  │  (every 10s)           │                  │                     │
```

---

## Configuration

| Variable                          | Type  | Default       | Description                            |
| --------------------------------- | ----- | ------------- | -------------------------------------- |
| `KAFKA_BOOTSTRAP`                 | `str` | `kafka:9092`  | Kafka broker address(es)               |
| `KAFKA_PRODUCER_ACKS`             | `str` | `all`         | Producer acknowledgment level          |
| `KAFKA_PRODUCER_RETRIES`          | `int` | `3`           | Max produce retries                    |
| `KAFKA_PRODUCER_RETRY_BACKOFF_MS` | `int` | `100`         | Backoff between retries                |
| `KAFKA_CONSUMER_GROUP`            | `str` | (per-service) | Consumer group ID                      |
| `KAFKA_AUTO_OFFSET_RESET`         | `str` | `earliest`    | Where to start consuming on first join |
| `KAFKA_MAX_POLL_RECORDS`          | `int` | `100`         | Max records per consumer poll          |
| `KAFKA_SESSION_TIMEOUT_MS`        | `int` | `30000`       | Consumer session timeout               |
| `DLQ_RETRY_MAX`                   | `int` | `3`           | Max retries before DLQ                 |
| `DLQ_ALERT_THRESHOLD`             | `int` | `5`           | DLQ messages/hour before ERROR alert   |
| `EVENT_IDEMPOTENCY_TTL_S`         | `int` | `3600`        | TTL for `event_id` dedup cache         |

---

## Internal Architecture

```
libs/nornweave-core/src/nornweave_core/events/
├── __init__.py
├── envelope.py          # EventEnvelope model (standard wrapper)
├── types.py             # IngestionEvent, AgentLifecycleEvent, RoutingFeedbackEvent
├── publisher.py         # EventPublisher (aiokafka producer wrapper)
├── consumer.py          # EventConsumer (aiokafka consumer loop)
├── idempotency.py       # IdempotencyGuard (TTL-based event_id cache)
├── dlq.py               # DLQ handler (wrap + republish failed events)
└── config.py            # KafkaSettings (pydantic-settings)
```

The event infrastructure lives in `nornweave-core` so it's shared across all services. Each service imports and configures it with service-specific handlers:

```python
# In the registry service
from nornweave_core.events import EventConsumer

consumer = EventConsumer(
    bootstrap_servers=settings.kafka_bootstrap,
    group_id="nornweave-registry",
    topics=[
        "nornweave.ingestion.events",
        "nornweave.agent.lifecycle",
    ],
    handlers={
        "ingestion.completed": handle_ingestion_event,
        "agent.status_changed": handle_lifecycle_event,
    },
)
```
