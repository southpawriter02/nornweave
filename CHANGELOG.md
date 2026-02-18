# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.3] - 2026-02-17

### Added

- Storage abstraction layer in `nornweave-storage` (repositories, connection pool, Alembic migrations).
- `DatabaseConfig` — pydantic-settings config with `NORNWEAVE_DB_*` env vars.
- `ConnectionPool` — async psycopg3 pool wrapper with automatic pgvector type registration.
- `DocumentRepository` — async CRUD: create, get_by_id, get_by_content_hash, list_by_domain, update, delete, count_by_domain.
- `ChunkRepository` — async CRUD + vector search: bulk_create, get_by_id, get_by_document_id, search_similar (cosine), delete_by_document_id, count_by_domain.
- `DocumentMapper` / `ChunkMapper` — bidirectional domain model ↔ DB row conversion with numpy float32 embedding arrays.
- Alembic migration `001_initial_schema` — documents + chunks tables, pgvector extension, IVFFlat cosine index.
- Storage error hierarchy: `StorageError`, `StorageConnectionError`, `DocumentNotFoundError`, `ChunkNotFoundError`, `DuplicateDocumentError`, `IntegrityError`.
- 18 unit tests for config and mappers.
- Integration tests: document CRUD, chunk CRUD, vector similarity search, cross-domain isolation, end-to-end ingest→search→retrieve workflow.

### Dependencies

- Added `psycopg[binary,pool]`, `pgvector`, `alembic`, `sqlalchemy`, `numpy`, `pydantic-settings` to `nornweave-storage`.
- Added `testcontainers[postgres]` to dev dependencies.

## [0.0.2] - 2026-02-17

### Added

- Implemented canonical domain model in `nornweave-core` (42 public types).
- Typed identifiers: `QueryId`, `DomainId`, `AgentId`, `DocumentId`, `ChunkId`, `TraceId`.
- Enumerations: `DomainType`, `AgentStatus`, `ConflictStrategy`, `ChunkingStrategy`, `IngestStatus`.
- Value objects: `RelevanceScore`, `EmbeddingVector`, `SourceCitation`, `DomainSignal`, `CoverageGap`, `TokenBudget`.
- Core entities: `Document`, `Chunk`, `DomainDescriptor`, `AgentRegistration`.
- Request models: `RecallRequest`, `IngestRequest`, `QueryRequest`, `FuseRequest`, `AgentRegisterRequest`, `HeartbeatRequest`.
- Response models: `RecallItem`, `ConflictRecord`, `RecallResponse`, `RoutingPlan`, `RoutingTarget`, `DocumentIngestStatus`, `IngestResult`, `FusionResult`, `HealthStatus`, `ErrorDetail`, `ErrorResponse`, `AgentListResponse`, `HeartbeatResponse`.
- Event models: `IngestionEvent`, `AgentLifecycleEvent`.
- JSON Schema export tests for every model (`model_json_schema()`).
- 153 unit tests with 100% coverage on `nornweave-core`.

## [0.0.1] - 2026-02-17

### Added

- Initialized `uv` workspace monorepo with root `pyproject.toml`.
- Created library stubs: `nornweave-core`, `nornweave-storage`, `nornweave-testing`.
- Created service stubs: `router`, `fusion`, `memory-agent`, `registry`.
- Configured `ruff` (linting + formatting), `mypy` (strict for libs, standard for services), and `pre-commit` hooks.
- Set up `pytest` with `tests/unit/`, `tests/integration/`, `tests/e2e/` directories.
- Added `docker-compose.yaml` with pgvector (pg16) and Kafka (KRaft mode, 4 topics).
- Added `.gitignore` for Python monorepo.

[Unreleased]: https://github.com/southpawriter02/nornweave/compare/v0.0.3...HEAD
[0.0.3]: https://github.com/southpawriter02/nornweave/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/southpawriter02/nornweave/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/southpawriter02/nornweave/releases/tag/v0.0.1
