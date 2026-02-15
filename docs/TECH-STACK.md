# NornWeave — Tech Stack Specification

> Comprehensive specification of the technologies, dependencies, tooling, and infrastructure required to build and operate the NornWeave Collaborative Recall Mesh.

---

## Table of Contents

- [Language and Runtime](#language-and-runtime)
- [Project Structure](#project-structure)
- [Core Framework Dependencies](#core-framework-dependencies)
  - [Web Framework and Networking](#web-framework-and-networking)
  - [Configuration and Validation](#configuration-and-validation)
  - [Asynchronous Concurrency](#asynchronous-concurrency)
- [Service Components](#service-components)
  - [Router Agent](#router-agent)
  - [Memory Agent](#memory-agent)
  - [Response Fusion Service](#response-fusion-service)
  - [Service Registry](#service-registry)
- [Storage Layer](#storage-layer)
  - [Vector Store](#vector-store)
  - [Relational Metadata](#relational-metadata)
  - [Event Bus](#event-bus)
- [ML and Embedding Pipeline](#ml-and-embedding-pipeline)
- [Ingestion Pipeline](#ingestion-pipeline)
- [Containerization and Orchestration](#containerization-and-orchestration)
- [Testing](#testing)
  - [Unit Testing](#unit-testing)
  - [Integration Testing](#integration-testing)
  - [End-to-End Testing](#end-to-end-testing)
  - [Load and Benchmark Testing](#load-and-benchmark-testing)
- [Logging and Observability](#logging-and-observability)
  - [Structured Logging](#structured-logging)
  - [Metrics and Tracing](#metrics-and-tracing)
  - [Health Checks](#health-checks)
- [Developer Tooling](#developer-tooling)
  - [Code Quality](#code-quality)
  - [Documentation](#documentation)
  - [CI/CD](#cicd)
- [Security](#security)
- [Dependency Summary](#dependency-summary)

---

## Language and Runtime

| Decision                 | Choice        | Rationale                                                                                                                         |
| ------------------------ | ------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Language**             | Python 3.12+  | Mature ML/NLP ecosystem, first-class async support, strong library coverage for embeddings, vector stores, and LLM orchestration. |
| **Runtime**              | CPython 3.12  | Stable, widely supported, compatible with all target libraries.                                                                   |
| **Package Manager**      | `uv` (Astral) | Fast dependency resolution and lockfile management. Drop-in replacement for pip/pip-tools with dramatically better performance.   |
| **Lockfile**             | `uv.lock`     | Deterministic, reproducible builds across environments.                                                                           |
| **Virtual Environments** | `uv venv`     | Isolated per-project environments managed through uv.                                                                             |

---

## Project Structure

NornWeave uses a **monorepo** layout. Each service is a Python package under `services/`, sharing common libraries from `libs/`.

```
nornweave/
├── README.md
├── LICENSE
├── pyproject.toml              # Workspace root (uv workspace)
├── uv.lock
├── docker-compose.yaml
├── docs/
│   └── TECH-STACK.md
├── agents/                     # Agent YAML configuration files
│   ├── code-memory.yaml
│   ├── docs-memory.yaml
│   └── convo-memory.yaml
├── libs/                       # Shared libraries
│   ├── nornweave-core/         # Domain models, interfaces, protocols
│   │   ├── pyproject.toml
│   │   └── src/nornweave_core/
│   ├── nornweave-storage/      # Storage backend abstractions
│   │   ├── pyproject.toml
│   │   └── src/nornweave_storage/
│   └── nornweave-testing/      # Shared test fixtures and helpers
│       ├── pyproject.toml
│       └── src/nornweave_testing/
├── services/
│   ├── router/                 # Router Agent service
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── src/nornweave_router/
│   ├── fusion/                 # Response Fusion service
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── src/nornweave_fusion/
│   ├── memory-agent/           # Memory Agent service (generic, config-driven)
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── src/nornweave_memory/
│   └── registry/               # Service Registry
│       ├── pyproject.toml
│       ├── Dockerfile
│       └── src/nornweave_registry/
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

---

## Core Framework Dependencies

### Web Framework and Networking

| Dependency   | Version   | Purpose                                                                                                                          |
| ------------ | --------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **FastAPI**  | `>=0.115` | Async REST framework for all service endpoints (`recall`, `ingest`, `health`, `describe`). Automatic OpenAPI spec generation.    |
| **Uvicorn**  | `>=0.34`  | ASGI server. Production deployments via `uvicorn --workers N`.                                                                   |
| **httpx**    | `>=0.28`  | Async HTTP client for inter-service communication (router → agents, fusion ← agents). Connection pooling and timeout management. |
| **Pydantic** | `>=2.10`  | Request/response models, configuration validation, serialization. Already a FastAPI dependency.                                  |

### Configuration and Validation

| Dependency            | Version  | Purpose                                                                                                    |
| --------------------- | -------- | ---------------------------------------------------------------------------------------------------------- |
| **PyYAML**            | `>=6.0`  | Parsing agent YAML configuration files.                                                                    |
| **pydantic-settings** | `>=2.7`  | Environment-variable-aware configuration with YAML overlay. Typed, validated settings objects per service. |
| **jsonschema**        | `>=4.23` | Optional validation of agent configuration files against published schemas.                                |

### Asynchronous Concurrency

| Dependency           | Version | Purpose                                                                                        |
| -------------------- | ------- | ---------------------------------------------------------------------------------------------- |
| **asyncio** (stdlib) | —       | Core event loop for non-blocking I/O.                                                          |
| **anyio**            | `>=4.8` | Structured concurrency primitives (task groups for fan-out, cancellation scopes for timeouts). |

---

## Service Components

### Router Agent

The router classifies incoming queries and produces routing plans.

| Dependency       | Version  | Purpose                                                                                                                      |
| ---------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **scikit-learn** | `>=1.6`  | Lightweight text classification (TF-IDF + logistic regression) for keyword-heuristic routing mode.                           |
| **tiktoken**     | `>=0.8`  | Fast token counting for query analysis and budget enforcement.                                                               |
| **litellm**      | `>=1.60` | (Optional) Unified LLM API proxy for zero-shot classification routing mode. Supports OpenAI, Anthropic, local Ollama models. |

> [!NOTE]
> The router supports three classification backends (selectable via `ROUTER_MODEL`):
>
> 1. `keyword-heuristic` — rule-based, zero-dependency
> 2. `sklearn-classifier` — lightweight ML, requires scikit-learn
> 3. `llm-zero-shot` — LLM-powered, requires litellm

### Memory Agent

The generic, configuration-driven memory agent. The same codebase handles all domains; behavior is determined by the YAML configuration.

| Dependency                   | Version  | Purpose                                                                                                           |
| ---------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------- |
| **sentence-transformers**    | `>=3.4`  | Loading and serving embedding models (e.g., `all-MiniLM-L6-v2`, `code-search-net`).                               |
| **tree-sitter**              | `>=0.24` | Syntax-aware code chunking (AST parsing).                                                                         |
| **tree-sitter-languages**    | `>=1.10` | Pre-built grammars for Python, TypeScript, Go, Rust, Java, C#, etc.                                               |
| **langchain-text-splitters** | `>=0.3`  | Text splitting strategies: `RecursiveCharacterTextSplitter`, `MarkdownHeaderTextSplitter`, token-aware splitting. |
| **psycopg[binary]**          | `>=3.2`  | Async PostgreSQL driver for pgvector interactions.                                                                |
| **pgvector**                 | `>=0.3`  | Python bindings for the pgvector extension (vector similarity search operations).                                 |
| **numpy**                    | `>=2.2`  | Vector arithmetic, similarity computation, array operations.                                                      |

### Response Fusion Service

| Dependency    | Version  | Purpose                                                                           |
| ------------- | -------- | --------------------------------------------------------------------------------- |
| **rapidfuzz** | `>=3.12` | Near-duplicate detection via fuzzy string matching (used in deduplication stage). |
| **litellm**   | `>=1.60` | (Optional) LLM-powered synthesis for narrative answer generation.                 |
| **numpy**     | `>=2.2`  | Composite relevance scoring and cross-domain signal reinforcement math.           |

### Service Registry

| Dependency           | Version   | Purpose                                                                           |
| -------------------- | --------- | --------------------------------------------------------------------------------- |
| **FastAPI**          | `>=0.115` | REST API for agent registration, discovery, and heartbeat management.             |
| **sqlite3** (stdlib) | —         | Lightweight persistent storage for registry state. No external database required. |

---

## Storage Layer

### Vector Store

| Component              | Details                                                                                       |
| ---------------------- | --------------------------------------------------------------------------------------------- |
| **PostgreSQL**         | `16.x` — Primary database engine.                                                             |
| **pgvector extension** | `>=0.8` — Vector similarity search (cosine, L2, inner product) with IVFFlat and HNSW indexes. |
| **Docker Image**       | `pgvector/pgvector:pg16` — Pre-built Postgres with pgvector extension.                        |

**Why pgvector over dedicated vector DBs:** Unified relational + vector store in a single system. Avoid operational overhead of a separate Pinecone/Qdrant/Weaviate cluster. Supports ACID transactions on metadata and vectors together. Well-suited for the initial scope; can be swapped for a dedicated vector DB via the storage backend interface.

### Relational Metadata

Stored in the same PostgreSQL instance as the vectors. Each memory agent gets its own database (e.g., `code`, `docs`, `convo`) for isolation.

| Dependency     | Version  | Purpose                                                                                                        |
| -------------- | -------- | -------------------------------------------------------------------------------------------------------------- |
| **Alembic**    | `>=1.14` | Database migration management. Schema versioning for all pgvector-backed stores.                               |
| **SQLAlchemy** | `>=2.0`  | ORM layer for complex metadata queries. Used alongside raw psycopg for performance-critical vector operations. |

### Event Bus

For cross-agent ingestion event notification (eventual consistency model).

| Dependency          | Version | Purpose                                                                                                                                                 |
| ------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **confluent-kafka** | `>=2.6` | Apache Kafka client for durable, replayable event streaming. Powers ingestion notifications, cross-agent advisory events, and future federated routing. |

**Why Kafka from day one:** NornWeave's eventual consistency model relies on agents publishing ingestion events to a shared bus. Kafka provides durable, ordered, replayable event logs — properties that matter immediately, not just at scale. Consumer groups give each agent independent read positions. Starting with Kafka avoids a migration tax from a simpler pub/sub system later, and `docker compose` makes local Kafka trivial to run via the Confluent or Bitnami images.

---

## ML and Embedding Pipeline

| Dependency                | Version  | Purpose                                                                                    |
| ------------------------- | -------- | ------------------------------------------------------------------------------------------ |
| **torch**                 | `>=2.6`  | Backend for sentence-transformers. CPU-only in development; GPU-accelerated in production. |
| **sentence-transformers** | `>=3.4`  | Embedding model loading, inference, and pooling.                                           |
| **tokenizers**            | `>=0.21` | Fast tokenization (Hugging Face). Transitive dependency of sentence-transformers.          |
| **transformers**          | `>=4.48` | Model hub integration, cross-encoder reranking models.                                     |

**Recommended Embedding Models:**

| Domain                  | Model                                  | Dimensions | Notes                                                  |
| ----------------------- | -------------------------------------- | ---------- | ------------------------------------------------------ |
| Code                    | `microsoft/codebert-base`              | 768        | Trained on code-NL pairs.                              |
| Documentation           | `BAAI/bge-base-en-v1.5`                | 768        | Strong general text embeddings.                        |
| Conversations           | `all-MiniLM-L6-v2`                     | 384        | Lightweight, fast for high-volume conversational data. |
| Cross-encoder reranking | `cross-encoder/ms-marco-MiniLM-L-6-v2` | —          | Pointwise reranker for top-k refinement.               |

---

## Ingestion Pipeline

| Dependency         | Version  | Purpose                                                                               |
| ------------------ | -------- | ------------------------------------------------------------------------------------- |
| **watchfiles**     | `>=1.0`  | Filesystem watching for live ingestion of changed files (git repos, doc directories). |
| **GitPython**      | `>=3.1`  | Git repository traversal, commit history access, diff extraction.                     |
| **beautifulsoup4** | `>=4.12` | HTML parsing for URL-crawl ingestion sources.                                         |
| **httpx**          | `>=0.28` | Async HTTP for web crawling.                                                          |
| **markdownit-py**  | `>=3.0`  | Markdown parsing for hierarchical section chunking.                                   |

---

## Containerization and Orchestration

| Tool                | Version  | Purpose                                                                                         |
| ------------------- | -------- | ----------------------------------------------------------------------------------------------- |
| **Docker**          | `>=27.0` | Container runtime. Multi-stage builds for lean production images.                               |
| **Docker Compose**  | `>=2.32` | Local-first orchestration of the full mesh (router, fusion, registry, agents, pgvector, Kafka). |
| **Docker BuildKit** | enabled  | Cacheable layer builds, multi-stage compilation, secret mounting.                               |

**Base Image Strategy:**

| Stage         | Image                               |
| ------------- | ----------------------------------- |
| Build stage   | `python:3.12-slim`                  |
| Runtime stage | `python:3.12-slim`                  |
| pgvector      | `pgvector/pgvector:pg16`            |
| Kafka         | `confluentinc/cp-kafka:7.7` (KRaft) |

---

## Testing

### Unit Testing

| Dependency         | Version   | Purpose                                                                                |
| ------------------ | --------- | -------------------------------------------------------------------------------------- |
| **pytest**         | `>=8.3`   | Test runner. Discovery, fixtures, parametrize, markers.                                |
| **pytest-asyncio** | `>=0.25`  | Async test support for testing async service methods.                                  |
| **pytest-cov**     | `>=6.0`   | Coverage measurement and reporting.                                                    |
| **pytest-mock**    | `>=3.14`  | `mocker` fixture wrapping `unittest.mock`.                                             |
| **hypothesis**     | `>=6.122` | Property-based testing for edge-case discovery in chunking, routing logic, and fusion. |
| **freezegun**      | `>=1.4`   | Time-freezing for testing recency-based conflict resolution and TTL logic.             |

**Coverage Target:** ≥ 90% line coverage for `libs/` packages, ≥ 80% for `services/`.

**Running unit tests:**

```bash
uv run pytest tests/unit/ -v --cov=src --cov-report=term-missing
```

### Integration Testing

| Dependency         | Version  | Purpose                                                                                 |
| ------------------ | -------- | --------------------------------------------------------------------------------------- |
| **testcontainers** | `>=4.10` | Ephemeral Docker containers for PostgreSQL/pgvector and Kafka during integration tests. |
| **pytest-docker**  | `>=3.1`  | Alternative: Docker Compose-based test fixtures.                                        |
| **httpx**          | `>=0.28` | Async HTTP test client for service-level integration tests.                             |

**Scope:** Verify agent ↔ pgvector interactions, router ↔ agent communication, fusion pipeline with real responses.

```bash
uv run pytest tests/integration/ -v --tb=short
```

### End-to-End Testing

| Dependency               | Version  | Purpose                                                     |
| ------------------------ | -------- | ----------------------------------------------------------- |
| **docker compose** (CLI) | `>=2.32` | Spin up the full mesh for E2E query lifecycle tests.        |
| **httpx**                | `>=0.28` | HTTP client driving E2E scenarios against the running mesh. |

**Scope:** Full query lifecycle — submit a query to the router, verify routing, agent recall, fusion, and final response.

```bash
docker compose -f docker-compose.test.yaml up -d
uv run pytest tests/e2e/ -v
docker compose -f docker-compose.test.yaml down
```

### Load and Benchmark Testing

| Dependency           | Version  | Purpose                                                                                        |
| -------------------- | -------- | ---------------------------------------------------------------------------------------------- |
| **locust**           | `>=2.32` | Load testing the router and memory agents under concurrent query pressure.                     |
| **pytest-benchmark** | `>=5.1`  | Micro-benchmarks for chunking strategies, embedding throughput, and similarity search latency. |

```bash
# Benchmark tests
uv run pytest tests/benchmarks/ --benchmark-only

# Load tests
uv run locust -f tests/load/locustfile.py --host http://localhost:8080
```

---

## Logging and Observability

### Structured Logging

| Dependency             | Version  | Purpose                                                                                             |
| ---------------------- | -------- | --------------------------------------------------------------------------------------------------- |
| **structlog**          | `>=24.4` | Structured, JSON-formatted logging with context binding. Consistent log schema across all services. |
| **python-json-logger** | `>=3.2`  | JSON formatter for stdlib `logging` integration where structlog is not directly used.               |

**Log Schema (enforced across all services):**

```json
{
  "timestamp": "2026-02-15T23:26:29Z",
  "level": "info",
  "service": "router",
  "event": "query_routed",
  "query_id": "uuid",
  "domains": ["code", "docs"],
  "latency_ms": 12,
  "trace_id": "abc123"
}
```

**Log Levels:**

- `DEBUG` — Internal state transitions, retrieved chunk details.
- `INFO` — Query lifecycle events (received, routed, recalled, fused, delivered).
- `WARNING` — Agent timeouts, low confidence routing, near-threshold scores.
- `ERROR` — Storage failures, agent crashes, unrecoverable fusion errors.

### Metrics and Tracing

| Dependency                                 | Version   | Purpose                                                     |
| ------------------------------------------ | --------- | ----------------------------------------------------------- |
| **opentelemetry-api**                      | `>=1.30`  | Vendor-neutral distributed tracing API.                     |
| **opentelemetry-sdk**                      | `>=1.30`  | SDK implementation for span collection and export.          |
| **opentelemetry-instrumentation-fastapi**  | `>=0.51b` | Auto-instrumentation for FastAPI endpoints.                 |
| **opentelemetry-instrumentation-httpx**    | `>=0.51b` | Auto-instrumentation for inter-service HTTP calls.          |
| **opentelemetry-exporter-otlp-proto-grpc** | `>=1.30`  | OTLP exporter for tracing backends (Jaeger, Grafana Tempo). |
| **prometheus-fastapi-instrumentator**      | `>=7.0`   | Prometheus metrics endpoint (`/metrics`) for each service.  |

**Key Metrics:**

- `nornweave_queries_total` — Counter by service, domain, status.
- `nornweave_query_latency_seconds` — Histogram for query lifecycle stages.
- `nornweave_agent_recall_items` — Histogram of result counts per recall.
- `nornweave_fusion_conflicts_total` — Counter of cross-domain conflicts.
- `nornweave_embedding_latency_seconds` — Histogram for embedding inference time.
- `nornweave_index_size_documents` — Gauge per agent/domain.

### Health Checks

Every service exposes:

| Endpoint       | Purpose                                                                                                     |
| -------------- | ----------------------------------------------------------------------------------------------------------- |
| `GET /health`  | Liveness probe — returns 200 if the process is running.                                                     |
| `GET /ready`   | Readiness probe — returns 200 only when the service is ready to serve traffic (DB connected, model loaded). |
| `GET /metrics` | Prometheus-scrapeable metrics.                                                                              |

---

## Developer Tooling

### Code Quality

| Tool           | Version  | Purpose                                                                                        |
| -------------- | -------- | ---------------------------------------------------------------------------------------------- |
| **ruff**       | `>=0.9`  | Linting and formatting (replaces flake8, isort, black). Single tool for all style enforcement. |
| **mypy**       | `>=1.14` | Static type checking. Strict mode enabled for `libs/`, standard mode for `services/`.          |
| **pre-commit** | `>=4.1`  | Git hooks for ruff, mypy, and commit message linting.                                          |
| **pyright**    | `>=1.1`  | (Optional) Secondary type checker for IDE integration (VS Code / Pylance).                     |

**Configuration (in `pyproject.toml`):**

```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "S", "B", "A", "C4", "SIM", "TCH"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
```

### Documentation

| Tool                     | Version  | Purpose                                                           |
| ------------------------ | -------- | ----------------------------------------------------------------- |
| **MkDocs**               | `>=1.6`  | Project documentation site generation.                            |
| **mkdocs-material**      | `>=9.5`  | Material theme with search, navigation tabs, and code annotation. |
| **mkdocstrings[python]** | `>=0.27` | Auto-generate API reference from docstrings.                      |

### CI/CD

| Tool                  | Purpose                                                                                  |
| --------------------- | ---------------------------------------------------------------------------------------- |
| **GitHub Actions**    | CI pipeline: lint → type-check → unit test → integration test → Docker build → E2E test. |
| **Docker Build/Push** | Container image publication to GitHub Container Registry (ghcr.io).                      |
| **Dependabot**        | Automated dependency update PRs.                                                         |

**Recommended CI Pipeline Stages:**

```
┌──────────┐   ┌────────────┐   ┌───────────┐   ┌─────────┐   ┌──────────┐
│   Lint   │──▶│ Type Check │──▶│ Unit Test │──▶│  Build  │──▶│ Int Test │
│  (ruff)  │   │   (mypy)   │   │ (pytest)  │   │(Docker) │   │(testcont)│
└──────────┘   └────────────┘   └───────────┘   └─────────┘   └──────────┘
                                                                     │
                                                                     ▼
                                                               ┌──────────┐
                                                               │ E2E Test │
                                                               │(compose) │
                                                               └──────────┘
```

---

## Security

| Concern                 | Approach                                                                                                                 |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Secret Management**   | Environment variables injected via Docker secrets or `.env` files (never committed). `pydantic-settings` reads from env. |
| **Inter-Service Auth**  | Shared bearer token for service-to-service calls (initial). Upgrade path to mTLS for production.                         |
| **Input Validation**    | Pydantic models on all API boundaries. Maximum query length, injection-safe parameterized SQL.                           |
| **Dependency Auditing** | `pip-audit>=2.7` in CI for known vulnerability detection.                                                                |
| **Container Hardening** | Non-root user in Dockerfiles, read-only filesystem where possible, minimal base images.                                  |

---

## Dependency Summary

A consolidated view of all top-level dependencies, grouped by concern.

### Runtime Dependencies

| Package                                  | Min Version | Used By                                |
| ---------------------------------------- | ----------- | -------------------------------------- |
| `fastapi`                                | 0.115       | Router, Memory Agent, Fusion, Registry |
| `uvicorn`                                | 0.34        | All services                           |
| `httpx`                                  | 0.28        | Router, Fusion, Ingestion              |
| `pydantic`                               | 2.10        | All services                           |
| `pydantic-settings`                      | 2.7         | All services                           |
| `pyyaml`                                 | 6.0         | All services                           |
| `anyio`                                  | 4.8         | Router, Fusion                         |
| `structlog`                              | 24.4        | All services                           |
| `opentelemetry-api`                      | 1.30        | All services                           |
| `opentelemetry-sdk`                      | 1.30        | All services                           |
| `opentelemetry-instrumentation-fastapi`  | 0.51b       | All services                           |
| `opentelemetry-instrumentation-httpx`    | 0.51b       | Router, Fusion                         |
| `opentelemetry-exporter-otlp-proto-grpc` | 1.30        | All services                           |
| `prometheus-fastapi-instrumentator`      | 7.0         | All services                           |
| `psycopg[binary]`                        | 3.2         | Memory Agent                           |
| `pgvector`                               | 0.3         | Memory Agent                           |
| `numpy`                                  | 2.2         | Memory Agent, Fusion                   |
| `sentence-transformers`                  | 3.4         | Memory Agent                           |
| `torch`                                  | 2.6         | Memory Agent                           |
| `transformers`                           | 4.48        | Memory Agent                           |
| `tree-sitter`                            | 0.24        | Memory Agent (code domain)             |
| `tree-sitter-languages`                  | 1.10        | Memory Agent (code domain)             |
| `langchain-text-splitters`               | 0.3         | Memory Agent                           |
| `scikit-learn`                           | 1.6         | Router (sklearn mode)                  |
| `tiktoken`                               | 0.8         | Router                                 |
| `litellm`                                | 1.60        | Router (LLM mode), Fusion (synthesis)  |
| `rapidfuzz`                              | 3.12        | Fusion                                 |
| `confluent-kafka`                        | 2.6         | Event Bus                              |
| `watchfiles`                             | 1.0         | Ingestion pipeline                     |
| `gitpython`                              | 3.1         | Ingestion pipeline                     |
| `beautifulsoup4`                         | 4.12        | Ingestion pipeline (URL crawl)         |
| `markdownit-py`                          | 3.0         | Ingestion pipeline                     |
| `alembic`                                | 1.14        | Storage migrations                     |
| `sqlalchemy`                             | 2.0         | Storage metadata                       |

### Development Dependencies

| Package                | Min Version | Purpose                     |
| ---------------------- | ----------- | --------------------------- |
| `pytest`               | 8.3         | Test runner                 |
| `pytest-asyncio`       | 0.25        | Async test support          |
| `pytest-cov`           | 6.0         | Coverage                    |
| `pytest-mock`          | 3.14        | Mocking                     |
| `pytest-benchmark`     | 5.1         | Microbenchmarks             |
| `hypothesis`           | 6.122       | Property-based testing      |
| `freezegun`            | 1.4         | Time mocking                |
| `testcontainers`       | 4.10        | Ephemeral Docker containers |
| `locust`               | 2.32        | Load testing                |
| `ruff`                 | 0.9         | Lint and format             |
| `mypy`                 | 1.14        | Type checking               |
| `pre-commit`           | 4.1         | Git hooks                   |
| `pip-audit`            | 2.7         | Vulnerability scanning      |
| `mkdocs`               | 1.6         | Documentation               |
| `mkdocs-material`      | 9.5         | Docs theme                  |
| `mkdocstrings[python]` | 0.27        | API docs                    |

### Infrastructure

| Component             | Image / Version             | Purpose                             |
| --------------------- | --------------------------- | ----------------------------------- |
| PostgreSQL + pgvector | `pgvector/pgvector:pg16`    | Vector and relational storage       |
| Apache Kafka          | `confluentinc/cp-kafka:7.7` | Event bus (ingestion notifications) |
| Docker                | ≥ 27.0                      | Container runtime                   |
| Docker Compose        | ≥ 2.32                      | Local orchestration                 |

---

## Version Pinning Policy

- **Lock all dependencies** in `uv.lock` for reproducible builds.
- **Specify minimum versions** in `pyproject.toml` (e.g., `fastapi>=0.115`).
- **Pin infrastructure images** by major version tag (e.g., `pgvector:pg16`, `redis:7-alpine`).
- **Renovate or Dependabot** for automated dependency update PRs on a weekly cadence.

---

## License Compatibility

All listed dependencies are compatible with the project's **GPL-3.0** license. Notable license types in the dependency tree:

| License    | Packages                                                                          |
| ---------- | --------------------------------------------------------------------------------- |
| MIT        | FastAPI, Uvicorn, httpx, Pydantic, structlog, sentence-transformers, ruff, pytest |
| BSD        | NumPy, scikit-learn, psycopg, SQLAlchemy                                          |
| Apache 2.0 | OpenTelemetry, transformers, torch, tiktoken                                      |
| PostgreSQL | pgvector                                                                          |
