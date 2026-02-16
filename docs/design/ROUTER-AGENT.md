# NornWeave — Router Agent Design

> Design specification for the Router Agent: the system's entry point responsible for query classification, domain routing, and query rewriting. References the [Domain Model](DOMAIN-MODEL.md) for type definitions and [Service Contracts](SERVICE-CONTRACTS.md) for API surface.

---

## Table of Contents

- [Responsibilities](#responsibilities)
- [Query Lifecycle](#query-lifecycle)
- [Classification Backends](#classification-backends)
  - [Keyword-Heuristic Backend](#keyword-heuristic-backend)
  - [Sklearn-Classifier Backend](#sklearn-classifier-backend)
  - [LLM-Zero-Shot Backend](#llm-zero-shot-backend)
  - [Backend Comparison](#backend-comparison)
  - [Backend Selection](#backend-selection)
- [Threshold Behavior](#threshold-behavior)
  - [Confidence Scoring](#confidence-scoring)
  - [Routing Thresholds](#routing-thresholds)
  - [Edge Cases](#edge-cases)
- [Query Rewriting](#query-rewriting)
  - [Rewrite Strategies](#rewrite-strategies)
  - [Rewrite Pipeline](#rewrite-pipeline)
  - [Examples](#examples)
- [Domain Discovery](#domain-discovery)
- [Fan-Out Orchestration](#fan-out-orchestration)
- [Configuration](#configuration)
- [Internal Architecture](#internal-architecture)

---

## Responsibilities

The router has exactly three jobs:

1. **Classify** incoming queries to determine which domains are relevant.
2. **Rewrite** the query into domain-optimized variants, one per target domain.
3. **Fan out** the rewritten queries to the appropriate memory agents.

The router does not search, rank, fuse, or synthesize. It is a lightweight, stateless dispatcher. Its entire job is to make sure the right questions reach the right experts.

---

## Query Lifecycle

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Router Agent Pipeline                         │
│                                                                      │
│  ┌────────────┐   ┌────────────────┐   ┌───────────────────────┐    │
│  │ 1. RECEIVE │──▶│ 2. VALIDATE    │──▶│ 3. CLASSIFY           │    │
│  │            │   │   + assign IDs │   │   (backend-dependent) │    │
│  └────────────┘   └────────────────┘   └───────────┬───────────┘    │
│                                                     │                │
│                                                     ▼                │
│  ┌────────────┐   ┌────────────────┐   ┌───────────────────────┐    │
│  │ 6. FAN-OUT │◀──│ 5. BUILD PLAN  │◀──│ 4. REWRITE            │    │
│  │  (parallel)│   │  (RoutingPlan) │   │   (per-domain)        │    │
│  └─────┬──────┘   └────────────────┘   └───────────────────────┘    │
│        │                                                             │
│        ▼                                                             │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │ 7. COLLECT responses (with per-agent timeout)              │      │
│  │    └── log CoverageGap for any timed-out agent            │      │
│  └────────────────────────────┬───────────────────────────────┘      │
│                               │                                      │
│                               ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ 8. FORWARD to Fusion Service (POST /fuse)                    │    │
│  │    └── return FusionResult to client                         │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

**Step details:**

| Step | Action                                              | Budget                             | Failure Mode                   |
| ---- | --------------------------------------------------- | ---------------------------------- | ------------------------------ |
| 1    | Parse JSON, extract `query_text`                    | —                                  | `400 INVALID_REQUEST`          |
| 2    | Token-count the query, assign `QueryId` + `TraceId` | —                                  | `400 QUERY_TOO_LONG`           |
| 3    | Run the configured classification backend           | 2,000 ms                           | Fall back to broadcast routing |
| 4    | Generate per-domain rewrites                        | 500 ms (included in step 3 budget) | Use original query unchanged   |
| 5    | Build `RoutingPlan` from signals + rewrites         | < 1 ms                             | —                              |
| 6    | Send `RecallRequest` to each target agent           | —                                  | —                              |
| 7    | Await responses up to per-agent deadline            | 5,000 ms per agent                 | `CoverageGap` annotation       |
| 8    | Forward collected responses to fusion               | 10,000 ms                          | `500 FUSION_FAILED`            |

---

## Classification Backends

The router supports three interchangeable classification backends. The backend is selected at startup via the `ROUTER_MODEL` environment variable and cannot be switched at runtime.

### Keyword-Heuristic Backend

**Config value:** `ROUTER_MODEL=keyword-heuristic`

A deterministic, rule-based classifier that uses keyword matching and pattern recognition. Zero external dependencies, zero latency variance, zero surprises.

**How it works:**

```
Query Text
    │
    ├── 1. Tokenize + normalize (lowercase, strip punctuation)
    │
    ├── 2. Match against domain keyword sets
    │      Each domain maintains a weighted keyword dictionary.
    │
    ├── 3. Apply pattern rules
    │      Regex patterns for structural signals (file paths, code syntax, etc.)
    │
    ├── 4. Score domains by weighted match count
    │
    └── 5. Return DomainSignal[] sorted by score, descending
```

**Domain Keyword Dictionaries:**

| Domain          | High-Weight Keywords (1.0)                                | Medium-Weight Keywords (0.5)                    | Pattern Rules                                          |
| --------------- | --------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------ |
| `code`          | `function`, `class`, `variable`, `import`, `error`, `bug` | `module`, `package`, `library`, `dependency`    | File path patterns (`src/`, `.py`, `.ts`), code fences |
| `documentation` | `readme`, `docs`, `api`, `reference`, `guide`, `tutorial` | `architecture`, `specification`, `runbook`      | Markdown headers, URL patterns (`/docs/`)              |
| `conversations` | `said`, `discussed`, `meeting`, `thread`, `slack`, `chat` | `told`, `mentioned`, `agreed`, `decided`        | @-mentions, date references ("last Tuesday")           |
| `research`      | `paper`, `study`, `citation`, `arxiv`, `published`        | `journal`, `abstract`, `findings`, `hypothesis` | DOI patterns, citation formats (`[1]`, `et al.`)       |

**Scoring formula:**

```
domain_score = (Σ high_weight_matches × 1.0 + Σ medium_weight_matches × 0.5 + Σ pattern_matches × 0.75)
               ÷ max_possible_score_for_domain
```

**Strengths:** Deterministic, fast (< 1 ms), no model loading, testable with unit tests.
**Weaknesses:** Rigid; struggles with ambiguous or novel queries that don't contain dictionary keywords.

---

### Sklearn-Classifier Backend

**Config value:** `ROUTER_MODEL=sklearn-classifier`

A lightweight machine learning classifier using TF-IDF vectorization and logistic regression. Trained on labeled query–domain pairs.

**How it works:**

```
Query Text
    │
    ├── 1. TF-IDF vectorize the query
    │      (using the pre-fitted TfidfVectorizer)
    │
    ├── 2. Predict class probabilities
    │      LogisticRegression.predict_proba() → probability per domain
    │
    ├── 3. Convert probabilities to DomainSignals
    │      Each domain gets a DomainSignal with score = class probability
    │
    └── 4. Return DomainSignal[] sorted by score, descending
```

**Model Pipeline:**

```python
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier

pipeline = Pipeline([
    ("tfidf", TfidfVectorizer(
        max_features=10_000,
        ngram_range=(1, 2),
        sublinear_tf=True,
    )),
    ("classifier", OneVsRestClassifier(
        LogisticRegression(
            C=1.0,
            max_iter=1000,
            class_weight="balanced",
        )
    )),
])
```

**Multi-label classification:** Wrapping `LogisticRegression` in `OneVsRestClassifier` allows the model to assign a query to _multiple_ domains simultaneously. A query like "what does the payment handler do according to the design doc" should route to both `code` and `documentation`.

**Training Data:**

| Source                            | Label Strategy                               | Expected Volume   |
| --------------------------------- | -------------------------------------------- | ----------------- |
| Synthetic query templates         | Hand-labeled domain assignments              | 500–1,000 samples |
| Historical queries (if available) | Labeled by which agent returned best results | Grows over time   |
| Augmented queries                 | Paraphrased versions of labeled queries      | 2× base volume    |

**Model Persistence:**

- Serialized via `joblib` to `router/models/domain_classifier.joblib`.
- Loaded at startup. The router fails to start if the model file is missing.
- Retraining is offline; deploy a new model file and restart.

**Strengths:** Handles novel phrasings, generalizes beyond exact keyword matches, sub-10 ms inference.
**Weaknesses:** Requires labeled training data, model may drift as domain definitions evolve, retraining is manual.

---

### LLM-Zero-Shot Backend

**Config value:** `ROUTER_MODEL=llm-zero-shot`

Uses a large language model for zero-shot classification via `litellm`. The most flexible backend but also the slowest and most expensive.

**How it works:**

```
Query Text
    │
    ├── 1. Build classification prompt
    │      Inject query + domain descriptions from registry
    │
    ├── 2. Call LLM via litellm
    │      Structured output: JSON array of domain → confidence pairs
    │
    ├── 3. Parse LLM response
    │      Extract domain IDs and confidence scores
    │
    └── 4. Return DomainSignal[] sorted by score, descending
```

**Prompt Template:**

```
You are a query router for a multi-domain knowledge system.

Given the following query, classify it into one or more knowledge domains.
For each relevant domain, assign a confidence score between 0.0 and 1.0.

Available domains:
{domain_descriptions}

Query: "{query_text}"

Respond with a JSON array of objects, each with "domain_id" and "confidence" keys.
Only include domains with confidence >= 0.1. Example:
[
  {"domain_id": "code", "confidence": 0.9},
  {"domain_id": "documentation", "confidence": 0.4}
]
```

`{domain_descriptions}` is populated dynamically from the registry's `DomainDescriptor` list, so the prompt adapts automatically when agents register or deregister.

**LLM Configuration:**

| Parameter      | Default           | Configurable Via         |
| -------------- | ----------------- | ------------------------ |
| Model          | `gpt-4o-mini`     | `ROUTER_LLM_MODEL`       |
| Temperature    | `0.0`             | `ROUTER_LLM_TEMPERATURE` |
| Max tokens     | `256`             | `ROUTER_LLM_MAX_TOKENS`  |
| Timeout        | `2,000 ms`        | `ROUTER_TIMEOUT_MS`      |
| Fallback model | `ollama/llama3.2` | `ROUTER_LLM_FALLBACK`    |

**Structured output enforcement:**

- Primary: Use the LLM's JSON mode if supported (OpenAI `response_format={"type": "json_object"}`).
- Fallback: Regex-extract the first JSON array from the response.
- Failure: If parsing fails after one retry, fall back to broadcast routing.

**Strengths:** Handles highly ambiguous or multi-intent queries, adapts to new domains without retraining, understands nuance.
**Weaknesses:** 200–2,000 ms latency, API cost, non-deterministic, requires external API access or local Ollama.

---

### Backend Comparison

| Property               | `keyword-heuristic` | `sklearn-classifier` | `llm-zero-shot`        |
| ---------------------- | ------------------- | -------------------- | ---------------------- |
| Latency (p50)          | < 1 ms              | 2–8 ms               | 200–2,000 ms           |
| Latency (p99)          | < 1 ms              | 15 ms                | 3,000 ms               |
| Dependencies           | None                | scikit-learn         | litellm + LLM provider |
| Training data required | No                  | Yes (500+ samples)   | No                     |
| Multi-domain queries   | Decent              | Good                 | Excellent              |
| Novel phrasings        | Poor                | Good                 | Excellent              |
| Deterministic          | Yes                 | Yes                  | No                     |
| Cost                   | Free                | Free                 | Per-token API cost     |
| Recommended for        | Dev, testing, CI    | Staging, production  | Complex deployments    |

---

### Backend Selection

```
                    ┌──────────────────────────┐
                    │  Is training data         │
                    │  available?               │
                    └──────────┬───────────────┘
                               │
                     Yes ──────┼────── No
                     │                   │
                     ▼                   ▼
              ┌──────────────┐   ┌───────────────────────┐
              │   sklearn-   │   │  Is LLM API access     │
              │  classifier  │   │  available?             │
              └──────────────┘   └──────────┬────────────┘
                                            │
                                  Yes ──────┼────── No
                                  │                   │
                                  ▼                   ▼
                           ┌──────────────┐   ┌──────────────┐
                           │ llm-zero-    │   │  keyword-    │
                           │ shot         │   │  heuristic   │
                           └──────────────┘   └──────────────┘
```

**Practical guidance:**

- Start with `keyword-heuristic` in early development. It requires no setup and makes router behavior trivially debuggable.
- Graduate to `sklearn-classifier` once you have 500+ labeled query–domain pairs from real usage.
- Use `llm-zero-shot` when query complexity justifies the latency cost, or when domains change frequently and retraining is impractical.

---

## Threshold Behavior

### Confidence Scoring

All three backends produce `DomainSignal[]` with scores on the `[0.0, 1.0]` range. The interpretation is consistent regardless of backend:

| Score Range  | Interpretation                                     |
| ------------ | -------------------------------------------------- |
| `0.9 – 1.0`  | Very high confidence. Route without hesitation.    |
| `0.6 – 0.89` | Confident. Route as a primary target.              |
| `0.3 – 0.59` | Uncertain. Include if within `MAX_DOMAINS` budget. |
| `0.1 – 0.29` | Low confidence. Include only in permissive mode.   |
| `0.0 – 0.09` | Noise. Never route.                                |

### Routing Thresholds

The router uses two thresholds to decide which domains receive the query:

| Threshold             | Default | Configurable Via             | Purpose                                          |
| --------------------- | ------- | ---------------------------- | ------------------------------------------------ |
| `PRIMARY_THRESHOLD`   | `0.6`   | `ROUTER_PRIMARY_THRESHOLD`   | Minimum score to be a primary routing target     |
| `SECONDARY_THRESHOLD` | `0.3`   | `ROUTER_SECONDARY_THRESHOLD` | Minimum score to be included as secondary target |
| `MAX_DOMAINS`         | `4`     | `ROUTER_MAX_DOMAINS`         | Maximum number of domains to route to            |

**Routing Decision Logic:**

```python
def select_targets(signals: list[DomainSignal]) -> list[DomainSignal]:
    # Sort descending by score
    ranked = sorted(signals, key=lambda s: s.score.value, reverse=True)

    # Always include primary targets
    primary = [s for s in ranked if s.score.value >= PRIMARY_THRESHOLD]

    # If no primaries, include secondary targets instead
    if not primary:
        secondary = [s for s in ranked if s.score.value >= SECONDARY_THRESHOLD]
        targets = secondary[:MAX_DOMAINS]
    else:
        # Pad primaries with secondaries up to budget
        remaining_budget = MAX_DOMAINS - len(primary)
        secondary = [
            s for s in ranked
            if SECONDARY_THRESHOLD <= s.score.value < PRIMARY_THRESHOLD
        ]
        targets = primary + secondary[:remaining_budget]

    return targets[:MAX_DOMAINS]
```

### Edge Cases

| Scenario                             | Behavior                                                 |
| ------------------------------------ | -------------------------------------------------------- |
| No signals above any threshold       | **Broadcast:** route to all registered domains           |
| Single signal above primary          | Route to one domain only (single-target query)           |
| All domains score equally            | Route to all (likely an ambiguous or meta-query)         |
| Domain in signal but not in registry | Skip that domain; log a warning                          |
| Client provides explicit `domains`   | Skip classification entirely; route to requested domains |
| Classification backend timeout       | Fall back to broadcast routing; log the timeout          |

**Broadcast routing** is the safety net. If the classifier can't decide, ask everyone. The fusion layer handles the rest. This ensures no relevant results are silently dropped.

---

## Query Rewriting

### Rewrite Strategies

Query rewriting transforms the original query into domain-optimized variants. The goal is to give each memory agent a query shaped for its domain's retrieval patterns.

Not every query benefits from rewriting. The router applies rewrites selectively based on rewrite rules.

| Strategy                 | Applied When                                      | Example Transformation                                                                                               |
| ------------------------ | ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Decomposition**        | Multi-intent query spanning domains               | "what changed in payments after the outage" → code: "payment module recent diffs", convo: "outage discussion Jan 15" |
| **Technical Expansion**  | Ambiguous reference that maps to a code construct | "the auth thing" → "authentication module, AuthService class, login flow"                                            |
| **Temporal Scoping**     | Query contains time references                    | "last week's changes" → add `since` filter, narrow query text                                                        |
| **Identity Passthrough** | Query is already domain-specific enough           | "class PaymentHandler" → no change                                                                                   |

### Rewrite Pipeline

```
Original Query
    │
    ├── 1. Detect rewrite signals
    │      Time references? Multi-intent? Ambiguous terms?
    │
    ├── 2. Generate rewrites
    │      ┌─ keyword-heuristic: template-based substitution
    │      ├─ sklearn-classifier: no rewrite capability (passthrough)
    │      └─ llm-zero-shot: prompt-based generation
    │
    ├── 3. Validate rewrites
    │      Token count within budget? Non-empty? Different from original?
    │
    └── 4. Attach to RoutingTargets
           rewritten_query field (null if passthrough)
```

**Backend-specific rewrite behavior:**

| Backend              | Rewrite Strategy                                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `keyword-heuristic`  | Template substitution only. Extracts temporal references and file paths into `filters`, appends domain keywords to query text. |
| `sklearn-classifier` | No rewrite capability. All targets receive the original query.                                                                 |
| `llm-zero-shot`      | Full rewrite via LLM. The classification prompt is extended to request per-domain query rewrites alongside confidence scores.  |

**LLM rewrite prompt extension:**

```
For each relevant domain, also provide an optimized query rewrite tailored to that
domain's retrieval patterns. The rewrite should help the domain agent find the most
relevant results.

Respond with a JSON array:
[
  {
    "domain_id": "code",
    "confidence": 0.9,
    "rewritten_query": "PaymentHandler class error handling methods, recent changes"
  },
  {
    "domain_id": "convo",
    "confidence": 0.6,
    "rewritten_query": "payment outage discussion January 15 incident response"
  }
]
```

### Examples

**Example 1: Multi-intent decomposition**

```
Original:  "what changed in the payment module after the outage on Jan 15"

Signal analysis:
  - "payment module" → code (0.85), documentation (0.55)
  - "outage on Jan 15" → conversations (0.80)
  - "what changed" → code (0.70)

Routing plan:
  ┌─────────────┬──────────────────────────────────────────────────────┐
  │ code (0.85) │ "payment module recent changes, diffs since Jan 15" │
  │ convo (0.80)│ "payment outage discussion Jan 15 incident"         │
  │ docs (0.55) │ "payment module architecture documentation"         │
  └─────────────┴──────────────────────────────────────────────────────┘
```

**Example 2: Single-domain, no rewrite needed**

```
Original:  "show me the PaymentHandler class"

Signal analysis:
  - "PaymentHandler class" → code (0.95)
  - No other signals above threshold.

Routing plan:
  ┌──────────────┬───────────────────────────────────────┐
  │ code (0.95)  │ null (identity passthrough)            │
  └──────────────┴───────────────────────────────────────┘
```

**Example 3: Ambiguous query, broadcast fallback**

```
Original:  "what is the current state of things"

Signal analysis:
  - All domains score below 0.3.

Routing plan:
  ┌─────────────────┬───────────────────────────────────────┐
  │ code (broadcast) │ "what is the current state of things" │
  │ docs (broadcast) │ "what is the current state of things" │
  │ convo (broadcast)│ "what is the current state of things" │
  │ research (bcast) │ "what is the current state of things" │
  └─────────────────┴───────────────────────────────────────┘
```

---

## Domain Discovery

The router does not hardcode domain knowledge. It discovers available domains dynamically via the service registry.

**Discovery lifecycle:**

```
┌──────────────────────────────────────────────────────┐
│ Startup                                              │
│  1. Query registry: GET /agents?status=READY         │
│  2. For each agent, cache DomainDescriptor           │
│  3. Build keyword dictionaries (heuristic backend)   │
│     or update prompt (LLM backend)                   │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ Runtime (periodic, every 30s)                        │
│  1. Re-query registry for agent list                 │
│  2. Diff against cached descriptors                  │
│  3. Add/remove domains as agents register/deregister │
│  4. Log changes at INFO level                        │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ On AgentLifecycleEvent (Kafka, optional)             │
│  Immediate refresh instead of waiting for poll cycle │
└──────────────────────────────────────────────────────┘
```

**Cache structure:**

| Key                  | Value                 | TTL                      |
| -------------------- | --------------------- | ------------------------ |
| `DomainId`           | `DomainDescriptor`    | 60s                      |
| `AgentId → base_url` | URL string            | 60s                      |
| `domain_keyword_map` | `dict[str, DomainId]` | Rebuilt on domain change |

---

## Fan-Out Orchestration

After classification and rewriting, the router dispatches `RecallRequest` messages to the selected agents in parallel.

**Implementation via `anyio` task groups:**

```python
async def fan_out(plan: RoutingPlan) -> tuple[list[RecallResponse], list[CoverageGap]]:
    responses: list[RecallResponse] = []
    gaps: list[CoverageGap] = []

    async with anyio.create_task_group() as tg:
        for target in plan.targets:
            tg.start_soon(
                recall_with_timeout,
                target,
                plan.query_id,
                responses,
                gaps,
            )

    return responses, gaps


async def recall_with_timeout(
    target: RoutingTarget,
    query_id: QueryId,
    responses: list[RecallResponse],
    gaps: list[CoverageGap],
) -> None:
    try:
        with anyio.fail_after(RECALL_TIMEOUT_MS / 1000):
            response = await http_client.post(
                f"{target.agent_url}/recall",
                json=RecallRequest(
                    query_id=query_id,
                    query_text=target.rewritten_query or plan.original_text,
                    original_text=plan.original_text,
                    domain_id=target.domain_id,
                    top_k=plan.top_k,
                    trace_id=plan.trace_id,
                    timeout_ms=RECALL_TIMEOUT_MS,
                ).model_dump(),
            )
            responses.append(RecallResponse.model_validate(response.json()))
    except TimeoutError:
        gaps.append(CoverageGap(
            domain_id=target.domain_id,
            agent_id=target.agent_id,
            reason=f"Agent did not respond within {RECALL_TIMEOUT_MS}ms",
        ))
    except Exception as exc:
        gaps.append(CoverageGap(
            domain_id=target.domain_id,
            agent_id=target.agent_id,
            reason=f"Agent recall failed: {exc}",
        ))
```

**Key behaviors:**

- All agent calls execute concurrently. The wall-clock time is bounded by the slowest agent (or the timeout).
- Failed agents produce `CoverageGap` annotations, not errors. The fusion service decides how to present partial results.
- The router uses `httpx.AsyncClient` with connection pooling. One connection pool per agent, reused across queries.

---

## Configuration

All configuration is via environment variables (read by `pydantic-settings`).

| Variable                     | Type    | Default                           | Description                                    |
| ---------------------------- | ------- | --------------------------------- | ---------------------------------------------- |
| `ROUTER_MODEL`               | `str`   | `keyword-heuristic`               | Classification backend                         |
| `ROUTER_PORT`                | `int`   | `8080`                            | HTTP listen port                               |
| `ROUTER_TIMEOUT_MS`          | `int`   | `2000`                            | Classification + rewrite budget                |
| `ROUTER_PRIMARY_THRESHOLD`   | `float` | `0.6`                             | Minimum score for primary routing              |
| `ROUTER_SECONDARY_THRESHOLD` | `float` | `0.3`                             | Minimum score for secondary routing            |
| `ROUTER_MAX_DOMAINS`         | `int`   | `4`                               | Max domains per query                          |
| `RECALL_TIMEOUT_MS`          | `int`   | `5000`                            | Per-agent recall deadline                      |
| `MAX_QUERY_TOKENS`           | `int`   | `4096`                            | Maximum query length                           |
| `REGISTRY_URL`               | `str`   | `http://registry:8083`            | Service registry address                       |
| `REGISTRY_POLL_INTERVAL_S`   | `int`   | `30`                              | Domain discovery poll interval                 |
| `ROUTER_LLM_MODEL`           | `str`   | `gpt-4o-mini`                     | LLM model (zero-shot backend only)             |
| `ROUTER_LLM_TEMPERATURE`     | `float` | `0.0`                             | LLM temperature (zero-shot backend only)       |
| `ROUTER_LLM_MAX_TOKENS`      | `int`   | `256`                             | LLM max output tokens (zero-shot backend only) |
| `ROUTER_LLM_FALLBACK`        | `str`   | `ollama/llama3.2`                 | Fallback LLM model (zero-shot backend only)    |
| `ROUTER_CLASSIFIER_PATH`     | `str`   | `models/domain_classifier.joblib` | Model file path (sklearn backend only)         |

---

## Internal Architecture

```
services/router/src/nornweave_router/
├── __init__.py
├── main.py                  # FastAPI app, lifespan hooks
├── api/
│   ├── __init__.py
│   ├── routes.py            # POST /query, GET /health, GET /ready
│   └── middleware.py        # Auth, tracing, request ID injection
├── classification/
│   ├── __init__.py
│   ├── base.py              # ClassificationBackend protocol
│   ├── keyword.py           # KeywordHeuristicBackend
│   ├── sklearn_backend.py   # SklearnClassifierBackend
│   └── llm.py               # LLMZeroShotBackend
├── rewriting/
│   ├── __init__.py
│   ├── base.py              # RewriteStrategy protocol
│   ├── template.py          # TemplateRewriter (keyword backend)
│   ├── passthrough.py       # PassthroughRewriter (sklearn backend)
│   └── llm.py               # LLMRewriter (zero-shot backend)
├── discovery/
│   ├── __init__.py
│   └── registry_client.py   # Registry polling, domain cache
├── orchestration/
│   ├── __init__.py
│   └── fan_out.py           # Parallel recall dispatch
├── models/
│   ├── __init__.py
│   └── config.py            # RouterSettings (pydantic-settings)
└── domain_classifier.joblib  # (sklearn backend only, not in VCS)
```

**Key protocols:**

```python
from typing import Protocol

class ClassificationBackend(Protocol):
    async def classify(self, query: str, domains: list[DomainDescriptor]) -> list[DomainSignal]:
        """Classify a query into domain signals."""
        ...

class RewriteStrategy(Protocol):
    async def rewrite(
        self, query: str, target: DomainDescriptor, signals: list[DomainSignal]
    ) -> str | None:
        """Return a domain-optimized query rewrite, or None for passthrough."""
        ...
```

The backend and rewrite strategy are paired and injected at startup based on `ROUTER_MODEL`:

| `ROUTER_MODEL`       | `ClassificationBackend`    | `RewriteStrategy`     |
| -------------------- | -------------------------- | --------------------- |
| `keyword-heuristic`  | `KeywordHeuristicBackend`  | `TemplateRewriter`    |
| `sklearn-classifier` | `SklearnClassifierBackend` | `PassthroughRewriter` |
| `llm-zero-shot`      | `LLMZeroShotBackend`       | `LLMRewriter`         |
