# NornWeave — Service Interface Contracts

> Formal API specification for every service in the NornWeave mesh. All request/response types reference the [Domain Model Specification](DOMAIN-MODEL.md).

---

## Table of Contents

- [Conventions](#conventions)
  - [Common Headers](#common-headers)
  - [Authentication](#authentication)
  - [Error Response Format](#error-response-format)
  - [Error Codes](#error-codes)
  - [Timeout Policy](#timeout-policy)
- [Memory Agent API](#memory-agent-api)
  - [POST /recall](#post-recall)
  - [POST /ingest](#post-ingest)
  - [GET /health](#get-health)
  - [GET /ready](#get-ready)
  - [GET /describe](#get-describe)
- [Router Agent API](#router-agent-api)
  - [POST /query](#post-query)
  - [GET /health](#get-health-1)
  - [GET /ready](#get-ready-1)
- [Fusion Service API](#fusion-service-api)
  - [POST /fuse](#post-fuse)
  - [GET /health](#get-health-2)
  - [GET /ready](#get-ready-2)
- [Service Registry API](#service-registry-api)
  - [POST /agents/register](#post-agentsregister)
  - [DELETE /agents/{agent_id}](#delete-agentsagent_id)
  - [GET /agents](#get-agents)
  - [GET /agents/{agent_id}](#get-agentsagent_id)
  - [POST /agents/{agent_id}/heartbeat](#post-agentsagent_idheartbeat)
  - [GET /health](#get-health-3)
- [Idempotency](#idempotency)
- [Versioning](#versioning)
- [Rate Limiting](#rate-limiting)

---

## Conventions

### Common Headers

Every request and response across all services must include the following headers.

**Request Headers:**

| Header          | Type     | Required    | Description                                                   |
| --------------- | -------- | ----------- | ------------------------------------------------------------- |
| `X-Trace-Id`    | `string` | Yes         | W3C Trace Context identifier. Propagated across all services. |
| `X-Query-Id`    | `string` | Conditional | UUID of the originating query. Required on recall/fuse calls. |
| `Authorization` | `string` | Yes         | Bearer token for inter-service auth.                          |
| `Content-Type`  | `string` | Yes         | Always `application/json`.                                    |
| `Accept`        | `string` | Yes         | Always `application/json`.                                    |

**Response Headers:**

| Header                  | Type     | Always Present | Description                                  |
| ----------------------- | -------- | -------------- | -------------------------------------------- |
| `X-Trace-Id`            | `string` | Yes            | Echoed from request.                         |
| `X-Request-Duration-Ms` | `int`    | Yes            | Server-side processing time in milliseconds. |
| `X-NornWeave-Version`   | `string` | Yes            | Service version string (e.g., `"0.1.0"`).    |
| `Content-Type`          | `string` | Yes            | Always `application/json`.                   |

### Authentication

**Initial implementation:** Shared bearer token, distributed via environment variables.

```
Authorization: Bearer ${NORNWEAVE_SERVICE_TOKEN}
```

All inter-service calls must include this header. Requests without a valid token receive `401 Unauthorized`. The token is configured per deployment environment and shared across all services in the mesh.

**Upgrade path:** mTLS for production deployments (documented in TECH-STACK.md, not enforced by this spec).

### Error Response Format

All error responses use a consistent JSON body regardless of which service produces them.

```json
{
  "error": {
    "code": "AGENT_TIMEOUT",
    "message": "Memory agent 'code-memory' did not respond within 5000ms.",
    "details": {
      "agent_id": "code-memory",
      "timeout_ms": 5000
    },
    "trace_id": "4bf92f3577b34da6...",
    "timestamp": "2026-02-16T13:37:22Z"
  }
}
```

| Field             | Type             | Required | Description                              |
| ----------------- | ---------------- | -------- | ---------------------------------------- |
| `error.code`      | `string`         | Yes      | Machine-readable error code (see table)  |
| `error.message`   | `string`         | Yes      | Human-readable description               |
| `error.details`   | `object \| null` | No       | Additional context, error-code-dependent |
| `error.trace_id`  | `string`         | Yes      | Trace ID for correlation                 |
| `error.timestamp` | `string`         | Yes      | ISO 8601 UTC timestamp                   |

### Error Codes

Standardized error codes used across all services. Each maps to a specific HTTP status.

| Error Code           | HTTP Status | Description                                           |
| -------------------- | ----------- | ----------------------------------------------------- |
| `INVALID_REQUEST`    | 400         | Request body failed Pydantic validation.              |
| `UNAUTHORIZED`       | 401         | Missing or invalid bearer token.                      |
| `AGENT_NOT_FOUND`    | 404         | Referenced agent ID does not exist in the registry.   |
| `DOMAIN_NOT_FOUND`   | 404         | Referenced domain ID does not exist.                  |
| `QUERY_TOO_LONG`     | 400         | Query text exceeds the maximum token limit.           |
| `AGENT_TIMEOUT`      | 504         | Memory agent did not respond within the deadline.     |
| `AGENT_UNAVAILABLE`  | 503         | Agent is registered but not in `READY` status.        |
| `INGESTION_REJECTED` | 422         | One or more documents failed validation.              |
| `INGESTION_FAILED`   | 500         | Ingestion accepted but processing failed.             |
| `FUSION_PARTIAL`     | 207         | Fusion completed but with coverage gaps.              |
| `FUSION_FAILED`      | 500         | Fusion pipeline failed entirely.                      |
| `REGISTRY_CONFLICT`  | 409         | Agent ID already registered (duplicate registration). |
| `INTERNAL_ERROR`     | 500         | Unhandled server error. Check logs.                   |
| `SERVICE_OVERLOADED` | 429         | Too many concurrent requests.                         |
| `MODEL_NOT_LOADED`   | 503         | Embedding or classification model not yet ready.      |

### Timeout Policy

Timeouts are layered to prevent cascade stalls.

```
┌─────────────────────────────────────────────────────────────┐
│ Client-facing query timeout                    30,000 ms    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Router classification + rewrite              2,000 ms │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Agent recall (per-agent deadline)             5,000 ms │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Fusion pipeline                              10,000 ms │  │
│  │  ├── Collection phase        (agent deadline + 500ms) │  │
│  │  ├── Normalize + Dedup + Rank                2,000 ms │  │
│  │  └── Synthesis (if enabled)                  5,000 ms │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

| Stage                 | Default Timeout | Configurable Via                | Behavior on Expiry                           |
| --------------------- | --------------- | ------------------------------- | -------------------------------------------- |
| Client-facing query   | 30,000 ms       | `QUERY_TIMEOUT_MS`              | Return best-effort `FusionResult` with gaps  |
| Router classification | 2,000 ms        | `ROUTER_TIMEOUT_MS`             | Return `504 AGENT_TIMEOUT`                   |
| Agent recall          | 5,000 ms        | `RECALL_TIMEOUT_MS`             | Proceed without agent; log `CoverageGap`     |
| Fusion collection     | 5,500 ms        | Derived (recall + 500ms buffer) | Close collection; fuse what arrived          |
| Fusion processing     | 2,000 ms        | `FUSION_PROCESS_TIMEOUT_MS`     | Return partial results without ranking/dedup |
| Synthesis             | 5,000 ms        | `SYNTHESIS_TIMEOUT_MS`          | Return results without narrative summary     |
| Health check          | 1,000 ms        | `HEALTH_TIMEOUT_MS`             | Mark agent as `DEGRADED`                     |

All timeout values are in milliseconds and overridable via environment variables as shown.

---

## Memory Agent API

The four-method common interface implemented by every memory agent.

**Base URL pattern:** `http://{agent_id}:{port}` (resolved via the service registry)

### POST /recall

Search the domain store and return ranked results.

**Request Body:** [`RecallRequest`](DOMAIN-MODEL.md#recallrequest)

```json
{
  "query_id": "a3f8d2c1-4b5e-4f6a-8c7d-9e0f1a2b3c4d",
  "query_text": "payment module error handling",
  "original_text": "what changed in the payment module after the outage",
  "domain_id": "code",
  "top_k": 20,
  "filters": {
    "path_glob": "src/payments/**",
    "since": "2026-01-15T00:00:00Z"
  },
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "timeout_ms": 5000
}
```

**Success Response:** `200 OK` → [`RecallResponse`](DOMAIN-MODEL.md#recallresponse)

```json
{
  "query_id": "a3f8d2c1-4b5e-4f6a-8c7d-9e0f1a2b3c4d",
  "agent_id": "code-memory",
  "domain_id": "code",
  "items": [
    {
      "chunk_id": "c9f2b3e8-1a2b-3c4d-5e6f-7a8b9c0d1e2f",
      "content": "def handle_payment_error(error: PaymentError) -> Response:\n    ...",
      "score": { "value": 0.91 },
      "citation": {
        "document_id": "b7e4a1d9-...",
        "chunk_id": "c9f2b3e8-...",
        "domain_id": "code",
        "source_path": "src/payments/handlers.py",
        "line_range": [42, 67],
        "timestamp": "2026-01-16T09:14:00Z"
      },
      "metadata": {
        "language": "python",
        "function_name": "handle_payment_error"
      }
    }
  ],
  "total_searched": 1847,
  "latency_ms": 312,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

**Error Responses:**

| Code | Error Code         | When                                 |
| ---- | ------------------ | ------------------------------------ |
| 400  | `INVALID_REQUEST`  | Missing required fields, bad `top_k` |
| 401  | `UNAUTHORIZED`     | Invalid bearer token                 |
| 503  | `MODEL_NOT_LOADED` | Embedding model not yet initialized  |

**Behavior Notes:**

- An empty `items` list is a valid successful response (the query matched nothing).
- The agent must respect the `timeout_ms` hint. If internal processing exceeds the budget, return whatever results are available.
- `filters` is an open `dict` with domain-specific keys. The code agent supports `path_glob` and `since`; the conversation agent supports `participants` and `date_range`. Unknown filter keys are silently ignored.

---

### POST /ingest

Submit documents for indexing into the domain store.

**Request Body:** [`IngestRequest`](DOMAIN-MODEL.md#ingestrequest)

```json
{
  "documents": [
    {
      "id": "b7e4a1d9-2c3d-4e5f-6a7b-8c9d0e1f2a3b",
      "domain_id": "code",
      "source_path": "src/payments/handlers.py",
      "content": "def handle_payment_error(error: PaymentError) -> Response:\n    ...",
      "content_hash": "a1b2c3d4e5f6...",
      "metadata": { "language": "python", "commit_sha": "abc1234" },
      "ingested_at": "2026-02-16T06:37:00Z",
      "source_updated_at": "2026-01-16T09:14:00Z"
    }
  ],
  "agent_id": "code-memory",
  "trace_id": "5cf93f4688c45eb7b4df030a1f1f5847"
}
```

**Success Response:** `202 Accepted` → [`IngestResult`](DOMAIN-MODEL.md#ingestresult)

```json
{
  "agent_id": "code-memory",
  "domain_id": "code",
  "results": [
    {
      "document_id": "b7e4a1d9-2c3d-4e5f-6a7b-8c9d0e1f2a3b",
      "status": "ACCEPTED",
      "chunks_created": 0,
      "error": null
    }
  ],
  "trace_id": "5cf93f4688c45eb7b4df030a1f1f5847"
}
```

**Error Responses:**

| Code | Error Code           | When                                         |
| ---- | -------------------- | -------------------------------------------- |
| 400  | `INVALID_REQUEST`    | Empty document list, missing required fields |
| 401  | `UNAUTHORIZED`       | Invalid bearer token                         |
| 422  | `INGESTION_REJECTED` | Document too large, unsupported format       |

**Behavior Notes:**

- Returns `202 Accepted`, not `200 OK`. Ingestion is asynchronous; the response confirms receipt, not completion. The `ACCEPTED` status means "queued for processing."
- Chunking, embedding, and storage happen after the response is returned. The agent publishes an `IngestionEvent` to Kafka upon completion.
- `content_hash` enables idempotent re-ingestion. If a document with the same hash already exists, the agent returns `REJECTED` with a `"duplicate"` reason.
- Maximum document size: 10 MB per document, 50 MB per batch. Exceeding either limit returns `422`.

---

### GET /health

Liveness probe. Returns `200` if the process is running.

**Request Body:** None.

**Success Response:** `200 OK` → [`HealthStatus`](DOMAIN-MODEL.md#healthstatus)

```json
{
  "service_name": "code-memory",
  "status": "READY",
  "uptime_seconds": 3847.2,
  "index_size": 42531,
  "last_ingest_at": "2026-02-16T05:22:00Z",
  "checks": {
    "db": true,
    "model": true,
    "disk": true
  }
}
```

**Behavior Notes:**

- This endpoint must respond within 1,000 ms under all conditions.
- Returns `200 OK` even when status is `DEGRADED`. The status field itself communicates the problem.
- Returns `503` only when the service is actively crashing or shutting down.
- No authentication required on health endpoints.

---

### GET /ready

Readiness probe. Returns `200` only when the agent is ready to serve traffic.

**Request Body:** None.

**Success Response:** `200 OK` → [`HealthStatus`](DOMAIN-MODEL.md#healthstatus)

Same body as `/health`, but returns `503 Service Unavailable` if:

- The database connection is not established.
- The embedding model is not loaded.
- The agent status is `STARTING`, `DRAINING`, or `OFFLINE`.

Kubernetes and Docker Compose use this endpoint to determine when to route traffic to this container.

---

### GET /describe

Return a machine-readable description of the domain this agent covers.

**Request Body:** None.

**Success Response:** `200 OK` → [`DomainDescriptor`](DOMAIN-MODEL.md#domaindescriptor)

```json
{
  "domain_id": "code",
  "name": "Source Code",
  "description": "Application source code, dependency manifests, infrastructure-as-code definitions, and CI/CD configurations.",
  "chunking_strategy": "SYNTAX_AWARE",
  "embedding_model": "microsoft/codebert-base",
  "embedding_dimensions": 768,
  "document_count": 1247,
  "chunk_count": 42531,
  "last_ingestion_at": "2026-02-16T05:22:00Z"
}
```

**Behavior Notes:**

- Called by the router on startup and periodically during runtime for dynamic domain discovery.
- Called by the registry during agent registration.
- No authentication required.
- Counts (`document_count`, `chunk_count`) are approximate; exact counts are expensive on large indexes and not worth the precision for routing decisions.

---

## Router Agent API

The system's public entry point. Receives queries from clients and orchestrates the recall pipeline.

**Base URL:** `http://router:{port}` (default port: `8080`)

### POST /query

Submit a query to the NornWeave mesh.

**Request Body:**

| Field        | Type           | Required | Default | Description                                     |
| ------------ | -------------- | -------- | ------- | ----------------------------------------------- |
| `query_text` | `string`       | Yes      | —       | The natural language query                      |
| `top_k`      | `int`          | No       | `20`    | Max results per domain agent                    |
| `domains`    | `list[string]` | No       | `null`  | Restrict to these domains (skip classification) |
| `filters`    | `object`       | No       | `{}`    | Domain-specific filters (passed through)        |
| `synthesize` | `bool`         | No       | `false` | Whether to generate a narrative summary         |
| `timeout_ms` | `int`          | No       | `30000` | Client-level timeout                            |

```json
{
  "query_text": "what changed in the payment module after the outage on Jan 15",
  "top_k": 10,
  "domains": null,
  "filters": { "since": "2026-01-15T00:00:00Z" },
  "synthesize": true,
  "timeout_ms": 30000
}
```

**Success Response:** `200 OK` → [`FusionResult`](DOMAIN-MODEL.md#fusionresult)

```json
{
  "query_id": "d4e5f6a7-8b9c-0d1e-2f3a-4b5c6d7e8f9a",
  "items": ["..."],
  "synthesis": "After the Jan 15 outage, the payment module received three commits...",
  "conflicts": [],
  "coverage_gaps": [],
  "domains_queried": ["code", "convo"],
  "total_latency_ms": 4200,
  "trace_id": "7da93f4688c45eb7b4df030a1f1f5847"
}
```

**Partial Success Response:** `207 Multi-Status` → [`FusionResult`](DOMAIN-MODEL.md#fusionresult)

Returned when the fusion pipeline completes but one or more agents failed to respond. The `coverage_gaps` field is non-empty. The response body is identical in structure to the `200` case.

**Error Responses:**

| Code | Error Code           | When                                          |
| ---- | -------------------- | --------------------------------------------- |
| 400  | `INVALID_REQUEST`    | Empty query, invalid `top_k`                  |
| 400  | `QUERY_TOO_LONG`     | Query exceeds max token count                 |
| 401  | `UNAUTHORIZED`       | Invalid bearer token                          |
| 404  | `DOMAIN_NOT_FOUND`   | Explicit domain list contains unknown domains |
| 504  | `AGENT_TIMEOUT`      | All agents timed out                          |
| 429  | `SERVICE_OVERLOADED` | Too many concurrent queries                   |

**Query Lifecycle (internal):**

```
POST /query
  │
  ├── 1. Assign QueryId, start trace span
  ├── 2. Classify query → domain signals
  ├── 3. Resolve agents via registry
  ├── 4. Rewrite query per target domain
  ├── 5. Fan-out RecallRequests (parallel)
  ├── 6. Collect RecallResponses (with timeouts)
  ├── 7. Forward to Fusion Service (POST /fuse)
  └── 8. Return FusionResult to client
```

**Behavior Notes:**

- If `domains` is provided, skip classification and route directly to those domains. This is useful for targeted queries where the caller already knows the relevant domains.
- The router assigns the `QueryId` and `TraceId` at step 1. All downstream calls include both.
- Maximum query length: 4,096 tokens (counted via `tiktoken`). Configurable via `MAX_QUERY_TOKENS`.

---

### GET /health

Same contract as [Memory Agent /health](#get-health). Health checks include:

| Check        | Description                                   |
| ------------ | --------------------------------------------- |
| `registry`   | Can reach the service registry                |
| `classifier` | Classification model is loaded and responsive |

### GET /ready

Same contract as [Memory Agent /ready](#get-ready). Returns `503` if the classifier is not loaded or the registry is unreachable.

---

## Fusion Service API

Internal service called by the router to reconcile multi-agent recall responses.

**Base URL:** `http://fusion:{port}` (default port: `8082`)

### POST /fuse

Execute the six-stage fusion pipeline on a collection of recall responses.

**Request Body:**

| Field               | Type                   | Required | Default   | Description                                     |
| ------------------- | ---------------------- | -------- | --------- | ----------------------------------------------- |
| `query_id`          | `QueryId`              | Yes      | —         | The originating query identifier                |
| `original_text`     | `string`               | Yes      | —         | The original query text (for synthesis context) |
| `responses`         | `list[RecallResponse]` | Yes      | —         | Recall responses from participating agents      |
| `coverage_gaps`     | `list[CoverageGap]`    | No       | `[]`      | Agents that failed to respond                   |
| `conflict_strategy` | `ConflictStrategy`     | No       | `RECENCY` | How to resolve cross-domain contradictions      |
| `synthesize`        | `bool`                 | No       | `false`   | Whether to generate a narrative summary         |
| `trace_id`          | `TraceId`              | Yes      | —         | Distributed trace identifier                    |

```json
{
  "query_id": "d4e5f6a7-...",
  "original_text": "what changed in the payment module after the outage on Jan 15",
  "responses": [
    {
      "query_id": "d4e5f6a7-...",
      "agent_id": "code-memory",
      "domain_id": "code",
      "items": ["..."],
      "total_searched": 1847,
      "latency_ms": 312,
      "trace_id": "..."
    },
    {
      "query_id": "d4e5f6a7-...",
      "agent_id": "convo-memory",
      "domain_id": "convo",
      "items": ["..."],
      "total_searched": 523,
      "latency_ms": 189,
      "trace_id": "..."
    }
  ],
  "coverage_gaps": [],
  "conflict_strategy": "RECENCY",
  "synthesize": true,
  "trace_id": "7da93f4688c45eb7b4df030a1f1f5847"
}
```

**Success Response:** `200 OK` → [`FusionResult`](DOMAIN-MODEL.md#fusionresult)

**Error Responses:**

| Code | Error Code        | When                                    |
| ---- | ----------------- | --------------------------------------- |
| 400  | `INVALID_REQUEST` | Empty responses list, missing query_id  |
| 401  | `UNAUTHORIZED`    | Invalid bearer token                    |
| 500  | `FUSION_FAILED`   | Pipeline failed (embedding error, etc.) |

**Behavior Notes:**

- The fusion service is stateless. It holds no data between requests. All context arrives in the request body.
- If `synthesize` is `true` but the synthesis model times out, the response is returned without a `synthesis` field (set to `null`) rather than failing the entire request.
- Deduplication uses `rapidfuzz` with a similarity threshold of 0.85 (configurable via `DEDUP_SIMILARITY_THRESHOLD`). Items above this threshold are merged, keeping the highest-scoring version and enriching its citation with the duplicate's provenance.

---

### GET /health

Same contract as [Memory Agent /health](#get-health). Health checks include:

| Check | Description                            |
| ----- | -------------------------------------- |
| `llm` | Synthesis model reachable (if enabled) |

### GET /ready

Same contract as [Memory Agent /ready](#get-ready).

---

## Service Registry API

Manages agent discovery and health monitoring.

**Base URL:** `http://registry:{port}` (default port: `8083`)

### POST /agents/register

Register a new memory agent.

**Request Body:**

| Field         | Type     | Required | Description                          |
| ------------- | -------- | -------- | ------------------------------------ |
| `agent_id`    | `string` | Yes      | Unique agent identifier              |
| `base_url`    | `string` | Yes      | Network address for this agent       |
| `health_port` | `int`    | Yes      | Port for health and readiness probes |

```json
{
  "agent_id": "code-memory",
  "base_url": "http://code-memory:8081",
  "health_port": 8081
}
```

**Internal behavior:** The registry immediately calls `GET /describe` on the agent's `base_url` to retrieve its `DomainDescriptor`. This populates the `domain` field of the registration record.

**Success Response:** `201 Created` → [`AgentRegistration`](DOMAIN-MODEL.md#agentregistration)

```json
{
  "agent_id": "code-memory",
  "domain": {
    "domain_id": "code",
    "name": "Source Code",
    "description": "...",
    "chunking_strategy": "SYNTAX_AWARE",
    "embedding_model": "microsoft/codebert-base",
    "embedding_dimensions": 768,
    "document_count": 1247,
    "chunk_count": 42531,
    "last_ingestion_at": "2026-02-16T05:22:00Z"
  },
  "base_url": "http://code-memory:8081",
  "status": "STARTING",
  "registered_at": "2026-02-16T06:37:22Z",
  "last_heartbeat_at": "2026-02-16T06:37:22Z",
  "health_port": 8081
}
```

**Error Responses:**

| Code | Error Code          | When                                |
| ---- | ------------------- | ----------------------------------- |
| 400  | `INVALID_REQUEST`   | Missing required fields             |
| 409  | `REGISTRY_CONFLICT` | Agent ID already registered         |
| 504  | `AGENT_TIMEOUT`     | Could not reach agent's `/describe` |

---

### DELETE /agents/{agent_id}

Deregister a memory agent.

**Path Parameter:** `agent_id` (string)

**Success Response:** `204 No Content`

**Error Responses:**

| Code | Error Code        | When             |
| ---- | ----------------- | ---------------- |
| 404  | `AGENT_NOT_FOUND` | Unknown agent ID |

**Behavior Notes:**

- Publishes an `AgentLifecycleEvent` with `new_status: OFFLINE` to Kafka.
- The router removes the agent from routing candidates on the next registry poll.

---

### GET /agents

List all registered agents.

**Query Parameters:**

| Parameter | Type     | Required | Default | Description                             |
| --------- | -------- | -------- | ------- | --------------------------------------- |
| `status`  | `string` | No       | —       | Filter by `AgentStatus` (e.g., `READY`) |
| `domain`  | `string` | No       | —       | Filter by `DomainId`                    |

**Success Response:** `200 OK`

```json
{
  "agents": [
    { "...AgentRegistration..." },
    { "...AgentRegistration..." }
  ],
  "total": 3
}
```

---

### GET /agents/{agent_id}

Get a single agent's registration record.

**Path Parameter:** `agent_id` (string)

**Success Response:** `200 OK` → [`AgentRegistration`](DOMAIN-MODEL.md#agentregistration)

**Error Responses:**

| Code | Error Code        | When             |
| ---- | ----------------- | ---------------- |
| 404  | `AGENT_NOT_FOUND` | Unknown agent ID |

---

### POST /agents/{agent_id}/heartbeat

Update an agent's last-seen timestamp. Called periodically by agents or by the registry's health-check loop.

**Path Parameter:** `agent_id` (string)

**Request Body:**

| Field    | Type     | Required | Description                         |
| -------- | -------- | -------- | ----------------------------------- |
| `status` | `string` | Yes      | Agent's current `AgentStatus` value |

```json
{
  "status": "READY"
}
```

**Success Response:** `200 OK`

```json
{
  "agent_id": "code-memory",
  "status": "READY",
  "last_heartbeat_at": "2026-02-16T06:42:00Z"
}
```

**Error Responses:**

| Code | Error Code        | When             |
| ---- | ----------------- | ---------------- |
| 404  | `AGENT_NOT_FOUND` | Unknown agent ID |

**Behavior Notes:**

- If no heartbeat is received within `HEARTBEAT_TIMEOUT_SECONDS` (default: 30), the registry marks the agent as `OFFLINE` and publishes an `AgentLifecycleEvent`.
- Heartbeat interval recommendation: every 10 seconds.

---

### GET /health

Same contract as [Memory Agent /health](#get-health). Health checks include:

| Check   | Description                |
| ------- | -------------------------- |
| `db`    | SQLite database accessible |
| `kafka` | Can reach the Kafka broker |

---

## Idempotency

| Endpoint                      | Idempotent | Mechanism                                                                   |
| ----------------------------- | ---------- | --------------------------------------------------------------------------- |
| `POST /recall`                | Yes        | Same `query_id` + `domain_id` returns cached result within a 60s window     |
| `POST /ingest`                | Yes        | `content_hash` deduplication; re-ingesting an identical document is a no-op |
| `POST /query`                 | No         | Each call generates a new `QueryId`                                         |
| `POST /fuse`                  | Yes        | Same `query_id` returns cached result within a 60s window                   |
| `POST /agents/register`       | No         | Duplicate `agent_id` returns `409`                                          |
| `POST /agents/{id}/heartbeat` | Yes        | Timestamp update is inherently idempotent                                   |

---

## Versioning

All APIs are unversioned in the initial release. The version contract is:

1. **Additive changes** (new optional fields, new endpoints) are non-breaking and deployed without version bumps.
2. **Removing or renaming fields** is a breaking change and requires a version prefix (`/v2/recall`).
3. **The `X-NornWeave-Version` response header** communicates the service version. Clients should log this for diagnostics but not branch on it.

---

## Rate Limiting

Rate limiting is enforced at the router level. Individual agents do not implement their own rate limiting.

| Limit                 | Default | Configurable Via         |
| --------------------- | ------- | ------------------------ |
| Queries per second    | 100     | `RATE_LIMIT_QPS`         |
| Concurrent queries    | 50      | `RATE_LIMIT_CONCURRENT`  |
| Ingest requests/min   | 30      | `RATE_LIMIT_INGEST_RPM`  |
| Max request body size | 50 MB   | `MAX_REQUEST_BODY_BYTES` |

Exceeded limits return `429 SERVICE_OVERLOADED` with a `Retry-After` header (in seconds).
