# NornWeave — Memory Agent Internals

> Design specification for the memory agent subsystem. Each domain agent follows the same structural template but implements domain-specific behavior for ingestion, chunking, storage, and retrieval. References the [Domain Model](DOMAIN-MODEL.md) for types and [Service Contracts](SERVICE-CONTRACTS.md) for API surface.

---

## Table of Contents

- [Common Architecture](#common-architecture)
  - [Agent Lifecycle](#agent-lifecycle)
  - [Ingestion Pipeline](#ingestion-pipeline)
  - [Recall Pipeline](#recall-pipeline)
  - [Storage Layer](#storage-layer)
  - [Reranking](#reranking)
  - [Internal File Structure](#internal-file-structure)
- [Code Memory Agent](#code-memory-agent)
- [Documentation Memory Agent](#documentation-memory-agent)
- [Conversation Memory Agent](#conversation-memory-agent)
- [Research Memory Agent](#research-memory-agent)
- [Agent Configuration Schema](#agent-configuration-schema)

---

## Common Architecture

Every memory agent is a FastAPI service that implements the four-method interface (`recall`, `ingest`, `health`, `describe`). The internal architecture is identical across agents; only the strategy implementations differ.

```
┌─────────────────────────────────────────────────────────┐
│                     Memory Agent                         │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │ API Layer (FastAPI)                               │   │
│  │  POST /recall  POST /ingest  GET /health/describe │   │
│  └──────────┬───────────────────┬────────────────────┘   │
│             │                   │                         │
│  ┌──────────▼──────────┐  ┌────▼─────────────────────┐  │
│  │  Recall Pipeline    │  │  Ingestion Pipeline       │  │
│  │  1. Embed query     │  │  1. Validate              │  │
│  │  2. Vector search   │  │  2. Deduplicate           │  │
│  │  3. Rerank          │  │  3. Chunk                 │  │
│  │  4. Build response  │  │  4. Embed                 │  │
│  └──────────┬──────────┘  │  5. Store                 │  │
│             │             │  6. Publish event          │  │
│             │             └────┬─────────────────────┘   │
│  ┌──────────▼──────────────────▼─────────────────────┐  │
│  │  Storage Adapter                                   │  │
│  │  PostgreSQL + pgvector (vectors)                   │  │
│  │  Document/chunk metadata                           │  │
│  └───────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Agent Lifecycle

```
STARTING ──▶ READY ──▶ DEGRADED ──▶ READY
   │            │                      │
   │            └──────── DRAINING ────┘
   │                        │
   └── (fatal) ──▶ OFFLINE ◀┘
```

| State      | Entry Condition                                | Behavior                                        |
| ---------- | ---------------------------------------------- | ----------------------------------------------- |
| `STARTING` | Process boot                                   | Load models, connect DB, register with registry |
| `READY`    | All health checks pass                         | Accept recall + ingest                          |
| `DEGRADED` | A non-fatal health check fails (e.g., slow DB) | Accept recall, reject ingest                    |
| `DRAINING` | Shutdown signal received                       | Finish in-flight work, reject new               |
| `OFFLINE`  | Process exit or fatal error                    | No traffic                                      |

**Startup sequence:**

1. Load configuration from environment (`pydantic-settings`)
2. Connect to PostgreSQL, verify pgvector extension
3. Load embedding model (sentence-transformers or API client)
4. Load reranker model (if applicable)
5. Register with service registry (`POST /agents/register`)
6. Transition to `READY`
7. Begin heartbeat loop (every 10s)

### Ingestion Pipeline

The generic pipeline that all agents execute, with domain-specific strategy injections at the marked points.

```
IngestRequest
    │
    ├── 1. VALIDATE
    │      - Check document size (≤ 10 MB)
    │      - Verify required fields
    │      - Return 422 for invalid documents
    │
    ├── 2. DEDUPLICATE
    │      - Compare content_hash against stored hashes
    │      - Skip documents with matching hash (idempotent)
    │      - Mark duplicates as REJECTED with reason "duplicate"
    │
    ├── 3. CHUNK  ◀── [domain-specific strategy]
    │      - Segment document into chunks
    │      - Assign ordinal positions
    │      - Compute token counts per chunk
    │      - Attach chunk-level metadata
    │
    ├── 4. EMBED  ◀── [domain-specific model]
    │      - Batch chunks for efficiency (batch size: 32)
    │      - Generate EmbeddingVector per chunk
    │      - Validate dimensionality matches config
    │
    ├── 5. STORE
    │      - Insert Document row
    │      - Bulk-insert Chunk rows with embeddings
    │      - Transaction: all-or-nothing per document
    │
    └── 6. PUBLISH EVENT
           - Emit IngestionEvent to Kafka
           - Topic: nornweave.ingestion.events
           - Includes document_ids and chunk count
```

**Batch processing:** Steps 3–5 process documents sequentially within a batch, but step 4 (embedding) batches all chunks from a single document into one model call to minimize round-trips.

### Recall Pipeline

```
RecallRequest
    │
    ├── 1. EMBED QUERY  ◀── [same model as ingestion]
    │      - Generate query embedding
    │      - Same model + dimensionality as stored chunks
    │
    ├── 2. VECTOR SEARCH
    │      - pgvector cosine similarity search
    │      - Fetch top_k × OVERFETCH_FACTOR candidates
    │      - Apply any domain-specific filters (path_glob, date_range, etc.)
    │
    ├── 3. RERANK  ◀── [domain-specific reranker]
    │      - Score candidates using cross-encoder or heuristics
    │      - Re-sort by reranked score
    │      - Trim to final top_k
    │
    └── 4. BUILD RESPONSE
           - Construct RecallItem[] with citations
           - Compute latency_ms
           - Return RecallResponse
```

**Overfetch factor:** The vector search retrieves `top_k × 3` candidates (configurable via `OVERFETCH_FACTOR`). The reranker then narrows this to the final `top_k`. Overfetching compensates for the approximate nature of vector similarity; the reranker uses richer signals to produce a better final ranking.

### Storage Layer

All agents share the same PostgreSQL + pgvector storage schema. Each agent gets its own database (or schema) to enforce aggregate isolation.

**Documents table:**

```sql
CREATE TABLE documents (
    id              UUID PRIMARY KEY,
    domain_id       TEXT NOT NULL,
    source_path     TEXT NOT NULL,
    content         TEXT NOT NULL,
    content_hash    TEXT NOT NULL UNIQUE,
    metadata        JSONB NOT NULL DEFAULT '{}',
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_documents_content_hash ON documents (content_hash);
CREATE INDEX idx_documents_domain_id ON documents (domain_id);
```

**Chunks table:**

```sql
CREATE TABLE chunks (
    id              UUID PRIMARY KEY,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    domain_id       TEXT NOT NULL,
    content         TEXT NOT NULL,
    embedding       vector(768),  -- dimensionality varies by agent config
    position        INTEGER NOT NULL,
    token_count     INTEGER NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chunks_document_id ON chunks (document_id);
CREATE INDEX idx_chunks_embedding ON chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**Index tuning:** The `ivfflat` index `lists` parameter should be set to `sqrt(total_rows)` for optimal recall. The default of 100 works for up to ~10,000 chunks. Beyond that, recalculate or switch to `hnsw`.

**pgvector index strategy by scale:**

| Chunk Count    | Index Type | Parameters                     | Trade-off                    |
| -------------- | ---------- | ------------------------------ | ---------------------------- |
| < 10,000       | `ivfflat`  | `lists = 100`                  | Fast builds, good recall     |
| 10,000–100,000 | `ivfflat`  | `lists = sqrt(n)`              | Reindex periodically         |
| > 100,000      | `hnsw`     | `m = 16, ef_construction = 64` | Slower builds, better recall |

### Reranking

All agents use a two-stage retrieval architecture:

1. **Stage 1 (retriever):** Fast, approximate vector similarity via pgvector.
2. **Stage 2 (reranker):** Slower, precise cross-encoder scoring on the candidate set.

**Reranker options:**

| Reranker                        | Latency (20 items) | Quality | When to Use                      |
| ------------------------------- | ------------------ | ------- | -------------------------------- |
| `cross-encoder/ms-marco-MiniLM` | 50–80 ms           | Good    | Default for most agents          |
| `BAAI/bge-reranker-base`        | 80–120 ms          | Better  | When quality matters more        |
| Domain heuristic (no model)     | < 1 ms             | Varies  | Dev/testing or constrained infra |

**Domain heuristics** (used as reranker fallback or supplement):

| Domain          | Heuristic Signal                               | Weight |
| --------------- | ---------------------------------------------- | ------ |
| `code`          | Exact symbol match in chunk                    | +0.15  |
| `code`          | Query file path matches chunk source path      | +0.10  |
| `documentation` | Query terms appear in section headers          | +0.10  |
| `conversations` | Recency bias (newer messages score higher)     | +0.10  |
| `research`      | Citation count / venue prestige (if available) | +0.05  |

The final reranked score is:

```
final_score = (reranker_model_score × 0.7) + (heuristic_bonus × 0.3)
```

Clamped to `[0.0, 1.0]`.

### Internal File Structure

Each agent service follows the same directory layout:

```
services/{agent-name}/src/nornweave_{agent_name}/
├── __init__.py
├── main.py                  # FastAPI app, lifespan hooks
├── api/
│   ├── __init__.py
│   └── routes.py            # The four endpoints
├── ingestion/
│   ├── __init__.py
│   ├── pipeline.py          # Orchestrates validate → chunk → embed → store
│   ├── chunker.py           # Domain-specific ChunkingStrategy impl
│   └── validator.py         # Document validation rules
├── recall/
│   ├── __init__.py
│   ├── pipeline.py          # Orchestrates embed → search → rerank
│   ├── searcher.py          # pgvector similarity search
│   └── reranker.py          # Domain-specific reranking logic
├── storage/
│   ├── __init__.py
│   ├── repository.py        # Document + Chunk CRUD
│   └── migrations/          # Alembic migrations
├── embedding/
│   ├── __init__.py
│   └── client.py            # Embedding model wrapper
├── models/
│   ├── __init__.py
│   └── config.py            # AgentSettings (pydantic-settings)
└── domain.yaml              # Declarative agent configuration
```

**Key protocol:**

```python
from typing import Protocol

class Chunker(Protocol):
    def chunk(self, document: Document) -> list[Chunk]:
        """Segment a document into chunks."""
        ...
```

---

## Code Memory Agent

> **Agent ID:** `code-memory`  
> **Domain ID:** `code`  
> **Expertise:** Source files, ASTs, dependency graphs, commit history.

### Ingestion

#### Chunking Strategy: `SYNTAX_AWARE`

Uses **tree-sitter** for AST-boundary chunking. Code is split at function, class, and module boundaries rather than arbitrary character limits.

**Chunking rules:**

| Language Construct     | Chunk Boundary                                                | Max Chunk Size |
| ---------------------- | ------------------------------------------------------------- | -------------- |
| Top-level function     | Entire function body (signature through closing brace/dedent) | 512 tokens     |
| Class                  | Split into: class header + each method as a separate chunk    | 512 tokens     |
| Module-level constants | Grouped into a single "preamble" chunk                        | 256 tokens     |
| Import block           | Single chunk                                                  | 128 tokens     |
| Large function (> 512) | Split at inner scope boundaries (loops, conditionals)         | 512 tokens     |

**AST metadata extracted per chunk:**

```json
{
  "language": "python",
  "node_type": "function_definition",
  "function_name": "handle_payment_error",
  "class_name": "PaymentHandler",
  "parameter_count": 2,
  "return_type": "Response",
  "imports_used": ["PaymentError", "Response"],
  "file_path": "src/payments/handlers.py",
  "line_range": [42, 67],
  "commit_sha": "abc1234"
}
```

**Supported languages (tree-sitter grammars):**

Python, TypeScript, JavaScript, Go, Rust, Java, C, C++, Ruby, PHP, C#, Swift, Kotlin.

Unsupported languages fall back to `RECURSIVE_CHARACTER` chunking.

#### Embedding Model

| Model                     | Dimensions | Why                                                     |
| ------------------------- | ---------- | ------------------------------------------------------- |
| `microsoft/codebert-base` | 768        | Trained on code; understands syntax, not just semantics |

**Alternative (if CodeBERT is too heavy):** `sentence-transformers/all-MiniLM-L6-v2` (384 dims). Smaller and faster, but less code-aware.

#### Filters

The code agent supports the following domain-specific `filters` in `RecallRequest`:

| Filter Key  | Type       | Example                  | Behavior                              |
| ----------- | ---------- | ------------------------ | ------------------------------------- |
| `path_glob` | `string`   | `"src/payments/**"`      | Restrict search to matching paths     |
| `language`  | `string`   | `"python"`               | Restrict to chunks from this language |
| `since`     | `ISO 8601` | `"2026-01-15T00:00:00Z"` | Only chunks from recent documents     |
| `node_type` | `string`   | `"function_definition"`  | Restrict to specific AST node types   |

Filters are applied as SQL `WHERE` clauses before the vector search, narrowing the candidate set.

### Recall

#### Reranking

The code agent uses a **two-signal reranker**:

1. **Cross-encoder score** from `cross-encoder/ms-marco-MiniLM` on `(query, chunk_content)`.
2. **Symbol match bonus:** If the query contains an identifier (detected via regex `[A-Z][a-zA-Z0-9]+|[a-z]+_[a-z_]+`) that appears in the chunk's `function_name` or `class_name` metadata, add `+0.15` to the score.

```
final_score = clamp(cross_encoder_score × 0.7 + symbol_bonus × 0.3, 0.0, 1.0)
```

---

## Documentation Memory Agent

> **Agent ID:** `docs-memory`  
> **Domain ID:** `documentation`  
> **Expertise:** API docs, READMEs, ADRs, runbooks, Markdown/RST files.

### Ingestion

#### Chunking Strategy: `HIERARCHICAL_SECTIONS`

Splits documents at heading boundaries, preserving the hierarchical structure. Each chunk inherits its full heading path as context.

**Chunking rules:**

| Document Element       | Chunk Boundary                                        | Max Chunk Size |
| ---------------------- | ----------------------------------------------------- | -------------- |
| H1 section             | Split point; section content becomes a chunk          | 1024 tokens    |
| H2 section             | Split point; nested under parent H1                   | 512 tokens     |
| H3+ section            | Split point; nested under parent hierarchy            | 512 tokens     |
| Code block in docs     | Kept with its surrounding text, never split mid-block | —              |
| Table                  | Kept as a single unit, never split mid-table          | —              |
| Large section (> 1024) | Split at paragraph boundaries within the section      | 1024 tokens    |

**Heading path metadata:**

Each chunk carries its full heading ancestry, giving the retriever hierarchical context.

```json
{
  "heading_path": [
    "NornWeave Architecture",
    "Core Concepts",
    "Domain-Specialized Memory Agents"
  ],
  "heading_level": 3,
  "file_path": "docs/architecture.md",
  "format": "markdown",
  "has_code_blocks": true,
  "has_tables": false,
  "word_count": 342
}
```

**Supported formats:**

| Format     | Parser               | Notes                                    |
| ---------- | -------------------- | ---------------------------------------- |
| Markdown   | `mistune` (AST mode) | Primary format                           |
| RST        | `docutils`           | For Sphinx-based projects                |
| Plain text | Line-based splitting | Fallback; splits at double newlines      |
| HTML       | `beautifulsoup4`     | Strip tags, extract structural hierarchy |

#### Embedding Model

| Model                                    | Dimensions | Why                                               |
| ---------------------------------------- | ---------- | ------------------------------------------------- |
| `sentence-transformers/all-MiniLM-L6-v2` | 384        | Strong on natural language; fast, small footprint |

**Alternative:** `BAAI/bge-base-en-v1.5` (768 dims) for higher quality at the cost of speed.

#### Filters

| Filter Key     | Type     | Example           | Behavior                                  |
| -------------- | -------- | ----------------- | ----------------------------------------- |
| `path_glob`    | `string` | `"docs/api/**"`   | Restrict to matching file paths           |
| `format`       | `string` | `"markdown"`      | Restrict to a specific document format    |
| `heading_path` | `string` | `"API Reference"` | Match chunks under this heading hierarchy |

### Recall

#### Reranking

The docs agent uses a **heading-aware reranker**:

1. **Cross-encoder score** from `cross-encoder/ms-marco-MiniLM`.
2. **Heading match bonus:** If any query term appears in the chunk's `heading_path`, add `+0.10`.
3. **Recency bias:** Documents with newer `source_updated_at` get a slight boost (max `+0.05`, linearly decaying over 90 days).

```
final_score = clamp(cross_encoder × 0.7 + heading_bonus × 0.2 + recency × 0.1, 0.0, 1.0)
```

---

## Conversation Memory Agent

> **Agent ID:** `convo-memory`  
> **Domain ID:** `conversations`  
> **Expertise:** Chat logs, issue threads, PR discussions, meeting transcripts.

### Ingestion

#### Chunking Strategy: `MESSAGE_BOUNDARY`

Chunks at message or topic boundaries. Preserves conversational context by including surrounding messages.

**Chunking rules:**

| Conversation Element | Chunk Boundary                                                   | Max Chunk Size |
| -------------------- | ---------------------------------------------------------------- | -------------- |
| Single message       | One chunk per message (if under limit)                           | 256 tokens     |
| Long message (> 256) | Split at sentence boundaries                                     | 256 tokens     |
| Thread/topic group   | Group consecutive messages on the same topic into one chunk      | 512 tokens     |
| Meeting transcript   | Split at speaker turns or topic shifts (detected via timestamps) | 512 tokens     |

**Context window:** Each message chunk includes up to 2 preceding messages as context, prepended with speaker labels. This gives the embedder conversational grounding.

```
[context] alice: Has anyone looked at the payment bug?
[context] bob: I saw it yesterday, seems like a null pointer issue.
[current] charlie: I pushed a fix in PR #247, can someone review?
```

**Metadata per chunk:**

```json
{
  "source_type": "slack",
  "channel": "#engineering",
  "speaker": "charlie",
  "participants": ["alice", "bob", "charlie"],
  "thread_id": "1708012345.000100",
  "message_timestamp": "2026-01-16T14:22:00Z",
  "has_code_snippet": true,
  "has_url": true,
  "reaction_count": 3
}
```

**Supported source types:**

| Source      | Ingestion Format                    | Notes                              |
| ----------- | ----------------------------------- | ---------------------------------- |
| Slack       | JSON export (per-channel)           | Threads are grouped by `thread_ts` |
| GitHub      | Issue/PR comments via API           | Each comment is a message          |
| Transcripts | VTT/SRT or plain text with speakers | Parsed by speaker turn             |
| Generic     | Newline-delimited messages          | Fallback for unknown sources       |

#### Embedding Model

| Model                                    | Dimensions | Why                                    |
| ---------------------------------------- | ---------- | -------------------------------------- |
| `sentence-transformers/all-MiniLM-L6-v2` | 384        | Good at short-text semantic similarity |

Conversations are short-form text. Heavier models add latency without proportional quality gains for sentence-length inputs.

#### Filters

| Filter Key     | Type           | Example                          | Behavior                            |
| -------------- | -------------- | -------------------------------- | ----------------------------------- |
| `participants` | `list[string]` | `["alice", "bob"]`               | At least one participant must match |
| `channel`      | `string`       | `"#engineering"`                 | Restrict to a specific channel      |
| `date_range`   | `object`       | `{"start": "...", "end": "..."}` | Restrict by message timestamp       |
| `source_type`  | `string`       | `"slack"`                        | Restrict to a specific source type  |

### Recall

#### Reranking

The conversation agent uses a **recency-weighted reranker**:

1. **Cross-encoder score** from `cross-encoder/ms-marco-MiniLM`.
2. **Recency bonus:** More recent messages score higher. The bonus decays exponentially:

```
recency_bonus = 0.15 × exp(-days_old / 30)
```

A message from today gets `+0.15`; a message from 30 days ago gets `+0.055`; a message from 90 days ago gets `+0.007`.

3. **Engagement signal:** High `reaction_count` adds a small bonus (max `+0.05`), on the assumption that reacted-to messages are more informative.

```
final_score = clamp(cross_encoder × 0.65 + recency × 0.25 + engagement × 0.10, 0.0, 1.0)
```

---

## Research Memory Agent

> **Agent ID:** `research-memory`  
> **Domain ID:** `research`  
> **Expertise:** Academic papers, articles, Stack Overflow, third-party documentation.

### Ingestion

#### Chunking Strategy: `HIERARCHICAL_SECTIONS` (with academic extensions)

Uses the same heading-based splitting as the docs agent, plus specialized handling for academic paper structure (abstract, methodology, results, references).

**Chunking rules:**

| Document Element        | Chunk Boundary                                            | Max Chunk Size |
| ----------------------- | --------------------------------------------------------- | -------------- |
| Abstract                | Always a standalone chunk                                 | 512 tokens     |
| Named section           | Split at section boundaries (Introduction, Methods, etc.) | 1024 tokens    |
| Subsection              | Split at subsection boundaries within a section           | 512 tokens     |
| References/bibliography | Single chunk (for citation-based retrieval)               | 1024 tokens    |
| Stack Overflow answer   | One chunk per answer (question included as context)       | 512 tokens     |
| Large section (> 1024)  | Split at paragraph boundaries                             | 1024 tokens    |

**Metadata per chunk:**

```json
{
  "source_type": "arxiv_paper",
  "title": "Attention Is All You Need",
  "authors": ["Vaswani, A.", "Shazeer, N.", "..."],
  "publication_date": "2017-06-12",
  "doi": "10.48550/arXiv.1706.03762",
  "section_name": "3.2 Multi-Head Attention",
  "venue": "NeurIPS 2017",
  "citation_count": 120000,
  "tags": ["transformers", "attention", "nlp"]
}
```

**Supported source types:**

| Source             | Ingestion Format          | Notes                                    |
| ------------------ | ------------------------- | ---------------------------------------- |
| arXiv papers       | PDF → text via `pymupdf`  | Section detection via heading patterns   |
| Markdown articles  | Same as docs-agent parser | Standard hierarchical chunking           |
| Stack Overflow     | JSON export or API        | Q&A pairs; question is prepended context |
| HTML documentation | `beautifulsoup4` → text   | Third-party API docs, tutorials          |

#### Embedding Model

| Model                                    | Dimensions | Why                                                       |
| ---------------------------------------- | ---------- | --------------------------------------------------------- |
| `sentence-transformers/all-MiniLM-L6-v2` | 384        | Balances quality and speed for mixed-length academic text |

**Alternative for heavy research use:** `BAAI/bge-base-en-v1.5` (768 dims). Better at capturing nuanced academic language.

#### Filters

| Filter Key    | Type           | Example                   | Behavior                            |
| ------------- | -------------- | ------------------------- | ----------------------------------- |
| `source_type` | `string`       | `"arxiv_paper"`           | Restrict to a specific source type  |
| `authors`     | `list[string]` | `["Vaswani"]`             | Match papers with any listed author |
| `date_range`  | `object`       | `{"start": "2023-01-01"}` | Restrict by publication date        |
| `tags`        | `list[string]` | `["transformers", "rag"]` | Match chunks with any listed tag    |

### Recall

#### Reranking

The research agent uses an **authority-weighted reranker**:

1. **Cross-encoder score** from `cross-encoder/ms-marco-MiniLM`.
2. **Source authority bonus:** Stack Overflow accepted answers get `+0.05`. High-citation papers get a logarithmic bonus:

```
citation_bonus = min(0.10, 0.02 × log10(citation_count + 1))
```

3. **Recency factor:** For fast-moving fields, newer papers get a mild boost (same formula as docs agent, `+0.05` max).

```
final_score = clamp(cross_encoder × 0.70 + authority × 0.20 + recency × 0.10, 0.0, 1.0)
```

---

## Agent Configuration Schema

Each agent is configured via a `domain.yaml` file alongside environment variables. The YAML file captures domain-specific behavior; env vars handle deployment-specific settings.

**`domain.yaml` schema:**

```yaml
# Identity
agent_id: code-memory
domain_id: code
name: "Source Code"
description: "Application source code, dependency manifests, infrastructure-as-code definitions, and CI/CD configurations."

# Chunking
chunking:
  strategy: SYNTAX_AWARE # SYNTAX_AWARE | HIERARCHICAL_SECTIONS | MESSAGE_BOUNDARY | RECURSIVE_CHARACTER
  max_chunk_tokens: 512
  overlap_tokens: 0 # Character-level overlap (only for RECURSIVE_CHARACTER)
  language_grammars: # Only for SYNTAX_AWARE
    - python
    - typescript
    - go

# Embedding
embedding:
  model: microsoft/codebert-base
  dimensions: 768
  batch_size: 32
  device: cpu # cpu | cuda

# Reranking
reranking:
  model: cross-encoder/ms-marco-MiniLM # null to disable cross-encoder
  overfetch_factor: 3
  heuristics:
    symbol_match_bonus: 0.15 # Domain-specific
    recency_bonus_max: 0.0 # Domain-specific
    heading_match_bonus: 0.0 # Domain-specific
  weights:
    model: 0.7
    heuristic: 0.3

# Storage
storage:
  database_url: "${DATABASE_URL}" # Resolved from env
  vector_index: ivfflat # ivfflat | hnsw
  ivfflat_lists: 100
  hnsw_m: 16
  hnsw_ef_construction: 64

# Filters (declarative filter-key registry)
filters:
  - key: path_glob
    type: string
    sql_template: "metadata->>'file_path' LIKE {value}"
  - key: language
    type: string
    sql_template: "metadata->>'language' = {value}"
  - key: since
    type: datetime
    sql_template: "created_at >= {value}"
```

**Environment variables (common to all agents):**

| Variable                  | Type  | Default                | Description                         |
| ------------------------- | ----- | ---------------------- | ----------------------------------- |
| `AGENT_PORT`              | `int` | `8081`                 | HTTP listen port                    |
| `DATABASE_URL`            | `str` | (required)             | PostgreSQL connection string        |
| `KAFKA_BOOTSTRAP`         | `str` | `kafka:9092`           | Kafka broker address                |
| `NORNWEAVE_SERVICE_TOKEN` | `str` | (required)             | Bearer token for inter-service auth |
| `REGISTRY_URL`            | `str` | `http://registry:8083` | Service registry address            |
| `HEARTBEAT_INTERVAL_S`    | `int` | `10`                   | Health heartbeat interval           |
| `LOG_LEVEL`               | `str` | `INFO`                 | Logging verbosity                   |
| `EMBEDDING_DEVICE`        | `str` | `cpu`                  | Device for embedding model          |
