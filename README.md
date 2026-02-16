# NornWeave

**Collaborative Recall Mesh**

A multi-agent architecture where specialized "memory agents" each maintain expertise in different domains. Query routing intelligently fans out recall requests to relevant experts, enabling virtually unlimited knowledge breadth while maintaining deep recall fidelity.

Think of it as building a team of savants instead of one forgetful polymath.

---

## Table of Contents

- [Motivation](#motivation)
- [Core Concepts](#core-concepts)
- [Architecture Overview](#architecture-overview)
  - [Domain Segmentation](#domain-segmentation)
  - [Router Agent](#router-agent)
  - [Response Fusion](#response-fusion)
  - [Specialization Training](#specialization-training)
- [System Design](#system-design)
  - [Query Lifecycle](#query-lifecycle)
  - [Memory Agent Anatomy](#memory-agent-anatomy)
  - [Conflict Resolution](#conflict-resolution)
  - [Consistency Model](#consistency-model)
- [Delivery Format](#delivery-format)
  - [Framework Design](#framework-design)
  - [Agent Configuration](#agent-configuration)
  - [Docker Compose Deployment](#docker-compose-deployment)
  - [Horizontal Scaling](#horizontal-scaling)
- [Theoretical Foundations](#theoretical-foundations)
  - [Why Partition Memory](#why-partition-memory)
  - [Fan-Out vs. Monolithic Recall](#fan-out-vs-monolithic-recall)
  - [Bounded Expertise Hypothesis](#bounded-expertise-hypothesis)
- [Failure Modes and Mitigations](#failure-modes-and-mitigations)
- [Future Directions](#future-directions)
- [License](#license)

---

## Motivation

Traditional monolithic memory systems face a fundamental tension: as the volume of stored knowledge grows, recall precision degrades. A single retrieval mechanism must index, rank, and surface information across wildly different domains (source code, natural language documentation, conversational history, research papers), each with its own structure, semantics, and retrieval patterns. The result is a system that is acceptably good at everything but deeply good at nothing. The dreaded "jack of all trades, master of none," except it's not even a jack; it's more like a distracted intern with too many browser tabs open.

NornWeave reframes the problem. Instead of asking one system to recall everything (a task that would make even Odin's ravens file a grievance), it distributes the responsibility across a mesh of cooperating specialists. Each memory agent owns a bounded domain and can invest all of its representational capacity in understanding that domain's structure. A lightweight routing layer ensures that incoming queries reach the right experts, and a fusion layer reconciles their answers into a coherent response.

The architecture draws its name from the Norns of Norse mythology: Urðr, Verðandi, and Skuld, weavers of fate who each tend a distinct thread while collaborating on a shared tapestry. We're doing the same thing, just with fewer prophecies and more vector embeddings.

---

## Core Concepts

| Concept             | Definition                                                                                                                                                                                 |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Memory Agent**    | An autonomous, domain-scoped service responsible for ingesting, indexing, and recalling knowledge within a single domain. Essentially a very focused librarian who never takes a sick day. |
| **Domain**          | A bounded category of knowledge with shared structure and retrieval semantics (e.g., "source code," "API documentation," "conversation logs").                                             |
| **Router Agent**    | A stateless classifier that inspects an incoming query and determines which memory agents are relevant. The traffic cop of the operation, except it actually does its job efficiently.     |
| **Recall Request**  | A structured query dispatched from the router to one or more memory agents, carrying the original query text plus routing metadata.                                                        |
| **Response Fusion** | The process of combining, deduplicating, ranking, and conflict-resolving answers from multiple memory agents into a single coherent response.                                              |
| **Recall Fidelity** | A measure of how accurately and completely a memory agent surfaces the most relevant stored knowledge for a given query. High fidelity = the good stuff floats to the top.                 |

---

## Architecture Overview

```
                          +------------------+
                          |   Incoming Query  |
                          +--------+---------+
                                   |
                                   v
                          +--------+---------+
                          |   Router Agent    |
                          |  (classification  |
                          |   & fan-out)      |
                          +--+-----+------+--+
                             |     |      |
                    +--------+  +--+--+  +--------+
                    v           v     v           v
              +-----+---+ +----+--+ +-+-------+ +-+----------+
              |  Code    | | Docs  | | Convo   | | Research   |
              |  Memory  | | Memory| | Memory  | | Memory     |
              |  Agent   | | Agent | | Agent   | | Agent      |
              +-----+---+ +----+--+ +-+-------+ +-+----------+
                    |           |       |              |
                    +-----+----+---+---+----+---------+
                          |        |        |
                          v        v        v
                    +-----+--------+--------+-----+
                    |      Response Fusion         |
                    |   (aggregation, ranking,     |
                    |    conflict resolution)       |
                    +-----+------------------------+
                          |
                          v
                    +-----+--------+
                    |  Unified     |
                    |  Response    |
                    +--------------+
```

### Domain Segmentation

Knowledge is partitioned into discrete domains, each served by a dedicated memory agent. The segmentation is not arbitrary; it reflects genuine structural and semantic differences in how different kinds of knowledge are best represented, indexed, and retrieved.

You wouldn't ask a marine biologist to perform heart surgery (even if they're very confident about it). Same principle.

**Default Domain Partition:**

| Domain                | Content                                                             | Indexing Strategy                                                                    | Retrieval Pattern                                                    |
| --------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | -------------------------------------------------------------------- |
| **Code**              | Source files, ASTs, dependency graphs, commit history               | Structural indexing (symbol tables, call graphs), semantic embeddings of code blocks | Symbol lookup, semantic similarity, structural traversal             |
| **Documentation**     | API docs, READMEs, architecture decision records, runbooks          | Hierarchical section indexing, semantic embeddings                                   | Section-scoped search, concept matching, cross-reference resolution  |
| **Conversations**     | Chat logs, issue threads, PR discussions, meeting transcripts       | Temporal indexing, participant-tagged embeddings, thread-structure preservation      | Temporal range queries, participant-scoped search, topic clustering  |
| **External Research** | Papers, articles, Stack Overflow answers, third-party documentation | Citation-graph indexing, semantic embeddings, provenance tracking                    | Citation-aware search, recency-weighted retrieval, authority ranking |

Each domain may employ a different underlying storage engine, embedding model, or index structure. The architecture does not impose uniformity. A code memory agent might lean on tree-sitter for structural parsing while a documentation agent uses hierarchical chunking. This heterogeneity is a feature, not a deficiency: it allows each agent to optimize for its domain's unique retrieval characteristics.

**Domain boundaries are configurable.** A deployment might split "Code" into "Application Code" and "Infrastructure Code," or merge "Documentation" and "External Research" if the distinction is not meaningful for a given use case. The framework treats domain definitions as configuration, not hard-coded categories. Your mesh, your rules.

### Router Agent

The router agent is the system's entry point. It receives raw queries and makes routing decisions, determining which memory agents should participate in answering a given query.

**Design Principles:**

1. **Stateless.** The router holds no accumulated state between requests. Routing decisions are made purely from the query content and a static (or slowly-updating) domain registry. This makes the router horizontally scalable and trivially replaceable. It has the memory of a goldfish, and that's the point.

2. **Multi-target.** A single query may be routed to multiple memory agents. The question "How does the authentication service handle token refresh, and what did the team decide about refresh token rotation in last month's architecture review?" naturally spans the Code, Documentation, and Conversations domains.

3. **Lightweight.** The router should be the cheapest component in the pipeline. It performs classification, not deep retrieval. Acceptable implementations range from a fine-tuned small language model to a keyword-and-heuristic classifier to a zero-shot prompt against a fast LLM. This isn't where you splurge your compute budget.

**Routing Mechanism:**

```
Input:  raw query string
Output: list of (domain_id, relevance_score, rewritten_query) tuples

Steps:
  1. Extract domain signals from the query (keywords, structure, explicit references)
  2. Score each registered domain against the extracted signals
  3. Apply threshold filtering (discard domains below minimum relevance)
  4. Optionally rewrite the query per-domain to improve recall
     (e.g., extracting a function name for the code agent,
      a date range for the conversation agent)
  5. Return the routing plan
```

Query rewriting at step 4 is an important subtlety, and a surprisingly fun one. A query like "what changed in the payment module after the outage on Jan 15" benefits from being decomposed: the code agent receives a query focused on the payment module's recent diffs, the conversation agent receives a query scoped to the Jan 15 timeframe, and the documentation agent receives a query about the payment module's architecture. One question, three perfectly tailored sub-questions. The router is basically a universal translator for intent.

### Response Fusion

When a query fans out to multiple memory agents, the system must reconcile their independent responses into a single coherent answer. This is a non-trivial problem that extends well beyond simple concatenation. (If you've ever tried to merge conflicting Google Docs edits at 2 AM, you have a visceral understanding of why.)

**Fusion Pipeline:**

1. **Collection.** Gather responses from all participating memory agents. Impose a timeout: if an agent does not respond within the deadline, proceed without it and annotate the response with a coverage gap. We don't wait for stragglers; we just take notes about who was late.

2. **Normalization.** Convert all responses into a common intermediate representation. Each response item carries: the content, a source citation, a relevance score (as assessed by the originating agent), and a domain tag.

3. **Deduplication.** Identify and merge items that convey the same information surfaced by different agents. For example, the code agent and the documentation agent may both reference the same API endpoint. The fusion layer should recognize the overlap and present a single, enriched entry rather than two redundant ones.

4. **Conflict Resolution.** When agents return contradictory information, the fusion layer must adjudicate. Strategies include:
   - **Recency preference:** Favor the most recently updated source.
   - **Source authority:** Rank by domain (e.g., the code agent's view of current behavior outranks documentation that may be stale).
   - **Confidence weighting:** Use the agents' own relevance scores as tiebreakers.
   - **Explicit flagging:** Surface the contradiction to the caller rather than silently resolving it. Because sometimes "these two disagree" _is_ the answer.

5. **Ranking.** Produce a final ordering of response items by composite relevance, accounting for cross-domain signal reinforcement (an item corroborated by multiple agents ranks higher).

6. **Synthesis.** Optionally, pass the ranked items through a synthesis model that produces a natural language summary. This step is configurable; some consumers want raw ranked results, others want a narrative answer.

### Specialization Training

Each memory agent is tuned (through fine-tuning, prompt engineering, retrieval parameter optimization, or a combination) to excel at its domain's specific retrieval patterns. Generic is the enemy of great.

**Specialization Dimensions:**

- **Embedding Model Selection.** Code agents benefit from code-specific embedding models (e.g., models trained on code-comment pairs) rather than general-purpose text embeddings. Documentation agents benefit from models that understand hierarchical document structure.

- **Chunking Strategy.** How knowledge is segmented for storage differs by domain. Code is best chunked at the function or class level, respecting syntactic boundaries. Documentation chunks along section headers. Conversations chunk along message boundaries or topic shifts. One size fits nobody.

- **Retrieval Prompting.** When agents use LLM-assisted retrieval (e.g., generating hypothetical answers to improve embedding search), the prompt templates are domain-specific. A code agent's hypothetical answer template differs substantially from a conversation agent's.

- **Reranking Criteria.** Post-retrieval reranking uses domain-appropriate signals. Code agents rerank by structural proximity (how close the result is in the call graph to the query target). Documentation agents rerank by section depth and cross-reference density. Conversation agents rerank by temporal proximity and participant relevance.

---

## System Design

### Query Lifecycle

A complete query flows through the system like a well-orchestrated relay race (minus the baton drops):

```
1. INGEST        Client submits a natural language query
2. CLASSIFY      Router agent analyzes the query and produces a routing plan
3. FAN-OUT       Router dispatches recall requests to selected memory agents (in parallel)
4. RECALL        Each memory agent independently searches its domain store
5. RESPOND       Memory agents return ranked results with citations
6. COLLECT       Fusion layer gathers all responses (with timeout handling)
7. FUSE          Fusion layer normalizes, deduplicates, resolves conflicts, and ranks
8. SYNTHESIZE    (Optional) Synthesis model produces a narrative answer
9. DELIVER       Unified response returned to the client
```

Steps 3-5 execute in parallel across agents. The fan-out is non-blocking; the fusion layer begins processing as soon as any agent responds and continues incrementally as more responses arrive, up to the configured timeout.

### Memory Agent Anatomy

Each memory agent is a self-contained service with a common interface and domain-specific internals.

**Common Interface (all agents implement):**

```
recall(query: RecallRequest) -> RecallResponse
ingest(documents: List[Document]) -> IngestResult
health() -> HealthStatus
describe() -> DomainDescriptor
```

- `recall`: Accept a query, search the domain store, return ranked results.
- `ingest`: Accept new documents for indexing into the domain store.
- `health`: Report agent status, index size, last update time.
- `describe`: Return a machine-readable description of the domain this agent covers, used by the router for dynamic domain discovery. It's essentially the agent's elevator pitch.

**Internal Components (domain-specific):**

```
+--------------------------------------------------+
|                  Memory Agent                     |
|                                                   |
|  +-----------+  +-----------+  +---------------+  |
|  | Ingestion |  |  Index    |  |  Retrieval    |  |
|  | Pipeline  |->|  Store    |<-|  Engine       |  |
|  +-----------+  +-----------+  +---------------+  |
|       |                             |              |
|  +-----------+              +---------------+      |
|  | Chunking  |              |  Reranker     |      |
|  | Strategy  |              |  (domain-     |      |
|  +-----------+              |   specific)   |      |
|                             +---------------+      |
+--------------------------------------------------+
```

### Conflict Resolution

Cross-domain conflicts are inevitable. The documentation says the API returns XML, but the code clearly returns JSON. The conversation from three months ago says the feature was deprioritized, but the code shows it was implemented last week. Welcome to software engineering, where the map and the territory are in a perpetual cold war.

NornWeave treats conflicts as information, not errors. The default resolution strategy is:

1. **Code trumps documentation** for questions about current system behavior (code is the ground truth of what the system _does_; the docs are what someone _wished_ it did).
2. **Documentation trumps conversation** for questions about intended design (conversations are informal and often exploratory, and half of Slack is brainstorming and emoji reactions).
3. **Recency trumps age** when two sources of the same type disagree (the more recent commit, the more recent doc update).
4. **When in doubt, surface the conflict.** Present both versions with their provenance and let the consumer decide. Transparency over false confidence.

These defaults are overridable per deployment.

### Consistency Model

NornWeave operates under an **eventual consistency** model. When new knowledge is ingested into one domain agent, other agents are not immediately aware of it. This is acceptable because:

- Each agent's domain is independent; code changes don't invalidate the conversation agent's index.
- Cross-domain consistency matters only at the fusion layer, which already handles contradictions like a seasoned diplomat.
- Strict consistency across agents would require distributed coordination that undermines the architecture's scalability goals. We chose "fast and eventually right" over "slow and immediately right."

Agents publish ingestion events to a shared event bus. Other agents may optionally subscribe to relevant cross-domain events (e.g., the documentation agent might listen for code change events to flag potentially stale docs), but this is advisory, not transactional.

---

## Delivery Format

### Framework Design

NornWeave is designed as a **composable framework**, not a monolithic application. Users define their memory agents, routing logic, and fusion strategies through configuration, then deploy the resulting system using standard containerization tooling.

**Design Goals:**

- **Declarative agent definition.** Define a memory agent by specifying its domain, ingestion pipeline, storage backend, and retrieval strategy in a configuration file. No custom code required for standard use cases. YAML is your friend here. (Tabs vs. spaces doesn't apply; it's always spaces. Sorry.)
- **Pluggable components.** Every major component (router, agents, fusion layer, storage backends) is defined by an interface. Swap implementations without changing the rest of the system. Lego bricks, not a Jenga tower.
- **Local-first development.** The entire mesh should run on a single developer machine via Docker Compose. Production deployments scale horizontally with the same configuration.
- **Incremental adoption.** Start with one memory agent. Add more as needed. The router adapts automatically when agents register or deregister. No big-bang migrations required.

### Agent Configuration

Memory agents are defined in YAML configuration files. Each file specifies everything the framework needs to instantiate, configure, and register an agent.

```yaml
# agents/code-memory.yaml
agent:
  name: code-memory
  domain: code
  description: "Source code, ASTs, dependency graphs, and commit history"

ingestion:
  sources:
    - type: git-repository
      path: /data/repos
      watch: true
      poll_interval: 60s
  chunking:
    strategy: syntax-aware
    languages: [python, typescript, go]
    max_chunk_tokens: 512

storage:
  backend: pgvector
  connection: ${PGVECTOR_URL}
  embedding_model: code-embedding-v2
  embedding_dimensions: 768

retrieval:
  top_k: 20
  reranker:
    model: cross-encoder-code-v1
    top_n: 5
  filters:
    - recency_boost: 0.1
    - structural_proximity: 0.2

health:
  port: 8081
  check_interval: 30s
```

```yaml
# agents/docs-memory.yaml
agent:
  name: docs-memory
  domain: documentation
  description: "API docs, READMEs, ADRs, and runbooks"

ingestion:
  sources:
    - type: filesystem
      path: /data/docs
      watch: true
      glob: "**/*.md"
    - type: url-crawl
      seeds:
        - https://docs.example.com
      depth: 3
      refresh_interval: 24h
  chunking:
    strategy: hierarchical-sections
    max_chunk_tokens: 1024
    preserve_headers: true

storage:
  backend: pgvector
  connection: ${PGVECTOR_URL}
  embedding_model: text-embedding-v3
  embedding_dimensions: 1536

retrieval:
  top_k: 15
  reranker:
    model: cross-encoder-text-v1
    top_n: 5
  filters:
    - section_depth_boost: 0.15
```

### Docker Compose Deployment

A standard deployment uses Docker Compose to orchestrate the mesh locally. Copy, paste, `up -d`, and you're weaving.

```yaml
# docker-compose.yaml
services:
  router:
    build: ./services/router
    ports:
      - "8080:8080"
    environment:
      - AGENT_REGISTRY_URL=http://registry:8500
      - ROUTER_MODEL=${ROUTER_MODEL:-keyword-heuristic}
      - ROUTER_THRESHOLD=0.3
    depends_on:
      - registry

  fusion:
    build: ./services/fusion
    environment:
      - AGENT_REGISTRY_URL=http://registry:8500
      - FUSION_TIMEOUT=5s
      - CONFLICT_STRATEGY=recency-then-flag
    depends_on:
      - registry

  registry:
    build: ./services/registry
    ports:
      - "8500:8500"
    volumes:
      - registry-data:/data

  code-memory:
    build: ./services/memory-agent
    environment:
      - AGENT_CONFIG=/config/code-memory.yaml
      - PGVECTOR_URL=postgres://nornweave:${DB_PASS}@pgvector:5432/code
    volumes:
      - ./agents/code-memory.yaml:/config/code-memory.yaml
      - ./data/repos:/data/repos:ro
    depends_on:
      - pgvector
      - registry

  docs-memory:
    build: ./services/memory-agent
    environment:
      - AGENT_CONFIG=/config/docs-memory.yaml
      - PGVECTOR_URL=postgres://nornweave:${DB_PASS}@pgvector:5432/docs
    volumes:
      - ./agents/docs-memory.yaml:/config/docs-memory.yaml
      - ./data/docs:/data/docs:ro
    depends_on:
      - pgvector
      - registry

  convo-memory:
    build: ./services/memory-agent
    environment:
      - AGENT_CONFIG=/config/convo-memory.yaml
      - PGVECTOR_URL=postgres://nornweave:${DB_PASS}@pgvector:5432/convo
    volumes:
      - ./agents/convo-memory.yaml:/config/convo-memory.yaml
    depends_on:
      - pgvector
      - registry

  pgvector:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_USER=nornweave
      - POSTGRES_PASSWORD=${DB_PASS}
    volumes:
      - pgvector-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

volumes:
  pgvector-data:
  registry-data:
```

To bring up the mesh:

```bash
docker compose up -d
```

To add a new domain agent, add a new service block referencing a new agent configuration file and restart. The registry detects the new agent, and the router begins including it in routing decisions. No code changes required. Just YAML and vibes.

### Horizontal Scaling

NornWeave is designed to scale along three axes:

**1. Domain Breadth (adding agents).**
Adding a new domain is an additive operation. Write a new agent configuration file, add a service entry to the deployment manifest, and start the container. The agent self-registers with the registry. The router discovers it via the registry and incorporates its `describe()` output into routing decisions. No existing agent or the router itself needs modification. It's plug-and-play, minus the part where nothing works on the first try.

**2. Domain Depth (scaling individual agents).**
A single domain agent can be scaled horizontally by running multiple replicas behind a load balancer. Each replica shares the same backing store. This is standard stateless service scaling; the agent's recall interface is idempotent and safe to parallelize.

**3. Query Throughput (scaling the router and fusion layer).**
The router is stateless and can be replicated freely. The fusion layer holds only transient state (in-flight query responses) and can be partitioned by query ID across replicas.

```
                    Load Balancer
                         |
              +----------+----------+
              |          |          |
           Router     Router     Router
           (replica)  (replica)  (replica)
              |          |          |
              +-----+----+----+----+
                    |         |
         +----------+    +----+-----+
         |               |          |
    Code Agent      Code Agent    Docs Agent
    (replica 1)     (replica 2)   (replica 1)
         |               |          |
         +-------+-------+    +----+
                 |             |
              pgvector      pgvector
              (code)        (docs)
```

---

## Theoretical Foundations

### Why Partition Memory

The case for partitioned memory rests on an observation about retrieval systems: **a retrieval mechanism tuned for one domain's structure systematically underperforms on other domains.** Code retrieval benefits from structural awareness (ASTs, call graphs, type hierarchies). Document retrieval benefits from hierarchical section awareness. Conversation retrieval benefits from temporal and participant-based indexing. These are not minor optimizations. They represent fundamentally different retrieval geometries.

It's the difference between "search" and "_find_."

A monolithic system must either use a single generic retrieval mechanism (sacrificing per-domain performance) or build a complex multi-strategy retrieval engine (concentrating complexity in a single service that becomes a maintenance black hole). NornWeave sidesteps this by giving each domain its own service with its own strategy, connected by a thin coordination layer.

### Fan-Out vs. Monolithic Recall

**Monolithic recall** sends every query against a single unified index. Advantages: simplicity, no routing overhead, no fusion complexity. Disadvantages: index pollution (irrelevant domains dilute result quality), inability to tune per-domain, scaling constraints (the index must handle all domains).

**Fan-out recall** (NornWeave's approach) routes each query to relevant domain specialists. Advantages: per-domain tuning, independent scaling, isolation (a misbehaving agent doesn't corrupt other domains). Disadvantages: routing latency, fusion complexity, potential for missed cross-domain connections if the router is imprecise.

The fan-out approach trades coordination complexity for specialization depth. This trade-off favors fan-out when:

- The knowledge base spans structurally diverse domains.
- Individual domains are large enough to benefit from specialized retrieval.
- Cross-domain queries are the minority (most queries have a clear primary domain).
- The deployment requires independent evolution of domain capabilities.

If your use case is a single-domain corpus with homogeneous content, monolithic recall is probably the right call. NornWeave isn't dogma; it's a tool, and tools should fit the job.

### Bounded Expertise Hypothesis

NornWeave is built on the hypothesis that **bounded expertise outperforms unbounded generalism for recall tasks.** A memory agent that knows everything about code retrieval (the right chunking boundaries, the right embedding model, the right reranking signals) will outperform a general-purpose system on code queries, even if the general-purpose system has access to the same underlying data.

This is analogous to the organizational insight that a team of specialists with a coordinator outperforms a team of generalists on complex problems, provided the coordination overhead is manageable. NornWeave's architecture keeps coordination overhead low by making the router stateless and classification-only, and by limiting cross-agent interaction to the well-defined fusion stage.

Or, in D&D terms: a party of min-maxed specialists with a good battle plan will wipe the floor with a party of "balanced" characters every time. The router is your bard. It doesn't do the heavy lifting, but the party falls apart without it.

---

## Failure Modes and Mitigations

Nothing is bulletproof. But you can at least know where the dents will appear.

| Failure Mode                 | Impact                                                                                           | Mitigation                                                                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| **Router misclassification** | Query sent to wrong agents; relevant results missed                                              | Bias the router toward inclusive routing (lower thresholds), accept minor latency cost from querying extra agents            |
| **Agent timeout**            | Partial results returned                                                                         | Fusion layer annotates response with coverage gaps; client can retry with extended timeout                                   |
| **Agent crash**              | Domain unavailable                                                                               | Health checks trigger alerts; registry deregisters unhealthy agents; router stops routing to them                            |
| **Storage corruption**       | Agent returns stale or incorrect results                                                         | Per-agent index rebuilds from source; agents are stateless beyond their backing store                                        |
| **Fusion conflicts**         | Contradictory information from different agents                                                  | Explicit conflict surfacing (default); configurable resolution strategies                                                    |
| **Cross-domain gap**         | Information that spans domain boundaries is split across agents and neither has the full picture | Router rewrites queries per-domain to maximize each agent's coverage; fusion layer detects and joins cross-domain references |
| **Router overload**          | Query ingestion bottleneck                                                                       | Router is stateless and horizontally scalable; deploy multiple replicas behind a load balancer                               |

---

## Future Directions

- **Adaptive Routing.** The router learns from fusion outcomes. If certain routing decisions consistently produce low-relevance results, the router adjusts its classification weights. This creates a feedback loop that improves routing precision over time without manual tuning. The router gets street-smart.

- **Inter-Agent Cross-References.** Memory agents can reference each other's content by ID, enabling the fusion layer to produce richer responses that explicitly link related information across domains (e.g., linking a code function to its documentation and the conversation where it was designed).

- **Dynamic Domain Splitting.** When a domain agent's index grows beyond a performance threshold, the system can automatically propose or execute a domain split, partitioning one agent into two more specialized agents (e.g., splitting "Code" into "Backend Code" and "Frontend Code"). Mitosis, but for microservices.

- **Federated Deployments.** Multiple NornWeave meshes can be connected, with routers capable of forwarding queries to external meshes when local agents lack domain coverage. Like a mesh of meshes. A meta-mesh, if you will.

- **Active Forgetting.** Agents implement decay functions that gradually reduce the retrieval weight of stale information, preventing index pollution from outdated knowledge without requiring manual curation. Because sometimes the best thing a memory can do is fade.

---

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.
