# NornWeave — Feature Roadmap

> The rough journey from "it compiles" to "it remembers everything." Each milestone builds on the last; no version is skippable. Think of it as a tech tree, not a wish list.

---

## Version Philosophy

NornWeave's roadmap follows three rules:

1. **Vertical slices over horizontal layers.** Every milestone produces something you can actually run, not just a library that theoretically works.
2. **One agent before many.** We prove the single-agent recall loop end-to-end before introducing multi-agent coordination.
3. **Hard problems last.** Conflict resolution, adaptive routing, and synthesis are deferred until the boring plumbing is battle-tested.

---

## Phase Overview

```
 v0.0.x    Foundation          Monorepo, models, storage, health checks
 v0.1.x    Single-Agent Loop   One memory agent, ingestion → recall
 v0.2.x    Router + Fan-Out    Multi-agent routing, parallel recall
 v0.3.x    Fusion + Mesh       Dedup, conflicts, ranking, synthesis
 v0.4.x    Production Harden   Observability, scaling, security, CI/CD
 v0.5.x–   Polish + Extend     Dynamic domains, adaptive routing, federation
 v1.0.0    General Availability Stable APIs, documented, fully tested
```

---

## Phase 1 — Foundation (v0.0.x)

> _Build the skeleton. Nothing moves yet, but everything has a shape._

### v0.0.1 — Project Scaffold

**Goal:** Monorepo structure, tooling, and shared library stubs.

- [ ] Initialize `uv` workspace with root `pyproject.toml`
- [ ] Create `libs/nornweave-core`, `libs/nornweave-storage`, `libs/nornweave-testing` package stubs
- [ ] Create `services/router`, `services/fusion`, `services/memory-agent`, `services/registry` package stubs
- [ ] Configure `ruff`, `mypy`, `pre-commit` hooks
- [ ] Set up `pytest` with `tests/unit/`, `tests/integration/`, `tests/e2e/` directories
- [ ] Add `docker-compose.yaml` with pgvector and Kafka services (infra only, no app services)
- [ ] Write initial `CHANGELOG.md`

**Milestone:** `uv run pytest` passes (even if there are zero tests). `docker compose up -d` starts pgvector and Kafka.

---

### v0.0.2 — Domain Model (nornweave-core)

**Goal:** Implement the canonical domain model from `DOMAIN-MODEL.md`.

- [ ] Implement all typed identifiers (`QueryId`, `DomainId`, `AgentId`, `DocumentId`, `ChunkId`, `TraceId`)
- [ ] Implement enumerations (`DomainType`, `AgentStatus`, `ConflictStrategy`, `ChunkingStrategy`, `IngestStatus`)
- [ ] Implement value objects (`RelevanceScore`, `EmbeddingVector`, `SourceCitation`, `DomainSignal`, `CoverageGap`, `ConflictRecord`, `TokenBudget`)
- [ ] Implement core entities (`Document`, `Chunk`, `DomainDescriptor`, `AgentRegistration`)
- [ ] Implement request/response models (`RecallRequest`, `RecallResponse`, `RecallItem`, `RoutingPlan`, `RoutingTarget`, `IngestRequest`, `IngestResult`, `FusionResult`, `HealthStatus`)
- [ ] Implement event types (`IngestionEvent`, `AgentLifecycleEvent`)
- [ ] JSON Schema export tests for every model
- [ ] ≥ 95% coverage on `nornweave-core`

**Milestone:** All domain model types serialize/deserialize cleanly. `model.model_json_schema()` produces valid JSON Schema for every model.

---

### v0.0.3 — Storage Abstraction (nornweave-storage)

**Goal:** Repository layer for documents and chunks against pgvector.

- [ ] Implement `DocumentRepository` (CRUD, content-hash dedup check)
- [ ] Implement `ChunkRepository` (bulk insert, vector similarity search)
- [ ] Alembic migration framework with initial schema (`documents`, `chunks` tables)
- [ ] `ivfflat` index creation on chunk embeddings
- [ ] Connection pooling via `psycopg` async pool
- [ ] Integration tests using `testcontainers` (ephemeral pgvector)

**Milestone:** Integration tests pass — insert a document, chunk it, store embeddings, retrieve by vector similarity.

---

### v0.0.4 — Event Bus Foundation

**Goal:** Kafka producer/consumer wrappers with the standard envelope format.

- [ ] Implement `EventPublisher` (fire-and-forget, envelope wrapping, graceful Kafka-down handling)
- [ ] Implement `EventConsumer` (consumer group, deserialization, idempotency via `event_id` dedup)
- [ ] Topic initialization script (`nornweave.ingestion.events`, `nornweave.agent.lifecycle`, `nornweave.routing.feedback`, `dlq`)
- [ ] Dead-letter queue routing for poison messages
- [ ] Integration tests using `testcontainers` (ephemeral Kafka)

**Milestone:** Publish an `IngestionEvent`, consume it in a test consumer, verify envelope structure and idempotent processing.

---

## Phase 2 — Single-Agent Loop (v0.1.x)

> _One agent, one domain, end-to-end. If this doesn't work, nothing else matters._

### v0.1.0 — Memory Agent: Ingestion Pipeline

**Goal:** A single memory agent can ingest documents, chunk them, embed them, and store them.

- [ ] FastAPI service skeleton (`main.py`, lifespan hooks, health/ready/describe endpoints)
- [ ] Agent configuration loader (YAML `domain.yaml` + `pydantic-settings` env overlay)
- [ ] Ingestion pipeline orchestrator (validate → deduplicate → chunk → embed → store → publish event)
- [ ] `RECURSIVE_CHARACTER` chunking strategy (the universal fallback)
- [ ] Embedding client wrapper (load `all-MiniLM-L6-v2` via sentence-transformers, batch inference)
- [ ] Dockerfile for memory-agent service
- [ ] Unit tests for each pipeline stage
- [ ] Integration test: ingest a Markdown file, verify chunks + embeddings land in pgvector

**Milestone:** `POST /ingest` with a Markdown document returns `202 Accepted`. Chunks appear in the database with valid embeddings.

---

### v0.1.1 — Memory Agent: Recall Pipeline

**Goal:** The same agent can search its stored chunks and return ranked results.

- [ ] Recall pipeline orchestrator (embed query → vector search → rerank → build response)
- [ ] pgvector cosine similarity searcher with overfetch factor
- [ ] Domain-heuristic reranker (no cross-encoder yet — heuristic-only for speed)
- [ ] `RecallResponse` construction with `SourceCitation` provenance
- [ ] Unit tests for recall pipeline
- [ ] Integration test: ingest docs, then recall against them, verify relevance ordering

**Milestone:** `POST /recall` with a query returns ranked `RecallItem[]` with valid citations. The right chunks surface for known queries.

---

### v0.1.2 — Service Registry

**Goal:** Agents can register, heartbeat, and be discovered.

- [ ] FastAPI service for the registry
- [ ] `POST /agents/register`, `POST /agents/{id}/heartbeat`, `GET /agents`, `GET /agents/{id}`
- [ ] SQLite-backed persistent storage
- [ ] Heartbeat timeout detection (mark agents `OFFLINE` after missed heartbeats)
- [ ] Consume `AgentLifecycleEvent` from Kafka for status updates
- [ ] Agent startup auto-registration
- [ ] Unit + integration tests

**Milestone:** Start a memory agent, verify it appears in `GET /agents` as `READY`. Stop it, verify it transitions to `OFFLINE`.

---

### v0.1.3 — Domain-Specific Chunking

**Goal:** Implement the three remaining chunking strategies beyond `RECURSIVE_CHARACTER`.

- [ ] `SYNTAX_AWARE` chunker (tree-sitter, code boundary detection, AST metadata extraction)
- [ ] `HIERARCHICAL_SECTIONS` chunker (Markdown heading-aware splitting, heading path metadata)
- [ ] `MESSAGE_BOUNDARY` chunker (conversational message splitting with context window)
- [ ] Chunking strategy selection from `domain.yaml` configuration
- [ ] Unit tests for each strategy with representative documents
- [ ] Property-based tests (Hypothesis) for chunk boundary correctness

**Milestone:** Each chunking strategy produces well-formed chunks with correct metadata for its domain type.

---

### v0.1.4 — Cross-Encoder Reranking

**Goal:** Upgrade recall quality with a real cross-encoder reranker.

- [ ] Cross-encoder model loading (`cross-encoder/ms-marco-MiniLM-L-6-v2`)
- [ ] Two-stage retrieval: vector search (stage 1) → cross-encoder rerank (stage 2)
- [ ] Domain-specific heuristic bonuses (symbol match, heading match, recency, authority)
- [ ] Weighted score combination: `final = model × 0.7 + heuristic × 0.3`
- [ ] Configurable reranker fallback (model unavailable → heuristic-only)
- [ ] Benchmark tests comparing heuristic-only vs cross-encoder recall quality

**Milestone:** Cross-encoder reranking demonstrably improves result quality over heuristic-only in benchmark tests.

---

## Phase 3 — Router + Fusion (v0.2.x)

> _Multiple agents, one brain. This is where NornWeave starts weaving._

### v0.2.0 — Router Agent: Keyword-Heuristic Backend

**Goal:** A router that classifies queries and fans them out to the right agents.

- [ ] FastAPI service skeleton for the router
- [ ] `POST /query` endpoint (client-facing entry point)
- [ ] `keyword-heuristic` classification backend (rule-based, domain keyword dictionaries)
- [ ] Multi-target routing (single query → multiple agents)
- [ ] Query rewriting per domain (extract symbols for code, date ranges for convo, etc.)
- [ ] Threshold filtering (discard low-relevance domains)
- [ ] Registry integration (discover available agents via `GET /agents`)
- [ ] Parallel fan-out to agents via `httpx` async client with task groups
- [ ] Timeout handling per agent (configurable deadline)
- [ ] Unit tests for classification and rewriting logic

**Milestone:** Submit a multi-domain query to `POST /query`. Router correctly classifies it and dispatches `RecallRequest` to multiple running agents.

---

### v0.2.1 — Router Agent: Sklearn + LLM Backends

**Goal:** Smarter classification for staging and production deployments.

- [ ] `sklearn-classifier` backend (TF-IDF + logistic regression)
- [ ] Training data pipeline (synthetic query template generation + labeling)
- [ ] Model serialization/loading (joblib)
- [ ] `llm-zero-shot` backend via `litellm` (structured JSON output, fallback model)
- [ ] Backend selection logic (configurable via `ROUTER_MODEL`)
- [ ] Comparison benchmarks across all three backends

**Milestone:** All three routing backends produce valid `RoutingPlan` objects. Sklearn and LLM backends demonstrably outperform keyword-heuristic on ambiguous queries.

---

### v0.2.2 — Fusion Service: Collection, Normalization, Deduplication (Stages 1–3)

**Goal:** The first half of the fusion pipeline — gather, normalize, and deduplicate results.

- [ ] FastAPI service skeleton for fusion
- [ ] `POST /fuse` endpoint
- [ ] Stage 1: Collection (gather `RecallResponse[]`, build `TaggedItem[]`, record `CoverageGap[]`)
- [ ] Stage 2: Normalization (per-agent min-max score normalization)
- [ ] Stage 3: Deduplication (fuzzy text matching via `rapidfuzz`, configurable threshold, citation enrichment)
- [ ] Unit tests for each stage with the worked example from `FUSION-PIPELINE.md`

**Milestone:** Given raw `RecallResponse` objects from multiple agents, the fusion service produces deduplicated, score-normalized results.

---

### v0.2.3 — Fusion Service: Conflict Resolution + Ranking (Stages 4–5)

**Goal:** Detect contradictions, resolve or flag them, and produce a final ranked result set.

- [ ] Stage 4: Conflict detection (same-entity divergence, temporal contradiction, negation patterns)
- [ ] Stage 4: All five resolution strategies (`RECENCY`, `SOURCE_AUTHORITY`, `CONFIDENCE`, `FLAG`, `RECENCY_THEN_FLAG`)
- [ ] Stage 4: Query-type inference for `SOURCE_AUTHORITY` ordering
- [ ] Stage 5: Multi-signal ranking (normalized score, corroboration, recency, domain relevance, content length)
- [ ] Tie-breaking logic
- [ ] `FusionResult` assembly with `conflicts[]` and `coverage_gaps[]`
- [ ] Unit tests for each conflict strategy with known-conflict scenarios

**Milestone:** Submit a query that triggers cross-domain conflicts. Verify correct conflict detection, resolution, and final ranking.

---

### v0.2.4 — Fusion Service: Synthesis (Stage 6)

**Goal:** Optional narrative answer generation from ranked results.

- [ ] Stage 6: Synthesis prompt construction (top-k items, citations, conflict annotations)
- [ ] `litellm` integration for synthesis LLM call (primary + fallback model)
- [ ] Graceful degradation (synthesis timeout → return ranked results without narrative)
- [ ] `synthesize=true/false` toggle on the query API
- [ ] E2E integration test: full query lifecycle from router → agents → fusion → synthesis

**Milestone:** A query with `synthesize=true` returns a `FusionResult` with a coherent narrative `synthesis` field that cites sources.

---

### v0.2.5 — Docker Compose Full Mesh

**Goal:** `docker compose up -d` brings up the entire NornWeave mesh.

- [ ] Dockerfiles for all four services (router, fusion, memory-agent, registry)
- [ ] `docker-compose.yaml` with all services, pgvector, Kafka
- [ ] Multi-agent configuration (code-memory, docs-memory, convo-memory using same image, different configs)
- [ ] Health check dependencies (services wait for infra readiness)
- [ ] `.env.example` with all required environment variables
- [ ] Smoke test script that ingests sample documents, runs a query, and verifies a complete `FusionResult`

**Milestone:** `docker compose up -d` → run smoke test → get a valid multi-domain fused response. The README demo works.

---

## Phase 4 — Production Hardening (v0.3.x)

> _It works. Now make it work reliably, observably, and securely._

### v0.3.0 — Structured Logging + Distributed Tracing

**Goal:** Full observability across the query lifecycle.

- [ ] `structlog` integration across all services (JSON output, context binding)
- [ ] Consistent log schema enforcement (service, event, query_id, trace_id, latency_ms)
- [ ] OpenTelemetry instrumentation (FastAPI auto-instrumentation, httpx auto-instrumentation)
- [ ] Trace propagation across router → agents → fusion (W3C Trace Context)
- [ ] OTLP exporter configuration for Jaeger/Grafana Tempo
- [ ] Prometheus metrics endpoints (`/metrics`) on every service
- [ ] Key metrics: `queries_total`, `query_latency_seconds`, `recall_items`, `fusion_conflicts_total`, `embedding_latency_seconds`, `index_size_documents`

**Milestone:** A query produces a complete distributed trace visible in Jaeger. Prometheus scrapes all service metrics.

---

### v0.3.1 — Security Hardening

**Goal:** Production-grade authentication, input validation, and container security.

- [ ] Inter-service bearer token authentication on all endpoints
- [ ] Input validation hardening (max query length, parameterized SQL, injection prevention)
- [ ] Container hardening (non-root user, read-only filesystem, minimal base images)
- [ ] `pip-audit` in CI for vulnerability scanning
- [ ] Secret management documentation (Docker secrets, `.env` files)

**Milestone:** `pip-audit` passes with zero known vulnerabilities. Services reject unauthenticated requests.

---

### v0.3.2 — CI/CD Pipeline

**Goal:** Automated quality gates from commit to container image.

- [ ] GitHub Actions workflow: lint → type-check → unit test → integration test → Docker build → E2E test
- [ ] Coverage enforcement (≥ 90% for `libs/`, ≥ 80% for `services/`)
- [ ] Container image publication to GitHub Container Registry (ghcr.io)
- [ ] Dependabot configuration for automated dependency updates
- [ ] MkDocs documentation site generation

**Milestone:** Every push triggers the full pipeline. PRs cannot merge without green CI.

---

### v0.3.3 — Load Testing + Performance Tuning

**Goal:** Validate performance characteristics and identify bottleneck thresholds.

- [ ] Locust load test suite (concurrent queries, sustained ingestion)
- [ ] Benchmark suite for chunking strategies, embedding throughput, vector search latency
- [ ] pgvector index tuning (ivfflat → hnsw transition thresholds)
- [ ] Connection pool sizing and timeout tuning
- [ ] Performance baseline documentation

**Milestone:** Published performance baseline. System handles N concurrent queries within documented latency bounds.

---

## Phase 5 — Polish + Extend (v0.4.x – v0.5.x)

> _From "it works" to "it works well." Smarter routing, richer recall, broader reach._

### v0.4.0 — Research Memory Agent

**Goal:** Fourth default domain agent for academic and external research content.

- [ ] `HIERARCHICAL_SECTIONS` chunker with academic extensions (abstract, methodology, references)
- [ ] PDF ingestion via `pymupdf` with section detection
- [ ] Stack Overflow Q&A ingestion
- [ ] Authority-weighted reranker (citation count, venue prestige)
- [ ] Agent configuration (`research-memory.yaml`)
- [ ] Docker Compose integration (fifth agent service)

**Milestone:** Ingest an arXiv paper and a Stack Overflow answer. Recall returns high-authority results with citation metadata.

---

### v0.4.1 — Live Ingestion (File Watchers)

**Goal:** Automatic re-ingestion when source files change.

- [ ] `watchfiles` integration for filesystem monitoring (git repos, doc directories)
- [ ] Change detection via content hash comparison
- [ ] Incremental re-chunking and re-embedding of changed documents
- [ ] Git repository traversal via `GitPython` (new commits → new/changed files)
- [ ] URL-crawl refresh on configurable intervals

**Milestone:** Edit a source file → agent automatically re-ingests → updated chunks appear in recall results.

---

### v0.4.2 — Adaptive Routing (Feedback Loop)

**Goal:** The router learns from fusion outcomes to improve classification over time.

- [ ] `RoutingFeedbackEvent` consumption by the router
- [ ] Routing quality scoring (was the domain's contribution useful?)
- [ ] Keyword weight adjustment based on feedback signals
- [ ] Sklearn classifier online retraining from accumulated feedback
- [ ] Routing precision metrics (before/after feedback loop)

**Milestone:** After N queries with feedback, the router demonstrably reduces misclassification rate.

---

### v0.5.0 — Inter-Agent Cross-References

**Goal:** Memory agents can reference each other's content by ID for richer fusion.

- [ ] Cross-reference metadata in chunk storage (links to related chunks in other domains)
- [ ] Fusion pipeline enrichment (follow cross-references during ranking)
- [ ] Cross-domain link surfacing in `FusionResult` (e.g., code function → its API doc → the conversation where it was designed)

**Milestone:** A query returns results that explicitly link related information across domains.

---

### v0.5.1 — Dynamic Domain Splitting

**Goal:** Automatic domain split proposals when an agent exceeds performance thresholds.

- [ ] Index size monitoring and threshold detection
- [ ] Domain split analysis (suggest new domains based on content clustering)
- [ ] Split execution (create new agent, redistribute chunks)
- [ ] Router and registry automatic adaptation

**Milestone:** A code agent exceeding 100k chunks proposes splitting into "backend-code" and "frontend-code" agents.

---

## Phase 6 — General Availability (v1.0.0)

> _The mesh is woven. Ship it._

### v1.0.0 — GA Release

**Goal:** Stable, documented, production-ready release.

- [ ] Stable API contracts (no breaking changes post-1.0 without major version bump)
- [ ] Comprehensive MkDocs documentation site (architecture, deployment, configuration, API reference)
- [ ] Quickstart guide (5-minute setup from `git clone` to first query)
- [ ] Performance and scaling guide
- [ ] All design specs verified against implementation (no spec drift)
- [ ] Full test suite: unit (≥ 90%/80% coverage), integration, E2E, load
- [ ] `CHANGELOG.md` covering all versions from v0.0.1
- [ ] Published Docker images on ghcr.io
- [ ] Release blog post / announcement

**Milestone:** A new user can `git clone`, `docker compose up -d`, ingest their codebase, and get multi-domain recall responses within 30 minutes.

---

## Post-1.0 Future Directions

These are the "someday" items from the README's [Future Directions](../README.md#future-directions), deliberately excluded from the 1.0 scope:

| Feature                     | Why it's post-1.0                                                                   |
| --------------------------- | ----------------------------------------------------------------------------------- |
| **Federated Deployments**   | Mesh-of-meshes requires stable single-mesh semantics first                          |
| **Active Forgetting**       | Decay functions need production data to calibrate; premature optimization otherwise |
| **Custom Embedding Models** | Pluggable, but initial defaults cover the 80% case                                  |
| **mTLS**                    | Bearer tokens are sufficient for initial deployments; mTLS is the upgrade path      |
| **GPU Acceleration**        | CPU-only is fine for development; GPU support is a deployment concern               |

---

## Version Summary

| Version | Codename                  | Key Deliverable                                |
| ------- | ------------------------- | ---------------------------------------------- |
| v0.0.1  | Scaffold                  | Monorepo structure, tooling, infra-only Docker |
| v0.0.2  | Vocabulary                | Canonical domain model library                 |
| v0.0.3  | Basement                  | Storage layer with pgvector                    |
| v0.0.4  | Wires                     | Kafka event bus foundation                     |
| v0.1.0  | First Breath              | Single-agent ingestion pipeline                |
| v0.1.1  | First Word                | Single-agent recall pipeline                   |
| v0.1.2  | Roll Call                 | Service registry                               |
| v0.1.3  | Specialist                | Domain-specific chunking strategies            |
| v0.1.4  | Sharp Eyes                | Cross-encoder reranking                        |
| v0.2.0  | Traffic Cop               | Router with keyword-heuristic backend          |
| v0.2.1  | Street Smart              | Sklearn + LLM routing backends                 |
| v0.2.2  | Gather Round              | Fusion stages 1–3 (collect, normalize, dedup)  |
| v0.2.3  | Judge and Jury            | Fusion stages 4–5 (conflicts, ranking)         |
| v0.2.4  | Storyteller               | Fusion stage 6 (narrative synthesis)           |
| v0.2.5  | Full Assembly             | Docker Compose complete mesh                   |
| v0.3.0  | X-Ray Vision              | Observability (logging, tracing, metrics)      |
| v0.3.1  | Lock and Key              | Security hardening                             |
| v0.3.2  | Assembly Line             | CI/CD pipeline                                 |
| v0.3.3  | Stress Test               | Load testing + performance tuning              |
| v0.4.0  | Scholar                   | Research memory agent                          |
| v0.4.1  | Always Watching           | Live file ingestion                            |
| v0.4.2  | Street Smart (Upgraded)   | Adaptive routing feedback loop                 |
| v0.5.0  | Connected                 | Inter-agent cross-references                   |
| v0.5.1  | Mitosis                   | Dynamic domain splitting                       |
| v1.0.0  | **The Tapestry is Woven** | General availability                           |
