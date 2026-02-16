# NornWeave — Domain Model Specification

> Canonical definitions of every type that crosses a service boundary or appears in the shared `nornweave-core` library. This document is the single source of truth for the system's vocabulary.

---

## Table of Contents

- [Design Principles](#design-principles)
- [Identifiers](#identifiers)
- [Enumerations](#enumerations)
- [Value Objects](#value-objects)
  - [RelevanceScore](#relevancescore)
  - [EmbeddingVector](#embeddingvector)
  - [SourceCitation](#sourcecitation)
  - [DomainSignal](#domainsignal)
  - [CoverageGap](#coveragegap)
  - [ConflictRecord](#conflictrecord)
  - [TokenBudget](#tokenbudget)
- [Core Entities](#core-entities)
  - [Document](#document)
  - [Chunk](#chunk)
  - [DomainDescriptor](#domaindescriptor)
  - [AgentRegistration](#agentregistration)
- [Request and Response Models](#request-and-response-models)
  - [RecallRequest](#recallrequest)
  - [RecallResponse](#recallresponse)
  - [RecallItem](#recallitem)
  - [RoutingPlan](#routingplan)
  - [RoutingTarget](#routingtarget)
  - [IngestRequest](#ingestrequest)
  - [IngestResult](#ingestresult)
  - [FusionResult](#fusionresult)
  - [HealthStatus](#healthstatus)
- [Event Types](#event-types)
  - [IngestionEvent](#ingestionevent)
  - [AgentLifecycleEvent](#agentlifecycleevent)
- [Aggregate Boundaries](#aggregate-boundaries)
- [Relationship Diagram](#relationship-diagram)
- [Pydantic Implementation Notes](#pydantic-implementation-notes)

---

## Design Principles

1. **Immutable by default.** All value objects and request/response models are frozen Pydantic models. Mutation happens by creating new instances.
2. **IDs are opaque.** Identifiers are typed wrappers around strings. Never pass raw strings where an ID is expected.
3. **Scores are bounded.** All numeric scores live on explicitly defined ranges. No magic floats.
4. **Serialization is the contract.** These models are the wire format. If it can't serialize to JSON cleanly, it doesn't belong here.
5. **Domain language only.** Names come from the README and architecture docs, not from implementation details. No "rows," "columns," or "endpoints" in the domain model.

---

## Identifiers

Typed identifiers prevent the classic "stringly-typed" bug where a `query_id` accidentally ends up in a `domain_id` parameter. Each is a `NewType` wrapper over `str`.

| Identifier   | Format                    | Example                                | Scope                              |
| ------------ | ------------------------- | -------------------------------------- | ---------------------------------- |
| `QueryId`    | UUID v4                   | `"a3f8d2c1-..."`, assigned by router   | Unique per incoming query          |
| `DomainId`   | Lowercase kebab-case slug | `"code"`, `"api-docs"`, `"convo"`      | Unique per registered domain       |
| `AgentId`    | Lowercase kebab-case slug | `"code-memory"`, `"docs-memory"`       | Unique per agent instance          |
| `DocumentId` | UUID v4                   | `"b7e4a1d9-..."`, assigned at ingest   | Unique per ingested document       |
| `ChunkId`    | UUID v4                   | `"c9f2b3e8-..."`, assigned at chunking | Unique per chunk within a document |
| `TraceId`    | W3C Trace Context hex     | `"4bf92f3577b34da6..."` via OTel       | Unique per distributed trace       |

---

## Enumerations

### DomainType

The default domain categories. Deployments may define custom values; these serve as the out-of-the-box partition.

| Value           | Description                                           |
| --------------- | ----------------------------------------------------- |
| `CODE`          | Source files, ASTs, dependency graphs, commit history |
| `DOCUMENTATION` | API docs, READMEs, ADRs, runbooks                     |
| `CONVERSATIONS` | Chat logs, issue threads, PR discussions, transcripts |
| `RESEARCH`      | Papers, articles, Stack Overflow, third-party docs    |

### AgentStatus

Lifecycle state of a registered memory agent.

| Value      | Description                                           |
| ---------- | ----------------------------------------------------- |
| `STARTING` | Agent is initializing (loading models, connecting DB) |
| `READY`    | Agent is accepting recall and ingest requests         |
| `DEGRADED` | Agent is operational but reporting partial failures   |
| `DRAINING` | Agent is finishing in-flight work, rejecting new work |
| `OFFLINE`  | Agent is unreachable or explicitly deregistered       |

### ConflictStrategy

How the fusion layer resolves contradictions between agents.

| Value               | Description                                                 |
| ------------------- | ----------------------------------------------------------- |
| `RECENCY`           | Favor the most recently updated source                      |
| `SOURCE_AUTHORITY`  | Rank by domain precedence (code > docs > conversation)      |
| `CONFIDENCE`        | Use agents' own relevance scores as tiebreakers             |
| `FLAG`              | Surface the contradiction without resolving it              |
| `RECENCY_THEN_FLAG` | Try recency first; flag if timestamps are too close to call |

### ChunkingStrategy

How a memory agent segments documents for storage.

| Value                   | Description                                         |
| ----------------------- | --------------------------------------------------- |
| `SYNTAX_AWARE`          | AST-boundary chunking for source code (tree-sitter) |
| `HIERARCHICAL_SECTIONS` | Section-header chunking for structured documents    |
| `MESSAGE_BOUNDARY`      | Per-message or per-topic chunking for conversations |
| `RECURSIVE_CHARACTER`   | Fallback character-level splitting with overlap     |

### IngestStatus

Outcome of a document ingestion attempt.

| Value      | Description                                                  |
| ---------- | ------------------------------------------------------------ |
| `ACCEPTED` | Document queued for processing                               |
| `INDEXED`  | Document fully chunked, embedded, and stored                 |
| `REJECTED` | Document rejected (unsupported format, too large, duplicate) |
| `FAILED`   | Processing failed after acceptance                           |

---

## Value Objects

### RelevanceScore

A bounded floating-point score representing how relevant a result is to a query.

| Field   | Type    | Constraints           | Description                           |
| ------- | ------- | --------------------- | ------------------------------------- |
| `value` | `float` | `0.0 <= value <= 1.0` | 0.0 = irrelevant, 1.0 = perfect match |

Validation rejects values outside the range rather than clamping. If the model says 1.3, something is wrong upstream and we want to know about it.

### EmbeddingVector

A dense vector representation of a chunk or query.

| Field        | Type          | Constraints                    | Description                         |
| ------------ | ------------- | ------------------------------ | ----------------------------------- |
| `values`     | `list[float]` | Length must match `dimensions` | The raw vector                      |
| `dimensions` | `int`         | One of: 384, 768, 1536         | Dimensionality (model-dependent)    |
| `model_name` | `str`         | Non-empty                      | Which embedding model produced this |

### SourceCitation

Provenance metadata for a recall item. Tells the consumer where the information came from.

| Field         | Type                     | Constraints   | Description                                  |
| ------------- | ------------------------ | ------------- | -------------------------------------------- |
| `document_id` | `DocumentId`             | Required      | The source document                          |
| `chunk_id`    | `ChunkId`                | Required      | The specific chunk                           |
| `domain_id`   | `DomainId`               | Required      | Which domain this came from                  |
| `source_path` | `str`                    | Required      | Human-readable path (file path, URL, etc.)   |
| `line_range`  | `tuple[int,int] \| None` | Optional      | Start/end line numbers (code, docs)          |
| `timestamp`   | `datetime`               | UTC, required | When this content was last updated at source |

### DomainSignal

A routing signal extracted from a query by the router.

| Field       | Type             | Constraints  | Description                                |
| ----------- | ---------------- | ------------ | ------------------------------------------ |
| `domain_id` | `DomainId`       | Required     | The domain this signal points to           |
| `score`     | `RelevanceScore` | Required     | How strongly the query matches this domain |
| `keywords`  | `list[str]`      | May be empty | Keywords that triggered this signal        |

### CoverageGap

Annotation indicating that a domain could not contribute to a fused response.

| Field       | Type       | Constraints | Description                                       |
| ----------- | ---------- | ----------- | ------------------------------------------------- |
| `domain_id` | `DomainId` | Required    | The domain that was expected but did not respond  |
| `agent_id`  | `AgentId`  | Required    | The specific agent that timed out or failed       |
| `reason`    | `str`      | Required    | Human-readable explanation (timeout, crash, etc.) |

### ConflictRecord

A record of contradictory information detected during fusion.

| Field         | Type                 | Constraints  | Description                                      |
| ------------- | -------------------- | ------------ | ------------------------------------------------ |
| `items`       | `list[RecallItem]`   | Min length 2 | The contradicting recall items                   |
| `resolution`  | `ConflictStrategy`   | Required     | Which strategy was applied                       |
| `resolved_to` | `RecallItem \| None` | Optional     | The winner, if one was chosen. `None` if flagged |

### TokenBudget

Token accounting for query analysis and response generation.

| Field      | Type  | Constraints | Description                       |
| ---------- | ----- | ----------- | --------------------------------- |
| `limit`    | `int` | `> 0`       | Maximum tokens allocated          |
| `consumed` | `int` | `>= 0`      | Tokens consumed so far            |
| `model`    | `str` | Non-empty   | Tokenizer model used for counting |

---

## Core Entities

### Document

A source document as ingested by a memory agent. This is the pre-chunking representation.

| Field               | Type            | Constraints             | Description                                              |
| ------------------- | --------------- | ----------------------- | -------------------------------------------------------- |
| `id`                | `DocumentId`    | Assigned at ingest      | Unique identifier                                        |
| `domain_id`         | `DomainId`      | Required                | Which domain this document belongs to                    |
| `source_path`       | `str`           | Required                | Original path or URL                                     |
| `content`           | `str`           | Required                | Raw content (text, code, transcript)                     |
| `content_hash`      | `str`           | SHA-256 hex             | For deduplication and change detection                   |
| `metadata`          | `dict[str,Any]` | Optional, defaults `{}` | Extensible metadata (language, author, commit SHA, etc.) |
| `ingested_at`       | `datetime`      | UTC, assigned at ingest | When this document entered the system                    |
| `source_updated_at` | `datetime`      | UTC, required           | When the source was last modified                        |

### Chunk

A segment of a document, stored with its embedding. This is the unit of retrieval.

| Field         | Type              | Constraints              | Description                                                      |
| ------------- | ----------------- | ------------------------ | ---------------------------------------------------------------- |
| `id`          | `ChunkId`         | Assigned at chunking     | Unique identifier                                                |
| `document_id` | `DocumentId`      | Required                 | Parent document                                                  |
| `domain_id`   | `DomainId`        | Required                 | Inherited from parent document                                   |
| `content`     | `str`             | Required, non-empty      | The chunk text                                                   |
| `embedding`   | `EmbeddingVector` | Required after embedding | Dense vector representation                                      |
| `position`    | `int`             | `>= 0`                   | Ordinal position within the document                             |
| `token_count` | `int`             | `> 0`                    | Number of tokens in this chunk                                   |
| `metadata`    | `dict[str, Any]`  | Optional, defaults `{}`  | Chunk-level metadata (header path, function name, speaker, etc.) |
| `created_at`  | `datetime`        | UTC                      | When this chunk was created                                      |

### DomainDescriptor

A machine-readable description of a registered domain. Returned by the `describe()` endpoint and used by the router for dynamic domain discovery.

| Field                  | Type               | Constraints | Description                               |
| ---------------------- | ------------------ | ----------- | ----------------------------------------- | -------------------------------------- |
| `domain_id`            | `DomainId`         | Required    | Unique domain identifier                  |
| `name`                 | `str`              | Required    | Human-readable domain name                |
| `description`          | `str`              | Required    | What kind of knowledge this domain covers |
| `chunking_strategy`    | `ChunkingStrategy` | Required    | How documents are segmented               |
| `embedding_model`      | `str`              | Required    | Name of the embedding model in use        |
| `embedding_dimensions` | `int`              | Required    | Dimensionality of stored vectors          |
| `document_count`       | `int`              | `>= 0`      | Current number of indexed documents       |
| `chunk_count`          | `int`              | `>= 0`      | Current number of stored chunks           |
| `last_ingestion_at`    | `datetime          | None`       | Nullable                                  | Timestamp of the most recent ingestion |

### AgentRegistration

A record of a memory agent in the service registry.

| Field               | Type               | Constraints            | Description                          |
| ------------------- | ------------------ | ---------------------- | ------------------------------------ |
| `agent_id`          | `AgentId`          | Required               | Unique agent identifier              |
| `domain`            | `DomainDescriptor` | Required               | The domain this agent serves         |
| `base_url`          | `str`              | Valid URL, required    | Network address for this agent       |
| `status`            | `AgentStatus`      | Defaults to `STARTING` | Current lifecycle state              |
| `registered_at`     | `datetime`         | UTC                    | When the agent first registered      |
| `last_heartbeat_at` | `datetime`         | UTC                    | Most recent successful health check  |
| `health_port`       | `int`              | Valid port range       | Port for health and readiness probes |

---

## Request and Response Models

### RecallRequest

Sent from the router to a memory agent. Carries the query plus routing context.

| Field           | Type             | Constraints       | Description                                             |
| --------------- | ---------------- | ----------------- | ------------------------------------------------------- |
| `query_id`      | `QueryId`        | Required          | Ties this request to the originating query              |
| `query_text`    | `str`            | Required          | The query string (possibly rewritten for this domain)   |
| `original_text` | `str`            | Required          | The original, un-rewritten query                        |
| `domain_id`     | `DomainId`       | Required          | Which domain this request targets                       |
| `top_k`         | `int`            | `> 0`, default 20 | Maximum number of results to return                     |
| `filters`       | `dict[str, Any]` | Optional          | Domain-specific filter criteria (date range, path glob) |
| `trace_id`      | `TraceId`        | Required          | Distributed trace identifier                            |
| `timeout_ms`    | `int`            | `> 0`             | How long the agent has to respond                       |

### RecallResponse

Returned by a memory agent. Contains ranked results and self-assessment metadata.

| Field            | Type               | Constraints  | Description                        |
| ---------------- | ------------------ | ------------ | ---------------------------------- |
| `query_id`       | `QueryId`          | Required     | Echoed from the request            |
| `agent_id`       | `AgentId`          | Required     | Which agent produced this response |
| `domain_id`      | `DomainId`         | Required     | Which domain was searched          |
| `items`          | `list[RecallItem]` | May be empty | Ranked results, best first         |
| `total_searched` | `int`              | `>= 0`       | How many chunks were searched      |
| `latency_ms`     | `int`              | `>= 0`       | How long the recall took           |
| `trace_id`       | `TraceId`          | Required     | Echoed from the request            |

### RecallItem

A single result from a memory agent. The atomic unit of information in the system.

| Field      | Type             | Constraints | Description                                    |
| ---------- | ---------------- | ----------- | ---------------------------------------------- |
| `chunk_id` | `ChunkId`        | Required    | Which chunk this result came from              |
| `content`  | `str`            | Required    | The chunk text                                 |
| `score`    | `RelevanceScore` | Required    | Agent-assessed relevance to the query          |
| `citation` | `SourceCitation` | Required    | Full provenance trail                          |
| `metadata` | `dict[str, Any]` | Optional    | Domain-specific metadata (function name, etc.) |

### RoutingPlan

The output of the router agent. Describes which domains should receive the query and how.

| Field           | Type                  | Constraints  | Description                                              |
| --------------- | --------------------- | ------------ | -------------------------------------------------------- |
| `query_id`      | `QueryId`             | Required     | Identifier for this query                                |
| `original_text` | `str`                 | Required     | The original query text                                  |
| `targets`       | `list[RoutingTarget]` | Non-empty    | Where to send the query                                  |
| `signals`       | `list[DomainSignal]`  | May be empty | All extracted domain signals (including below-threshold) |
| `created_at`    | `datetime`            | UTC          | When this plan was produced                              |
| `trace_id`      | `TraceId`             | Required     | Distributed trace identifier                             |

### RoutingTarget

A single entry in a routing plan. Pairs a domain with an optional query rewrite.

| Field             | Type             | Constraints | Description                                      |
| ----------------- | ---------------- | ----------- | ------------------------------------------------ | --------------------------------------------- |
| `domain_id`       | `DomainId`       | Required    | Target domain                                    |
| `agent_id`        | `AgentId`        | Required    | Specific agent to receive the request            |
| `relevance`       | `RelevanceScore` | Required    | Router's confidence that this domain is relevant |
| `rewritten_query` | `str             | None`       | Nullable                                         | Domain-optimized query rewrite, if applicable |

### IngestRequest

Submitted to a memory agent to add new documents.

| Field       | Type             | Constraints | Description                  |
| ----------- | ---------------- | ----------- | ---------------------------- |
| `documents` | `list[Document]` | Non-empty   | Documents to ingest          |
| `agent_id`  | `AgentId`        | Required    | Target agent                 |
| `trace_id`  | `TraceId`        | Required    | Distributed trace identifier |

### IngestResult

Returned by a memory agent after processing an ingestion request.

| Field       | Type                         | Constraints | Description                                 |
| ----------- | ---------------------------- | ----------- | ------------------------------------------- |
| `agent_id`  | `AgentId`                    | Required    | Which agent performed the ingestion         |
| `domain_id` | `DomainId`                   | Required    | Which domain the documents were ingested to |
| `results`   | `list[DocumentIngestStatus]` | Non-empty   | Per-document outcome                        |
| `trace_id`  | `TraceId`                    | Required    | Distributed trace identifier                |

**DocumentIngestStatus** (inline):

| Field            | Type           | Constraints | Description                   |
| ---------------- | -------------- | ----------- | ----------------------------- | ----------------------------------- |
| `document_id`    | `DocumentId`   | Required    | The document in question      |
| `status`         | `IngestStatus` | Required    | Outcome of the ingest attempt |
| `chunks_created` | `int`          | `>= 0`      | Number of chunks generated    |
| `error`          | `str           | None`       | Nullable                      | Error message if status is `FAILED` |

### FusionResult

The final output of the response fusion pipeline. This is what the client receives.

| Field              | Type                   | Constraints  | Description                                             |
| ------------------ | ---------------------- | ------------ | ------------------------------------------------------- | ---------------------------------------------------- |
| `query_id`         | `QueryId`              | Required     | Ties back to the original query                         |
| `items`            | `list[RecallItem]`     | May be empty | Deduplicated, ranked, conflict-resolved results         |
| `synthesis`        | `str                   | None`        | Nullable                                                | Optional narrative summary (if synthesis is enabled) |
| `conflicts`        | `list[ConflictRecord]` | May be empty | Any detected cross-domain contradictions                |
| `coverage_gaps`    | `list[CoverageGap]`    | May be empty | Domains that failed to respond in time                  |
| `domains_queried`  | `list[DomainId]`       | Non-empty    | Which domains participated                              |
| `total_latency_ms` | `int`                  | `>= 0`       | End-to-end time from query receipt to fusion completion |
| `trace_id`         | `TraceId`              | Required     | Distributed trace identifier                            |

### HealthStatus

Returned by every service's `/health` and `/ready` endpoints.

| Field            | Type              | Constraints | Description                                               |
| ---------------- | ----------------- | ----------- | --------------------------------------------------------- | -------------------------------------- |
| `service_name`   | `str`             | Required    | Name of the service (e.g., `"code-memory"`)               |
| `status`         | `AgentStatus`     | Required    | Current lifecycle state                                   |
| `uptime_seconds` | `float`           | `>= 0`      | Time since service start                                  |
| `index_size`     | `int              | None`       | Nullable                                                  | Number of indexed chunks (agents only) |
| `last_ingest_at` | `datetime         | None`       | Nullable                                                  | Most recent ingestion (agents only)    |
| `checks`         | `dict[str, bool]` | Required    | Named health checks (e.g., `{"db": true, "model": true}`) |

---

## Event Types

Published to the Kafka event bus for cross-agent coordination.

### IngestionEvent

Published by a memory agent after successfully indexing new documents.

| Field            | Type               | Constraints | Description                           |
| ---------------- | ------------------ | ----------- | ------------------------------------- |
| `agent_id`       | `AgentId`          | Required    | Which agent ingested the documents    |
| `domain_id`      | `DomainId`         | Required    | Which domain was updated              |
| `document_ids`   | `list[DocumentId]` | Non-empty   | Documents that were ingested          |
| `chunks_created` | `int`              | `> 0`       | Total new chunks across all documents |
| `timestamp`      | `datetime`         | UTC         | When the ingestion completed          |
| `trace_id`       | `TraceId`          | Required    | Distributed trace identifier          |

**Kafka Topic:** `nornweave.ingestion.events`

### AgentLifecycleEvent

Published when an agent's status changes. Consumed by the registry.

| Field        | Type          | Constraints | Description                  |
| ------------ | ------------- | ----------- | ---------------------------- |
| `agent_id`   | `AgentId`     | Required    | Which agent changed state    |
| `old_status` | `AgentStatus` | Required    | Previous status              |
| `new_status` | `AgentStatus` | Required    | New status                   |
| `timestamp`  | `datetime`    | UTC         | When the transition occurred |

**Kafka Topic:** `nornweave.agent.lifecycle`

---

## Aggregate Boundaries

The domain model splits into four aggregates, each owned by a single service. No service directly reads or writes another aggregate's state.

| Aggregate        | Root Entity         | Owned Types                                                                 | Owning Service   |
| ---------------- | ------------------- | --------------------------------------------------------------------------- | ---------------- |
| **Routing**      | `RoutingPlan`       | `RoutingTarget`, `DomainSignal`, `TokenBudget`                              | Router Agent     |
| **Memory**       | `Document`          | `Chunk`, `EmbeddingVector`, `RecallRequest`, `RecallResponse`, `RecallItem` | Memory Agent     |
| **Fusion**       | `FusionResult`      | `ConflictRecord`, `CoverageGap`                                             | Fusion Service   |
| **Registration** | `AgentRegistration` | `DomainDescriptor`, `HealthStatus`, `AgentLifecycleEvent`                   | Service Registry |

Cross-aggregate communication happens exclusively through:

1. **HTTP request/response** (synchronous, via the defined request/response models)
2. **Kafka events** (asynchronous, via the defined event types)

---

## Relationship Diagram

```
                        ┌─────────────────────────────────────────────────┐
                        │                  ROUTING                        │
                        │                                                 │
  Incoming Query ──────▶│  RoutingPlan                                    │
                        │    ├── RoutingTarget[]                          │
                        │    │     ├── DomainId                           │
                        │    │     ├── AgentId                            │
                        │    │     ├── RelevanceScore                     │
                        │    │     └── rewritten_query?                   │
                        │    └── DomainSignal[]                           │
                        └────────────────┬────────────────────────────────┘
                                         │ fan-out (RecallRequest per target)
                        ┌────────────────▼────────────────────────────────┐
                        │                  MEMORY                         │
                        │                                                 │
                        │  Document ──── Chunk[]                          │
                        │                  ├── EmbeddingVector             │
                        │                  └── SourceCitation              │
                        │                                                 │
                        │  RecallRequest ──▶ RecallResponse                │
                        │                      └── RecallItem[]           │
                        │                           ├── RelevanceScore    │
                        │                           └── SourceCitation    │
                        └────────────────┬────────────────────────────────┘
                                         │ collect responses
                        ┌────────────────▼────────────────────────────────┐
                        │                  FUSION                         │
                        │                                                 │
                        │  FusionResult                                   │
                        │    ├── RecallItem[] (deduplicated, ranked)      │
                        │    ├── ConflictRecord[]                         │
                        │    ├── CoverageGap[]                            │
                        │    └── synthesis?                                │
                        └─────────────────────────────────────────────────┘

                        ┌─────────────────────────────────────────────────┐
                        │               REGISTRATION                      │
                        │                                                 │
                        │  AgentRegistration                              │
                        │    ├── DomainDescriptor                         │
                        │    ├── AgentStatus                              │
                        │    └── HealthStatus                             │
                        │                                                 │
                        │  ◀── AgentLifecycleEvent (Kafka)                │
                        │  ◀── IngestionEvent (Kafka, advisory)           │
                        └─────────────────────────────────────────────────┘
```

---

## Pydantic Implementation Notes

All models in this spec map to Pydantic v2 `BaseModel` subclasses in the `nornweave-core` library.

**Conventions:**

- **Frozen models.** All value objects and request/response models use `model_config = ConfigDict(frozen=True)`.
- **Typed IDs.** Use `NewType` from `typing` for all identifier types. Pydantic validates these as their base type (`str`) on the wire, but the type checker enforces correct usage in code.
- **Strict mode.** Enable `strict=True` on `RelevanceScore` to reject ints-masquerading-as-floats and out-of-range values.
- **JSON Schema export.** Every model must produce a valid JSON Schema via `model.model_json_schema()`. These schemas are published alongside the OpenAPI spec.
- **Datetime handling.** All timestamps are UTC `datetime` instances. Serialized as ISO 8601 strings with `Z` suffix.

**Package location:** `libs/nornweave-core/src/nornweave_core/models/`

```
models/
├── __init__.py           # Re-exports all public models
├── identifiers.py        # NewType definitions
├── enums.py              # All enumerations
├── values.py             # Value objects (RelevanceScore, EmbeddingVector, etc.)
├── entities.py           # Core entities (Document, Chunk, DomainDescriptor, etc.)
├── requests.py           # Request models (RecallRequest, IngestRequest)
├── responses.py          # Response models (RecallResponse, FusionResult, etc.)
└── events.py             # Kafka event types
```
