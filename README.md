# NornWeave

**Collaborative Recall Mesh — A Multi-Agent Memory Architecture**

NornWeave is a multi-agent architecture where specialized "memory agents" each maintain expertise in different knowledge domains. Query routing intelligently fans out recall requests to relevant experts, enabling virtually unlimited knowledge breadth while maintaining deep recall fidelity.

Named after the Norns of Norse mythology — beings who weave the threads of fate and memory — NornWeave treats organizational knowledge not as a monolithic store, but as a living tapestry woven from the contributions of domain-specialized agents.

---

## Table of Contents

- [Theoretical Foundation](#theoretical-foundation)
- [Architecture Overview](#architecture-overview)
- [Core Components](#core-components)
  - [Domain Memory Agents](#domain-memory-agents)
  - [Router Agent](#router-agent)
  - [Response Fusion Layer](#response-fusion-layer)
  - [Specialization Training](#specialization-training)
- [Domain Segmentation Model](#domain-segmentation-model)
- [Query Lifecycle](#query-lifecycle)
- [Scaling Properties](#scaling-properties)
- [Delivery Format](#delivery-format)
  - [Framework Design](#framework-design)
  - [Agent Configuration](#agent-configuration)
  - [Docker Compose Deployment](#docker-compose-deployment)
  - [Horizontal Scaling](#horizontal-scaling)
- [Conflict Resolution and Consensus](#conflict-resolution-and-consensus)
- [Failure Modes and Resilience](#failure-modes-and-resilience)
- [Performance Characteristics](#performance-characteristics)
- [Comparison to Monolithic Memory Architectures](#comparison-to-monolithic-memory-architectures)
- [Future Directions](#future-directions)
- [License](#license)

---

## Theoretical Foundation

Traditional AI memory systems treat recall as a single-index lookup problem: one embedding store, one retrieval path, one ranking function. This works at small scale but degrades as knowledge breadth increases. Embedding spaces become crowded, retrieval precision drops, and the system loses the ability to distinguish between superficially similar but semantically distinct concepts across domains.

NornWeave draws from two key insights:

1. **Expert Decomposition**: Human organizations don't store all knowledge in a single brain. They distribute expertise across specialists and route questions to the right person. This architecture mirrors that pattern — each memory agent is a specialist, and the router is the organizational switchboard.

2. **Recall Fidelity vs. Breadth Tradeoff**: A single retrieval system forced to cover all domains inevitably makes compromises. Either the embedding space becomes too diluted for precise recall, or the context window fills with irrelevant cross-domain noise. By isolating domains, each agent maintains a tight, high-fidelity recall surface.

The architecture is grounded in the principle that **partitioned expertise with intelligent routing outperforms monolithic retrieval** at scale — the same principle that drives microservice architectures, sharded databases, and federated search systems.

---

## Architecture Overview

```
                         ┌─────────────────┐
                         │   User / Client  │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │  Router Agent    │
                         │  (Classifier)    │
                         └────────┬─────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │             │             │
                    ▼             ▼             ▼
             ┌───────────┐ ┌───────────┐ ┌───────────┐
             │  Code      │ │  Docs     │ │  Research  │
             │  Memory    │ │  Memory   │ │  Memory    │
             │  Agent     │ │  Agent    │ │  Agent     │
             └─────┬─────┘ └─────┬─────┘ └─────┬─────┘
                    │             │             │
                    └─────────────┼─────────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │  Response Fusion │
                         │  (Aggregator)    │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │  Unified Response│
                         └─────────────────┘
```

The architecture follows a **fan-out / fan-in** pattern. A query arrives, gets classified and routed to one or more domain agents in parallel, and the responses are fused into a coherent answer. This pattern enables both latency optimization (parallel recall) and quality optimization (domain-specific retrieval).

---

## Core Components

### Domain Memory Agents

Each domain memory agent is a self-contained recall system specialized for a particular knowledge domain. An agent encapsulates:

- **Domain-Specific Embedding Store**: Embeddings trained or tuned for the vocabulary, structure, and semantics of the domain. Code embeddings differ fundamentally from conversational embeddings — variable names, function signatures, and AST structures require different representation strategies than natural language paragraphs.

- **Retrieval Strategy**: Each domain may use a different retrieval approach. Code memory might use hybrid retrieval combining semantic search with AST-aware structural matching. Documentation memory might use hierarchical chunking that preserves section structure. Conversation memory might use temporal windowing combined with entity extraction.

- **Domain Context Window**: Each agent maintains its own context budget, meaning the total system context scales linearly with the number of agents rather than being a fixed constraint.

- **Ingestion Pipeline**: Domain-specific preprocessing, chunking, and indexing logic. Code is parsed differently than prose, which is parsed differently than structured research data.

```
┌─────────────────────────────────────────┐
│           Domain Memory Agent            │
│                                         │
│  ┌──────────┐  ┌──────────────────────┐ │
│  │ Ingestion│  │  Embedding Store     │ │
│  │ Pipeline │──│  (Domain-Tuned)      │ │
│  └──────────┘  └──────────┬───────────┘ │
│                            │             │
│  ┌──────────┐  ┌──────────▼───────────┐ │
│  │ Domain   │  │  Retrieval Engine    │ │
│  │ Schema   │──│  (Strategy-Specific) │ │
│  └──────────┘  └──────────┬───────────┘ │
│                            │             │
│                 ┌──────────▼───────────┐ │
│                 │  Response Formatter  │ │
│                 └─────────────────────┘ │
└─────────────────────────────────────────┘
```

**Key design constraint**: Domain agents must be stateless with respect to queries. All persistent state lives in the embedding store and domain schema. This enables horizontal scaling — multiple replicas of the same domain agent can serve concurrent queries against a shared store.

### Router Agent

The Router Agent is a lightweight classifier that sits at the system's entry point. Its responsibilities:

1. **Query Analysis**: Parse the incoming query to extract intent, entities, and domain signals. A query like *"What was the authentication bug we fixed last sprint?"* carries signals for both the code domain (authentication, bug, fix) and the conversation domain (last sprint — temporal, collaborative context).

2. **Domain Selection**: Map the analyzed query to one or more target domains. This is not a hard classification — the router outputs a weighted distribution across domains, and any domain above a configurable threshold receives the query.

3. **Query Rewriting**: Optionally transform the query for each target domain. The code memory agent might receive a reformulated query emphasizing technical terms, while the conversation agent receives a version emphasizing temporal and social context.

4. **Fan-Out Coordination**: Dispatch queries to selected agents in parallel and manage timeouts, retries, and partial failure scenarios.

```
Input Query
    │
    ▼
┌──────────────┐
│ Intent        │
│ Extraction    │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌─────────────────────┐
│ Domain        │────▶│ Domain Confidence    │
│ Classification│     │ Scores               │
└──────┬───────┘     │                     │
       │              │ code:         0.82   │
       │              │ docs:         0.15   │
       │              │ conversations: 0.91  │
       │              │ research:     0.03   │
       │              └─────────────────────┘
       ▼
┌──────────────┐
│ Threshold     │──── threshold: 0.20
│ Filter        │
└──────┬───────┘
       │
       ▼
  Fan-out to: [code, conversations]
```

The router is deliberately kept lightweight. It does not perform retrieval itself — it only classifies and dispatches. This separation of concerns means the router can be updated, retrained, or replaced without touching any domain agent logic.

### Response Fusion Layer

When a query fans out to multiple domain agents, the system receives multiple partial responses that must be synthesized. The Response Fusion Layer handles:

- **Deduplication**: Multiple agents may surface the same underlying fact from different angles. The fusion layer detects semantic overlap and consolidates.

- **Conflict Resolution**: Domain agents may return contradictory information. The fusion layer applies a configurable conflict resolution strategy — timestamp-based recency, source authority ranking, or confidence-weighted voting (see [Conflict Resolution and Consensus](#conflict-resolution-and-consensus)).

- **Relevance Ranking**: Each domain agent returns results with domain-local relevance scores. These scores are not directly comparable across domains (a 0.9 in code search means something different than a 0.9 in conversation search). The fusion layer normalizes scores using calibrated cross-domain weighting.

- **Coherent Synthesis**: The final output is not a concatenation of domain responses but a coherent, unified answer that draws from all contributing domains while attributing provenance.

### Specialization Training

Each memory agent is fine-tuned or prompted specifically for its domain's retrieval patterns. This specialization operates at multiple levels:

- **Embedding Model Selection**: Different domains may use entirely different embedding models. Code domains benefit from models trained on source code (e.g., code-specific transformer variants). Documentation domains benefit from models trained on technical prose.

- **Prompt Engineering**: Each agent's retrieval prompts are crafted for the domain. A code agent's reranking prompt understands function signatures and type systems. A conversation agent's prompt understands dialogue structure and speaker attribution.

- **Chunking Strategy**: Domain-specific chunking ensures retrieval units are semantically coherent within the domain. Code is chunked along function/class boundaries. Documentation is chunked along section hierarchies. Conversations are chunked along topic boundaries with speaker context preserved.

- **Relevance Calibration**: Each agent's relevance scoring is calibrated against domain-specific ground truth, ensuring that confidence scores are meaningful within the domain and can be normalized across domains by the fusion layer.

---

## Domain Segmentation Model

NornWeave partitions knowledge into domains. The default segmentation includes four primary domains, though the architecture supports arbitrary domain definitions:

| Domain | Scope | Retrieval Characteristics |
|--------|-------|---------------------------|
| **Code** | Source code, diffs, commit history, ASTs, dependency graphs | Structural matching, symbol-aware search, version-sensitive recall |
| **Documentation** | READMEs, wikis, API docs, architecture decision records, runbooks | Hierarchical section-aware retrieval, cross-reference resolution |
| **Conversations** | Chat logs, meeting notes, decision threads, PR discussions | Temporal windowing, speaker attribution, topic segmentation |
| **External Research** | Papers, articles, third-party documentation, web references | Citation tracking, source authority scoring, freshness weighting |

### Domain Boundary Design

Domain boundaries should be drawn along **retrieval strategy lines**, not content type lines. The question is not *"What kind of content is this?"* but *"How should this content be searched?"*. Content that requires the same retrieval strategy belongs in the same domain, even if it seems categorically different.

For example, inline code comments might seem like they belong in the documentation domain, but they are best retrieved alongside the code they annotate — so they belong in the code domain. Conversely, a long-form architecture decision record written as a code comment might be better served by the documentation domain's hierarchical retrieval.

### Domain Overlap Zones

Some knowledge naturally spans domains. A pull request, for instance, contains code changes (code domain), a description (documentation domain), and review comments (conversation domain). NornWeave handles this through **multi-domain indexing**: the same source artifact can be ingested by multiple domain agents, each extracting the aspects relevant to its specialization.

```
Pull Request #1234
    │
    ├──▶ Code Agent:         indexes diff, file changes, symbols modified
    ├──▶ Documentation Agent: indexes PR description, linked issues
    └──▶ Conversation Agent:  indexes review comments, discussion threads
```

This means a query about the PR can be answered from any angle, and cross-domain queries naturally receive multi-perspective responses.

---

## Query Lifecycle

A complete query through the NornWeave system follows this lifecycle:

```
1. RECEIVE    ─── Client submits natural language query
                   │
2. CLASSIFY   ─── Router analyzes query, produces domain scores
                   │
3. REWRITE    ─── Query optionally reformulated per target domain
                   │
4. DISPATCH   ─── Parallel fan-out to qualifying domain agents
                   │
5. RETRIEVE   ─── Each agent performs domain-specific retrieval
                   │
6. RESPOND    ─── Each agent returns ranked results with metadata
                   │
7. FUSE       ─── Aggregator deduplicates, resolves conflicts, ranks
                   │
8. SYNTHESIZE ─── Coherent response assembled with provenance
                   │
9. DELIVER    ─── Final response returned to client
```

### Latency Profile

Steps 1–3 are sequential and fast (classifier inference). Steps 4–6 are parallel across agents — total latency is bounded by the slowest agent, not the sum. Steps 7–9 are sequential but operate on the reduced result set. The overall latency profile is:

```
T_total = T_route + max(T_agent_1, T_agent_2, ..., T_agent_n) + T_fuse
```

This is significantly better than a sequential multi-domain search, where latency would be the sum of all agent retrieval times.

---

## Scaling Properties

NornWeave exhibits several favorable scaling properties:

### Knowledge Breadth Scaling

Adding a new knowledge domain requires deploying a new domain agent and registering it with the router. The router's classification layer is extended (via config, not code changes), and the fusion layer automatically incorporates the new domain's responses. Existing agents are unaffected.

```
Scaling knowledge breadth:

  Before:  [Code] [Docs] [Conversations]
  After:   [Code] [Docs] [Conversations] [Research] [Metrics]
                                          ▲           ▲
                                    new agents added
```

### Knowledge Depth Scaling

Each domain agent can independently scale its embedding store, upgrade its retrieval model, or refine its chunking strategy. Improving recall fidelity in one domain has no impact on other domains — there is no shared embedding space to pollute or context window to contend for.

### Query Throughput Scaling

Domain agents are stateless query processors. Multiple replicas of any agent can be deployed behind a load balancer, providing horizontal throughput scaling per domain. High-traffic domains can be scaled independently of low-traffic ones.

### Agent Independence

The critical architectural property is **agent independence**: agents share nothing except the query/response protocol. They can be written in different languages, use different embedding models, run on different hardware, and be deployed/updated on independent schedules.

---

## Delivery Format

### Framework Design

NornWeave is built as a composable framework, not a monolithic application. The core abstractions are:

- **MemoryAgent**: Interface that any domain agent must implement — `ingest(document)`, `query(text) → results`, `health() → status`.
- **Router**: Pluggable query classifier. The default implementation uses a lightweight embedding-based classifier, but the interface supports rule-based, LLM-based, or hybrid routing strategies.
- **Fusioner**: Pluggable response aggregator. Default implementation handles deduplication and relevance-weighted merging, but custom strategies can be injected.
- **Registry**: Service discovery layer where agents register their domain, capabilities, and health status.

### Agent Configuration

Domain agents are defined declaratively via configuration. A new domain agent requires only a config block — no framework code changes:

```yaml
# nornweave.yaml

router:
  model: "classifier-v1"
  threshold: 0.20
  strategy: "weighted-fanout"

agents:
  - name: "code-memory"
    domain: "code"
    embedding_model: "code-embed-v2"
    chunk_strategy: "ast-aware"
    store:
      backend: "pgvector"
      connection: "${CODE_DB_URL}"
    retrieval:
      top_k: 20
      rerank: true
      rerank_model: "code-rerank-v1"

  - name: "docs-memory"
    domain: "documentation"
    embedding_model: "text-embed-v3"
    chunk_strategy: "hierarchical-sections"
    store:
      backend: "pgvector"
      connection: "${DOCS_DB_URL}"
    retrieval:
      top_k: 15
      rerank: true
      rerank_model: "text-rerank-v1"

  - name: "conversation-memory"
    domain: "conversations"
    embedding_model: "text-embed-v3"
    chunk_strategy: "topic-windowed"
    store:
      backend: "pgvector"
      connection: "${CONV_DB_URL}"
    retrieval:
      top_k: 25
      rerank: false

  - name: "research-memory"
    domain: "research"
    embedding_model: "academic-embed-v1"
    chunk_strategy: "paragraph-with-citations"
    store:
      backend: "pgvector"
      connection: "${RESEARCH_DB_URL}"
    retrieval:
      top_k: 10
      rerank: true
      rerank_model: "academic-rerank-v1"

fusion:
  strategy: "confidence-weighted"
  deduplication: true
  conflict_resolution: "recency-biased"
  max_results: 10
```

### Docker Compose Deployment

NornWeave provides a Docker Compose template for local multi-agent deployment. Each component runs as an independent service:

```yaml
# docker-compose.yaml

services:
  router:
    build: ./services/router
    ports:
      - "8000:8000"
    environment:
      - NORNWEAVE_CONFIG=/config/nornweave.yaml
      - REGISTRY_URL=http://registry:8500
    depends_on:
      - registry

  registry:
    build: ./services/registry
    ports:
      - "8500:8500"

  code-memory:
    build: ./services/memory-agent
    environment:
      - AGENT_NAME=code-memory
      - DOMAIN=code
      - EMBEDDING_MODEL=code-embed-v2
      - STORE_BACKEND=pgvector
      - DB_URL=postgresql://nornweave:${DB_PASS}@code-db:5432/code_memory
    depends_on:
      - code-db
      - registry

  docs-memory:
    build: ./services/memory-agent
    environment:
      - AGENT_NAME=docs-memory
      - DOMAIN=documentation
      - EMBEDDING_MODEL=text-embed-v3
      - STORE_BACKEND=pgvector
      - DB_URL=postgresql://nornweave:${DB_PASS}@docs-db:5432/docs_memory
    depends_on:
      - docs-db
      - registry

  conversation-memory:
    build: ./services/memory-agent
    environment:
      - AGENT_NAME=conversation-memory
      - DOMAIN=conversations
      - EMBEDDING_MODEL=text-embed-v3
      - STORE_BACKEND=pgvector
      - DB_URL=postgresql://nornweave:${DB_PASS}@conv-db:5432/conv_memory
    depends_on:
      - conv-db
      - registry

  research-memory:
    build: ./services/memory-agent
    environment:
      - AGENT_NAME=research-memory
      - DOMAIN=research
      - EMBEDDING_MODEL=academic-embed-v1
      - STORE_BACKEND=pgvector
      - DB_URL=postgresql://nornweave:${DB_PASS}@research-db:5432/research_memory
    depends_on:
      - research-db
      - registry

  fusion:
    build: ./services/fusion
    ports:
      - "8001:8001"
    environment:
      - REGISTRY_URL=http://registry:8500
      - FUSION_STRATEGY=confidence-weighted
    depends_on:
      - registry

  # Vector-enabled PostgreSQL instances per domain
  code-db:
    image: pgvector/pgvector:pg16
    volumes:
      - code-data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=code_memory
      - POSTGRES_USER=nornweave
      - POSTGRES_PASSWORD=${DB_PASS}

  docs-db:
    image: pgvector/pgvector:pg16
    volumes:
      - docs-data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=docs_memory
      - POSTGRES_USER=nornweave
      - POSTGRES_PASSWORD=${DB_PASS}

  conv-db:
    image: pgvector/pgvector:pg16
    volumes:
      - conv-data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=conv_memory
      - POSTGRES_USER=nornweave
      - POSTGRES_PASSWORD=${DB_PASS}

  research-db:
    image: pgvector/pgvector:pg16
    volumes:
      - research-data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=research_memory
      - POSTGRES_USER=nornweave
      - POSTGRES_PASSWORD=${DB_PASS}

volumes:
  code-data:
  docs-data:
  conv-data:
  research-data:
```

### Horizontal Scaling

The architecture is designed so that adding new domain agents requires no modification to the router's core logic. The scaling model:

1. **Add a New Agent**: Define a new agent config block and deploy the service.
2. **Register with the Registry**: The new agent registers itself, declaring its domain and capabilities.
3. **Router Discovers Automatically**: The router polls the registry and incorporates the new domain into its classification space. If the router uses an embedding-based classifier, the new domain's representative embeddings are added to the classification index. If rule-based, a new rule set is appended.
4. **Fusion Layer Adapts**: The fusion layer already handles an arbitrary number of response sources — no changes needed.

```
                  ┌─────────┐
    New Agent ──▶ │ Registry │ ──▶ Router auto-discovers
                  └─────────┘     Fusion auto-incorporates
```

For production deployments beyond Docker Compose, agents can be deployed as Kubernetes pods with horizontal pod autoscalers, enabling per-domain throughput scaling based on actual query load.

---

## Conflict Resolution and Consensus

When multiple domain agents return information about the same topic, conflicts can arise. NornWeave supports pluggable conflict resolution strategies:

### Recency-Biased Resolution

Prefer the most recently ingested information. Useful when knowledge evolves over time and newer sources supersede older ones.

### Source Authority Ranking

Each domain agent can tag results with a source authority score. Official documentation outranks a chat message; a merged PR outranks an open discussion. The fusion layer uses these scores to break ties.

### Confidence-Weighted Voting

Each agent's confidence score is calibrated and normalized. When agents disagree, the response with the highest calibrated confidence wins. This requires careful per-domain calibration to ensure scores are comparable.

### Provenance Preservation

Regardless of conflict resolution strategy, NornWeave preserves provenance metadata. The final response always attributes which domain agent contributed which piece of information, allowing users to trace back to the original source and make their own judgment.

---

## Failure Modes and Resilience

A distributed memory architecture introduces failure modes absent from monolithic systems. NornWeave addresses these:

| Failure Mode | Impact | Mitigation |
|-------------|--------|------------|
| Single agent unavailable | Partial recall — one domain missing | Graceful degradation; response notes which domains were unreachable |
| Router failure | No queries processed | Router is stateless and horizontally replicable |
| Fusion layer failure | Agents respond but results aren't synthesized | Fall back to returning raw per-domain results |
| Slow agent (timeout) | Query latency spike | Configurable per-agent timeouts; return partial results from responsive agents |
| Registry failure | New agents can't register | Agents cache last-known registry state; existing routing continues |
| Embedding store corruption | Domain recall degraded | Per-domain isolation prevents cross-domain contamination; rebuild single store |

The critical resilience property is **blast radius containment**: a failure in one domain agent cannot cascade to other domains. Each agent is an independent process with its own resources, stores, and failure boundaries.

---

## Performance Characteristics

### Expected Latency Bounds

| Phase | Expected Latency | Notes |
|-------|-----------------|-------|
| Routing | 10–50ms | Lightweight classifier inference |
| Per-agent retrieval | 50–200ms | Depends on store size and retrieval strategy |
| Fusion | 20–100ms | Scales with number of responding agents |
| **End-to-end** | **100–350ms** | **Parallel agent retrieval dominates** |

### Memory Footprint

Each domain agent maintains its own embedding index. Total system memory is the sum of all domain indices — but unlike a monolithic system, each index can be sized, optimized, and hosted independently. Low-traffic domains can use smaller, cheaper instances while high-value domains get dedicated resources.

### Throughput

With stateless agents behind load balancers, throughput scales linearly with replica count per domain. The router and fusion layer are lightweight and rarely the bottleneck — agent retrieval is the dominant cost.

---

## Comparison to Monolithic Memory Architectures

| Property | Monolithic Memory | NornWeave |
|----------|------------------|-----------|
| Knowledge breadth | Limited by single embedding space capacity | Scales with number of domain agents |
| Recall precision | Degrades as breadth increases | Maintained per-domain regardless of total breadth |
| Context budget | Single shared window | Independent per agent; total scales linearly |
| Failure blast radius | Total system failure | Contained to single domain |
| Scaling model | Vertical (bigger index, more RAM) | Horizontal (more agents, more replicas) |
| Deployment complexity | Low (single service) | Higher (multiple services, registry, orchestration) |
| Domain-specific tuning | Difficult (changes affect all domains) | Natural (each agent independently tuned) |
| Latency | Single retrieval call | Parallel multi-agent + fusion overhead |

NornWeave trades deployment simplicity for architectural properties that matter at scale: independent scaling, fault isolation, and domain-specific optimization without cross-domain interference.

---

## Future Directions

- **Inter-Agent Learning**: Agents that learn from the fusion layer's conflict resolution decisions, improving their own relevance calibration over time.
- **Dynamic Domain Discovery**: Automatic detection of emerging knowledge domains from ingestion patterns, with autonomous agent spawning.
- **Hierarchical Routing**: Multi-level routers for organizations with dozens of domains, using coarse-grained first-pass routing followed by fine-grained sub-domain selection.
- **Agent Collaboration Protocols**: Enabling agents to directly query each other for cross-domain context enrichment before responding to the fusion layer.
- **Federated NornWeave**: Connecting NornWeave instances across organizational boundaries, enabling cross-organization knowledge recall with access control preservation.

---

## License

NornWeave is licensed under the [GNU General Public License v3.0](LICENSE).
