# NornWeave — Response Fusion Pipeline

> Design specification for the six-stage fusion pipeline that reconciles multi-agent recall responses into a single, deduplicated, conflict-resolved result set. References the [Domain Model](DOMAIN-MODEL.md) for types and [Service Contracts](SERVICE-CONTRACTS.md) for the `POST /fuse` API.

---

## Table of Contents

- [Pipeline Overview](#pipeline-overview)
- [Stage 1: Collection](#stage-1-collection)
- [Stage 2: Normalization](#stage-2-normalization)
- [Stage 3: Deduplication](#stage-3-deduplication)
- [Stage 4: Conflict Resolution](#stage-4-conflict-resolution)
- [Stage 5: Ranking](#stage-5-ranking)
- [Stage 6: Synthesis](#stage-6-synthesis)
- [Worked Example: End-to-End](#worked-example-end-to-end)
- [Configuration](#configuration)
- [Internal Architecture](#internal-architecture)

---

## Pipeline Overview

```
RecallResponse[]                                          FusionResult
from N agents                                             to client
     │                                                         ▲
     ▼                                                         │
┌─────────┐   ┌─────────────┐   ┌───────────┐   ┌──────────┐ │ ┌───────────┐   ┌───────────┐
│ 1.      │──▶│ 2.          │──▶│ 3.        │──▶│ 4.       │─┼▶│ 5.        │──▶│ 6.        │
│COLLECT  │   │ NORMALIZE   │   │ DEDUPLICATE│  │ CONFLICT │ │ │ RANK      │   │ SYNTHESIZE│
│         │   │             │   │           │   │ RESOLVE  │ │ │           │   │ (optional)│
└─────────┘   └─────────────┘   └───────────┘   └──────────┘ │ └───────────┘   └───────────┘
                                                              │
                                                    conflicts[], coverage_gaps[]
```

Each stage is a pure function: it takes immutable input, produces immutable output, and logs its decisions. No stage mutates state from a previous stage.

| Stage            | Input                                 | Output                                 | May Reduce Item Count |
| ---------------- | ------------------------------------- | -------------------------------------- | --------------------- |
| 1. Collection    | Raw `RecallResponse[]` + timeout info | `CollectedItems` + `CoverageGap[]`     | No                    |
| 2. Normalization | `CollectedItems`                      | `NormalizedItems` (unified scores)     | No                    |
| 3. Deduplication | `NormalizedItems`                     | `DedupedItems` (unique items)          | **Yes**               |
| 4. Conflict Res. | `DedupedItems`                        | `ResolvedItems` + `ConflictRecord[]`   | **Yes** (if resolved) |
| 5. Ranking       | `ResolvedItems`                       | `RankedItems` (final order)            | No                    |
| 6. Synthesis     | `RankedItems` + original query        | `FusionResult` (with optional summary) | No                    |

---

## Stage 1: Collection

**Purpose:** Gather all `RecallResponse` messages from agents, accounting for timeouts and failures.

**Input:** The router forwards all received `RecallResponse` objects plus a list of agents that failed to respond.

**Logic:**

```python
def collect(
    responses: list[RecallResponse],
    coverage_gaps: list[CoverageGap],
) -> CollectedItems:
    all_items: list[TaggedItem] = []

    for response in responses:
        for item in response.items:
            all_items.append(TaggedItem(
                item=item,
                source_agent=response.agent_id,
                source_domain=response.domain_id,
                agent_latency_ms=response.latency_ms,
            ))

    return CollectedItems(
        items=all_items,
        coverage_gaps=coverage_gaps,
        agents_responded=[r.agent_id for r in responses],
        total_candidates=sum(r.total_searched for r in responses),
    )
```

**`TaggedItem` wrapper:**

| Field              | Type         | Description                         |
| ------------------ | ------------ | ----------------------------------- |
| `item`             | `RecallItem` | The original recall item            |
| `source_agent`     | `AgentId`    | Which agent produced this item      |
| `source_domain`    | `DomainId`   | Which domain it came from           |
| `agent_latency_ms` | `int`        | How long that agent took to respond |

**Behavior:**

- Items arrive pre-sorted within each agent's response (best-first), but the cross-agent ordering is undefined at this stage.
- Coverage gaps are passed through unchanged; they'll be attached to the final `FusionResult`.
- If zero agents responded, collection produces an empty item list. This is not an error; it produces a valid `FusionResult` with no items and non-empty `coverage_gaps`.

---

## Stage 2: Normalization

**Purpose:** Transform agent-local relevance scores into a globally comparable scale.

**Problem:** Agent A rates its best result 0.95; Agent B rates its best result 0.72. This doesn't mean A's result is better. The scores come from different models with different calibrations. Comparing them directly is like comparing Fahrenheit to Celsius.

**Strategy: Per-agent min-max normalization.**

```python
def normalize(collected: CollectedItems) -> NormalizedItems:
    # Group items by source agent
    by_agent: dict[AgentId, list[TaggedItem]] = group_by(collected.items, key=lambda t: t.source_agent)

    normalized: list[TaggedItem] = []
    for agent_id, agent_items in by_agent.items():
        scores = [t.item.score.value for t in agent_items]
        min_score = min(scores)
        max_score = max(scores)
        score_range = max_score - min_score

        for tagged in agent_items:
            if score_range == 0:
                # All items from this agent have the same score; normalize to 0.5
                norm_score = 0.5
            else:
                norm_score = (tagged.item.score.value - min_score) / score_range

            normalized.append(tagged.with_normalized_score(norm_score))

    return NormalizedItems(items=normalized)
```

**Edge cases:**

| Scenario                           | Behavior                                                |
| ---------------------------------- | ------------------------------------------------------- |
| Agent returns 1 item               | Score normalizes to `0.5` (no range to compare against) |
| Agent returns all identical scores | All normalize to `0.5`                                  |
| Agent returns items with 0.0 score | Min is 0.0; normalization proceeds normally             |

**Why min-max?** It's simple, deterministic, and preserves within-agent ranking. More sophisticated calibration (e.g., isotonic regression on held-out data) is a future enhancement, not an initial requirement.

---

## Stage 3: Deduplication

**Purpose:** Identify and merge items that convey the same information surfaced by different agents.

**Common scenario:** The code agent and the documentation agent both reference the same API endpoint. The code agent returns the function definition; the docs agent returns the API reference page describing the same function. These are semantically duplicate.

**Strategy: Fuzzy text similarity with `rapidfuzz`.**

```python
from rapidfuzz import fuzz

def deduplicate(items: NormalizedItems, threshold: float = 0.85) -> DedupedItems:
    unique: list[TaggedItem] = []
    merged_citations: dict[int, list[SourceCitation]] = {}

    for candidate in items.items:
        merged = False
        for i, existing in enumerate(unique):
            similarity = fuzz.token_sort_ratio(
                candidate.item.content, existing.item.content
            ) / 100.0

            if similarity >= threshold:
                # Merge: keep the higher-scoring version
                if candidate.normalized_score > existing.normalized_score:
                    merged_citations.setdefault(i, [existing.item.citation])
                    merged_citations[i].append(candidate.item.citation)
                    unique[i] = candidate
                else:
                    merged_citations.setdefault(i, []).append(candidate.item.citation)
                merged = True
                break

        if not merged:
            unique.append(candidate)

    return DedupedItems(
        items=unique,
        duplicates_removed=len(items.items) - len(unique),
        merged_citations=merged_citations,
    )
```

**Similarity threshold: `0.85` (configurable via `DEDUP_SIMILARITY_THRESHOLD`).**

| Threshold | Effect                                                   |
| --------- | -------------------------------------------------------- |
| `0.95`    | Very conservative; only near-exact duplicates are merged |
| `0.85`    | Default; catches paraphrased duplicates across domains   |
| `0.70`    | Aggressive; risk of merging related-but-distinct items   |

**Citation enrichment:** When items merge, the winner's `citation` is kept as primary, and the loser's citation is stored as an additional provenance source. The consumer can see that this information was corroborated across domains.

**Performance note:** Deduplication is O(n²) in the candidate count. With default `top_k=20` across 4 agents, n ≤ 80, which completes in < 10 ms. If n ever exceeds 200, switch to locality-sensitive hashing (MinHash) for the candidate-pair selection step.

---

## Stage 4: Conflict Resolution

**Purpose:** Detect and resolve contradictions between items from different domains.

**What is a conflict?** Two items contradict each other when they make incompatible claims about the same entity. The fusion layer uses a heuristic detector followed by a strategy-based resolver.

### Conflict Detection

```python
def detect_conflicts(items: DedupedItems) -> list[ConflictGroup]:
    conflicts: list[ConflictGroup] = []

    for i, a in enumerate(items.items):
        for j, b in enumerate(items.items):
            if i >= j:
                continue
            if a.source_domain == b.source_domain:
                continue  # Intra-domain conflicts are the agent's problem

            if is_conflicting(a.item, b.item):
                conflicts.append(ConflictGroup(items=[a, b]))

    return merge_overlapping_groups(conflicts)
```

**`is_conflicting` heuristics:**

| Heuristic                  | Detection Logic                                                                    | Example                                                    |
| -------------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| **Same-entity divergence** | Items reference the same file/function but with different content                  | Code shows `v2.1`; docs say `v2.0`                         |
| **Temporal contradiction** | Items describe the same event with conflicting dates or sequences                  | Convo says "shipped Monday"; docs say "deployed Wednesday" |
| **Negation pattern**       | One item asserts X; another asserts "not X" or "no longer X"                       | Docs: "supports OAuth"; code: `# OAuth removed in v3`      |
| **Semantic opposition**    | Embedding cosine similarity between items is < 0.3 despite both matching the query | Indicates they're relevant but say different things        |

The same-entity check uses the `SourceCitation.source_path` field: if two items share the same base filename or the same `function_name` in metadata, they're considered to reference the same entity.

### Conflict Resolution Strategies

The resolution strategy is set per-query via the `conflict_strategy` field in the fuse request. The default is `RECENCY`.

#### `RECENCY`

Keep the item with the most recent `SourceCitation.timestamp`.

```
Item A (code):  timestamp 2026-01-20  →  WINNER
Item B (docs):  timestamp 2026-01-10  →  dropped
```

**Rationale:** More recent information is more likely to reflect the current state of the system. Code that was committed yesterday is more trustworthy than documentation written last month.

#### `SOURCE_AUTHORITY`

Apply the domain authority hierarchy from the README:

```
Code > Documentation > Conversations > Research
```

| Query Type              | Authority Order (highest first) |
| ----------------------- | ------------------------------- |
| Current system behavior | Code → Docs → Convo → Research  |
| Intended design         | Docs → Code → Convo → Research  |
| Historical decisions    | Convo → Docs → Code → Research  |

The query type is inferred from signals:

- Contains "how does it work" / "what does it do" → current behavior
- Contains "why" / "design" / "intended" → intended design
- Contains "decided" / "agreed" / "discussed" → historical decisions

Default (if query type is ambiguous): `Code → Docs → Convo → Research`.

#### `CONFIDENCE`

Keep the item with the higher normalized score.

```
Item A (code):  normalized_score 0.88  →  WINNER
Item B (docs):  normalized_score 0.71  →  dropped
```

Simple, but only useful when normalization has been effective.

#### `FLAG`

Do not resolve. Keep both items and add a `ConflictRecord` to the response with `resolved_to = None`.

```json
{
  "items": [
    { "chunk_id": "a...", "content": "Returns 200 OK", "score": 0.88 },
    { "chunk_id": "b...", "content": "Returns 201 Created", "score": 0.71 }
  ],
  "resolution": "FLAG",
  "resolved_to": null
}
```

The consumer decides. This is the safest strategy for high-stakes queries.

#### `RECENCY_THEN_FLAG`

Try `RECENCY` first. If the timestamps are within 24 hours of each other (configurable via `RECENCY_TIE_WINDOW_HOURS`), fall back to `FLAG`.

```
Item A: timestamp 2026-01-20T10:00  ┐
                                     ├── within 24h → FLAG
Item B: timestamp 2026-01-20T14:00  ┘
```

### Resolution Output

Each conflict, whether resolved or flagged, produces a `ConflictRecord`:

```python
ConflictRecord(
    items=[item_a.item, item_b.item],
    resolution=ConflictStrategy.RECENCY,
    resolved_to=item_a.item,  # or None if FLAG
)
```

Resolved conflicts remove the loser from the item list. Flagged conflicts keep both.

---

## Stage 5: Ranking

**Purpose:** Produce the final ordering of items for presentation to the consumer.

**Input:** Deduplicated, conflict-resolved items from diverse domains with normalized scores.

**Strategy: Weighted multi-signal ranking.**

```python
def rank(items: list[TaggedItem], query_text: str) -> list[TaggedItem]:
    scored = []
    for item in items:
        final = compute_rank_score(item, query_text)
        scored.append((final, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]
```

### Ranking Signals

| Signal                     | Weight | Source                  | Range      | Description                                                   |
| -------------------------- | ------ | ----------------------- | ---------- | ------------------------------------------------------------- |
| Normalized score           | 0.50   | Stage 2                 | 0.0–1.0    | Agent-assessed relevance (normalized)                         |
| Cross-domain corroboration | 0.15   | Stage 3 (dedup)         | 0.0 or 1.0 | 1.0 if item was corroborated across domains                   |
| Source recency             | 0.15   | `citation.timestamp`    | 0.0–1.0    | Exponential decay: `exp(-days / 90)`                          |
| Domain relevance           | 0.10   | Router's `DomainSignal` | 0.0–1.0    | How strongly the router associated this domain with the query |
| Content length penalty     | 0.10   | `item.content`          | 0.0–1.0    | Slight preference for substantive chunks over short fragments |

```
rank_score = (normalized_score × 0.50)
           + (corroboration × 0.15)
           + (recency × 0.15)
           + (domain_relevance × 0.10)
           + (length_signal × 0.10)
```

**Content length signal:**

```python
def length_signal(content: str) -> float:
    tokens = len(content.split())
    if tokens < 10:
        return 0.2    # Very short; probably not useful alone
    elif tokens > 500:
        return 0.7    # Long but might be noise
    else:
        return 1.0    # Sweet spot
```

**Tie-breaking:** If two items have the same rank score (within `1e-6`), break ties by:

1. Higher original (pre-normalization) score
2. More recent `citation.timestamp`
3. Alphabetical `source_domain` (deterministic fallback)

---

## Stage 6: Synthesis

**Purpose:** Optionally generate a natural language summary that weaves the top results into a coherent narrative answer.

**Triggered by:** `synthesize=true` in the fuse request (forwarded from the client's `POST /query`).

**If disabled:** Skip this stage. The `FusionResult.synthesis` field is `null`.

### Synthesis Prompt

```
You are a knowledge synthesis assistant. Given the following ranked results from
a multi-domain knowledge search, produce a concise, accurate answer to the
original query.

Original query: "{query_text}"

Results (ranked by relevance):
{formatted_results}

Instructions:
- Cite sources using [domain:chunk_id] format.
- If results conflict, acknowledge the disagreement and state which source
  is likely more authoritative.
- If coverage gaps exist, mention what information might be missing.
- Keep the answer under 500 words.
- Do not invent information not present in the results.
```

`{formatted_results}` is built from the top 10 ranked items:

```
[1] (code, score: 0.92) src/payments/handlers.py:42-67
    def handle_payment_error(error: PaymentError) -> Response: ...

[2] (convo, score: 0.85) #engineering, 2026-01-16
    charlie: I pushed a fix in PR #247 for the null pointer in payments...

[3] (docs, score: 0.78) docs/api/payments.md § Error Handling
    The payment module returns HTTP 422 for validation errors and ...
```

### Synthesis Configuration

| Variable                | Default           | Description                                 |
| ----------------------- | ----------------- | ------------------------------------------- |
| `SYNTHESIS_MODEL`       | `gpt-4o-mini`     | LLM model for synthesis via `litellm`       |
| `SYNTHESIS_TEMPERATURE` | `0.3`             | Low temperature for factual accuracy        |
| `SYNTHESIS_MAX_TOKENS`  | `1024`            | Maximum synthesis output length             |
| `SYNTHESIS_TIMEOUT_MS`  | `5000`            | Timeout for synthesis LLM call              |
| `SYNTHESIS_TOP_K`       | `10`              | Number of ranked items to include in prompt |
| `SYNTHESIS_FALLBACK`    | `ollama/llama3.2` | Fallback model if primary is unavailable    |

### Graceful Degradation

If the synthesis model times out or errors:

1. Log the failure at `WARNING` level.
2. Set `FusionResult.synthesis = null`.
3. Return the result with all ranked items intact.

The consumer still gets the full ranked result set; they just don't get the narrative wrapper. This is a soft failure, not a hard error.

---

## Worked Example: End-to-End

A complete trace through all six stages for a realistic query.

### Setup

**Query:** `"what's the error handling behavior in the payment module"`

**Three agents respond:**

**Code agent** (`code-memory`, latency: 280ms):

| #   | chunk_id | content                                                                                                    | score | source_path                 | timestamp  |
| --- | -------- | ---------------------------------------------------------------------------------------------------------- | ----- | --------------------------- | ---------- |
| 1   | `c-001`  | `def handle_payment_error(e: PaymentError) → Response: return JSONResponse(status_code=422, ...)`          | 0.91  | `src/payments/handlers.py`  | 2026-01-20 |
| 2   | `c-002`  | `class PaymentValidator: def validate(self, req): if not req.amount: raise PaymentError("missing amount")` | 0.84  | `src/payments/validator.py` | 2026-01-18 |
| 3   | `c-003`  | `# Payment retry logic with exponential backoff`                                                           | 0.65  | `src/payments/retry.py`     | 2026-01-10 |

**Docs agent** (`docs-memory`, latency: 190ms):

| #   | chunk_id | content                                                                                                                | score | source_path            | timestamp  |
| --- | -------- | ---------------------------------------------------------------------------------------------------------------------- | ----- | ---------------------- | ---------- |
| 1   | `d-001`  | `## Error Handling — The payment module returns HTTP 400 for malformed requests and HTTP 500 for downstream failures.` | 0.88  | `docs/api/payments.md` | 2025-12-01 |
| 2   | `d-002`  | `## Payment Module Overview — Handles all payment processing including validation, authorization, and settlement.`     | 0.72  | `docs/api/payments.md` | 2025-12-01 |

**Convo agent** (`convo-memory`): **TIMED OUT** (5000ms deadline exceeded).

---

### Stage 1 — Collection

```
Input:  2 RecallResponses + 1 CoverageGap

Output:
  TaggedItems: [
    (c-001, code, score=0.91),
    (c-002, code, score=0.84),
    (c-003, code, score=0.65),
    (d-001, docs, score=0.88),
    (d-002, docs, score=0.72),
  ]
  CoverageGaps: [
    {domain: "conversations", agent: "convo-memory", reason: "timeout after 5000ms"}
  ]
  Agents responded: ["code-memory", "docs-memory"]
  Total candidates searched: 2,370
```

---

### Stage 2 — Normalization

Per-agent min-max normalization:

**Code agent** (min=0.65, max=0.91, range=0.26):

| Item  | Original | Normalized                    |
| ----- | -------- | ----------------------------- |
| c-001 | 0.91     | `(0.91 - 0.65) / 0.26 = 1.00` |
| c-002 | 0.84     | `(0.84 - 0.65) / 0.26 = 0.73` |
| c-003 | 0.65     | `(0.65 - 0.65) / 0.26 = 0.00` |

**Docs agent** (min=0.72, max=0.88, range=0.16):

| Item  | Original | Normalized                    |
| ----- | -------- | ----------------------------- |
| d-001 | 0.88     | `(0.88 - 0.72) / 0.16 = 1.00` |
| d-002 | 0.72     | `(0.72 - 0.72) / 0.16 = 0.00` |

Now `c-001` and `d-001` are on the same footing: both are the best result from their respective agents.

---

### Stage 3 — Deduplication

Compare all pairs using `fuzz.token_sort_ratio`:

| Pair          | Similarity | Action                                                                                                          |
| ------------- | ---------- | --------------------------------------------------------------------------------------------------------------- |
| c-001 ↔ d-001 | **0.41**   | Both discuss payment error handling, but c-001 is code and d-001 is prose. Below 0.85 threshold. **Keep both.** |
| c-001 ↔ d-002 | 0.22       | No match.                                                                                                       |
| c-002 ↔ d-001 | 0.28       | No match.                                                                                                       |
| c-002 ↔ d-002 | 0.31       | No match.                                                                                                       |
| c-003 ↔ d-001 | 0.18       | No match.                                                                                                       |
| c-003 ↔ d-002 | 0.15       | No match.                                                                                                       |

**Result:** No duplicates removed. All 5 items pass through.

_(In a scenario where the docs agent returned the exact same function signature as the code agent, the similarity would be > 0.85 and they'd merge.)_

---

### Stage 4 — Conflict Resolution

**Conflict detection:** c-001 and d-001 both reference payment error handling but describe different HTTP status codes.

- `c-001` (code): Returns `422` for payment errors.
- `d-001` (docs): Says the module returns `400` for malformed requests and `500` for downstream failures.

These reference the same entity (`payments/handlers.py` error handling) with divergent status codes. **Conflict detected.**

**Resolution (strategy: `RECENCY`):**

```
c-001 timestamp: 2026-01-20  →  WINNER (more recent)
d-001 timestamp: 2025-12-01  →  kept, but conflict recorded
```

Since the code was updated 50 days after the docs were written, the code is the authoritative source for current behavior. The docs are stale.

**Output:**

```
ConflictRecord:
  items: [c-001, d-001]
  resolution: RECENCY
  resolved_to: c-001

Items after resolution: [c-001, c-002, c-003, d-001 (demoted), d-002]
d-001 is retained in the result set but its normalized score is penalized by 0.3.
```

---

### Stage 5 — Ranking

Multi-signal ranking for each item:

| Item  | Norm (×0.50)        | Corrob. (×0.15)    | Recency (×0.15)     | Domain Rel. (×0.10) | Length (×0.10)     | **Final** |
| ----- | ------------------- | ------------------ | ------------------- | ------------------- | ------------------ | --------- |
| c-001 | 1.00 × 0.50 = 0.500 | 0.0 × 0.15 = 0.000 | 0.97 × 0.15 = 0.146 | 0.85 × 0.10 = 0.085 | 1.0 × 0.10 = 0.100 | **0.831** |
| c-002 | 0.73 × 0.50 = 0.365 | 0.0 × 0.15 = 0.000 | 0.95 × 0.15 = 0.143 | 0.85 × 0.10 = 0.085 | 1.0 × 0.10 = 0.100 | **0.693** |
| d-001 | 0.70 × 0.50 = 0.350 | 0.0 × 0.15 = 0.000 | 0.51 × 0.15 = 0.077 | 0.55 × 0.10 = 0.055 | 1.0 × 0.10 = 0.100 | **0.582** |
| d-002 | 0.00 × 0.50 = 0.000 | 0.0 × 0.15 = 0.000 | 0.51 × 0.15 = 0.077 | 0.55 × 0.10 = 0.055 | 1.0 × 0.10 = 0.100 | **0.232** |
| c-003 | 0.00 × 0.50 = 0.000 | 0.0 × 0.15 = 0.000 | 0.85 × 0.15 = 0.128 | 0.85 × 0.10 = 0.085 | 0.7 × 0.10 = 0.070 | **0.283** |

_(d-001's normalized score reduced from 1.00 to 0.70 due to conflict demotion.)_

**Final ranked order:**

```
1. c-001  (0.831)  — handle_payment_error function definition
2. c-002  (0.693)  — PaymentValidator class
3. d-001  (0.582)  — Error Handling docs (conflict-demoted)
4. c-003  (0.283)  — Payment retry logic
5. d-002  (0.232)  — Payment Module Overview
```

---

### Stage 6 — Synthesis

**Prompt sent to LLM** (with top items formatted):

```
Original query: "what's the error handling behavior in the payment module"

Results (ranked by relevance):
[1] (code, 0.831) src/payments/handlers.py:42-67
    def handle_payment_error(e: PaymentError) → Response: return JSONResponse(status_code=422, ...)

[2] (code, 0.693) src/payments/validator.py
    class PaymentValidator: def validate(self, req): if not req.amount: raise PaymentError(...)

[3] (docs, 0.582) docs/api/payments.md § Error Handling  ⚠️ CONFLICT: disagrees with [1] on status codes
    The payment module returns HTTP 400 for malformed requests and HTTP 500 for downstream failures.

Coverage gaps: conversations domain timed out.
```

**Synthesis output:**

> The payment module's error handling centers on the `handle_payment_error` function in `src/payments/handlers.py` [code:c-001], which returns HTTP 422 with a JSON error body for payment validation failures. Input validation is handled by the `PaymentValidator` class [code:c-002], which raises `PaymentError` for missing or invalid fields.
>
> **Note:** The API documentation [docs:d-001] describes different status codes (400 and 500) for error cases, but the code was updated more recently (Jan 20 vs Dec 1) and is likely the current ground truth. The documentation may need updating.
>
> The conversation history was unavailable for this query (timeout), so discussions about recent error handling changes could not be included.

---

### Final `FusionResult`

```json
{
  "query_id": "d4e5f6a7-...",
  "items": [
    {"chunk_id": "c-001", "content": "def handle_payment_error...", "score": {"value": 0.831}, "citation": {"..."}},
    {"chunk_id": "c-002", "content": "class PaymentValidator...", "score": {"value": 0.693}, "citation": {"..."}},
    {"chunk_id": "d-001", "content": "## Error Handling...", "score": {"value": 0.582}, "citation": {"..."}},
    {"chunk_id": "c-003", "content": "# Payment retry...", "score": {"value": 0.283}, "citation": {"..."}},
    {"chunk_id": "d-002", "content": "## Payment Module...", "score": {"value": 0.232}, "citation": {"..."}}
  ],
  "synthesis": "The payment module's error handling centers on...",
  "conflicts": [
    {
      "items": ["c-001", "d-001"],
      "resolution": "RECENCY",
      "resolved_to": "c-001"
    }
  ],
  "coverage_gaps": [
    {"domain_id": "conversations", "agent_id": "convo-memory", "reason": "timeout after 5000ms"}
  ],
  "domains_queried": ["code", "documentation"],
  "total_latency_ms": 4200,
  "trace_id": "7da93f4688c45eb7b4df030a1f1f5847"
}
```

---

## Configuration

| Variable                     | Type    | Default           | Description                                      |
| ---------------------------- | ------- | ----------------- | ------------------------------------------------ |
| `FUSION_PORT`                | `int`   | `8082`            | HTTP listen port                                 |
| `DEDUP_SIMILARITY_THRESHOLD` | `float` | `0.85`            | rapidfuzz similarity threshold for deduplication |
| `CONFLICT_DEMOTION_PENALTY`  | `float` | `0.30`            | Score penalty applied to conflict losers         |
| `RECENCY_TIE_WINDOW_HOURS`   | `int`   | `24`              | Window for RECENCY_THEN_FLAG tie detection       |
| `RANK_WEIGHT_SCORE`          | `float` | `0.50`            | Ranking weight: normalized relevance score       |
| `RANK_WEIGHT_CORROBORATION`  | `float` | `0.15`            | Ranking weight: cross-domain corroboration       |
| `RANK_WEIGHT_RECENCY`        | `float` | `0.15`            | Ranking weight: source recency                   |
| `RANK_WEIGHT_DOMAIN`         | `float` | `0.10`            | Ranking weight: domain relevance from router     |
| `RANK_WEIGHT_LENGTH`         | `float` | `0.10`            | Ranking weight: content length signal            |
| `SYNTHESIS_MODEL`            | `str`   | `gpt-4o-mini`     | LLM for narrative synthesis                      |
| `SYNTHESIS_TEMPERATURE`      | `float` | `0.3`             | LLM temperature                                  |
| `SYNTHESIS_MAX_TOKENS`       | `int`   | `1024`            | LLM max output tokens                            |
| `SYNTHESIS_TIMEOUT_MS`       | `int`   | `5000`            | Synthesis deadline                               |
| `SYNTHESIS_TOP_K`            | `int`   | `10`              | Items included in synthesis prompt               |
| `SYNTHESIS_FALLBACK`         | `str`   | `ollama/llama3.2` | Fallback LLM model                               |

---

## Internal Architecture

```
services/fusion/src/nornweave_fusion/
├── __init__.py
├── main.py                  # FastAPI app, lifespan hooks
├── api/
│   ├── __init__.py
│   └── routes.py            # POST /fuse, GET /health, GET /ready
├── pipeline/
│   ├── __init__.py
│   ├── orchestrator.py      # Runs stages 1–6 in sequence
│   ├── collection.py        # Stage 1
│   ├── normalization.py     # Stage 2
│   ├── deduplication.py     # Stage 3
│   ├── conflict.py          # Stage 4 (detect + resolve)
│   ├── ranking.py           # Stage 5
│   └── synthesis.py         # Stage 6
├── models/
│   ├── __init__.py
│   ├── config.py            # FusionSettings (pydantic-settings)
│   └── internal.py          # TaggedItem, CollectedItems, NormalizedItems, etc.
└── llm/
    ├── __init__.py
    └── client.py            # litellm wrapper for synthesis
```

Each stage module exports a single function with a clear input → output signature. The orchestrator calls them in sequence:

```python
async def fuse(request: FuseRequest) -> FusionResult:
    collected   = collect(request.responses, request.coverage_gaps)
    normalized  = normalize(collected)
    deduped     = deduplicate(normalized)
    resolved    = resolve_conflicts(deduped, request.conflict_strategy)
    ranked      = rank(resolved, request.original_text)
    result      = await synthesize(ranked, request) if request.synthesize else finalize(ranked)
    return result
```
