# WealthPilot — Advanced & Agentic RAG Roadmap

_Options to evolve WealthPilot's retrieval intelligence beyond the current MVP.
Version 1.0 · 2026-07-11 · Audience: management / engineering._

---

## 1. Purpose

The MVP already answers grounded, cited, guarded questions. This roadmap lays out
**research-backed techniques (2026)** to raise answer quality, faithfulness, and reasoning
depth — mapped to **specific gaps we observed**, prioritised by value vs. cost, and framed
so we adopt them **selectively** rather than all at once.

**Guiding principle:** agentic depth buys accuracy at a real cost — industry benchmarks put
it at **3–10× token spend and 2–5× latency**. Because our LLM (deepseek-r1-70b) is a slow
reasoning model, we apply an **adaptive** strategy: cheap single-pass for simple lookups,
deeper agentic loops only for complex or high-risk queries.

---

## 2. Current baseline (already implemented)

WealthPilot already includes what the research calls "the cheapest upgrades that win most":

- **Hybrid retrieval** — dense vectors (pgvector/mxbai) + keyword (BM25-style full-text),
  fused with **Reciprocal Rank Fusion**.
- **Cross-encoder reranking** — `bge-reranker-v2-m3` second-pass precision.
- **Confidence gate** — abstains when retrieval is too weak (anti-fabrication).
- **Forced-tool-choice router** — an agentic routing decision (quote / index / portfolio /
  rebalance / knowledge).
- **Deterministic guardrails** — no-directive, citations, disclaimers.
- **Entity-tagged chunks** — company/section prepended for numerical fidelity.

So we are already at "advanced RAG". The next gains are **corrective / self-reflective loops**
and **agentic decomposition**.

---

## 3. Observed gaps this roadmap targets

| # | Gap seen in the MVP | Impact |
|---|---|---|
| G1 | deepseek dropped inline `[S#]` citations on some answers | Weaker traceability |
| G2 | Pure vector confused "IT sector" with the ITC ticker (keyword rescued it) | Precision on ambiguous terms |
| G3 | No multi-turn coreference ("what about *its* P/E?") | Follow-up questions fail |
| G4 | Comparison / multi-entity queries ("compare TCS vs Infosys") retrieve poorly | Can't do multi-hop |
| G5 | No answer-level faithfulness check beyond the retrieval gate | Residual hallucination risk |
| G6 | Financial vocabulary mismatch (user words ≠ document words) | Recall gaps |
| G7 | No "connect-the-dots" relationship queries (peers, sector rollups) | Limited analytical depth |

---

## 4. Technique catalogue (by tier)

### Tier 1 — high value, low latency (recommended first)

**T1.1 Self-RAG (answer-level critique)** — *fixes G1, G5.*
After drafting, a critique pass verifies each claim is supported by a retrieved source;
unsupported claims are dropped or flagged, and citations are enforced. This is the single
highest-value addition for a finance assistant (faithfulness is paramount).

**T1.2 Self-query / metadata extraction** — *fixes G2.*
An LLM pre-step extracts structured filters from the query (ticker → `entity`, "sector" →
`doc_type=market`, "fund" → `doc_type=fund`) and applies them to retrieval, sharply improving
precision on named entities.

**T1.3 Query rewriting + coreference resolution** — *fixes G3.*
Rewrite the current turn using conversation history into a standalone query
("what about its P/E?" → "what is TCS's P/E?") before retrieval.

**T1.4 Query decomposition** — *fixes G4.*
Break multi-entity/multi-hop questions into sub-queries, retrieve each independently, then
synthesise ("compare TCS and Infosys" → retrieve each company's metrics → combine).

**T1.5 CRAG-style grading + fallback** — *upgrades the gate.*
Grade retrieved chunks as relevant / ambiguous / irrelevant; on weak retrieval, rewrite or
re-retrieve **before** abstaining — a softer, smarter version of the current binary gate.

### Tier 2 — medium cost, strong gains

**T2.1 Contextual Retrieval** (Anthropic; reported −67% retrieval failures) — *fixes G6, numerical fidelity.*
Prepend a short LLM-generated context sentence to each chunk **before embedding** (a re-ingest
step). Extends the entity-tagging we already do.

**T2.2 HyDE (Hypothetical Document Embeddings)** — *fixes G6.*
Generate a hypothetical answer, embed *that* for retrieval — bridges the gap between how users
ask and how documents are written.

**T2.3 Plan-and-execute (agentic)** — *enables multi-step.*
A planner drafts steps for compound requests ("how does my portfolio compare to the Nifty this
year?") → gather portfolio + index + sector context → combine.

**T2.4 ReAct loop** — *tool + knowledge together.*
Iterative reason → retrieve/tool → reason until grounded, replacing one-shot routing where a
query needs both a tool result and corpus knowledge.

### Tier 3 — higher cost, specialised

**T3.1 GraphRAG** — *fixes G7.*
Build a knowledge graph over the corpus (company → sector → index, peers). Research is explicit:
GraphRAG **only earns its cost on cross-document relationship questions** ("which Nifty banks
have the lowest P/E and rising promoter holding") — not simple lookups.

**T3.2 Multi-agent retrieval** — specialised company / market / education retrievers under an
orchestrator (our `portfolio_summary` is already a mini-agent to generalise).

**T3.3 Self-correcting RAG (NLI / MCTS)** — maximum faithfulness (2026 research); heavy, adopt
only if evaluation shows residual hallucination after Tier 1.

---

## 5. Target architecture — Adaptive Agentic RAG

Rather than make every query agentic (too slow with deepseek), add a **complexity router** at
the front and scale depth to the question:

```
query
  │
  ├─ query rewrite + coreference (T1.3) + self-query filters (T1.2)
  │
  ▼ complexity router
  ├─ SIMPLE (price, single fact, definition)     → current single-pass RAG/tool      [fast]
  ├─ COMPARISON / MULTI-HOP                       → decompose (T1.4) → parallel        [medium]
  │                                                 retrieve → synthesise
  └─ COMPLEX / PORTFOLIO / RISKY                  → plan-and-execute (T2.3) +          [deep]
                                                    CRAG grading (T1.5) +
                                                    Self-RAG critique (T1.1)
  │
  ▼ (all paths) output guardrail → cited answer + trace
```

This keeps latency low where possible and spends the agentic budget only where it changes the
answer — directly managing the cost/latency trade-off the research warns about.

---

## 6. Recommended sequence

1. **T1.1 Self-RAG critique** — biggest quality win; fixes the citation/grounding gap we saw.
2. **T1.2 + T1.3 self-query filters + coreference** — precision + multi-turn follow-ups.
3. **T1.4 query decomposition** — unlocks comparison queries.
4. **T2.1 Contextual Retrieval re-ingest** — durable retrieval boost.
5. **Adaptive complexity router** — ties Tier 1 together; escalate depth only when needed.
6. Then **HyDE / plan-execute / GraphRAG** as the evaluation harness justifies each.

Each step should be gated by the **eval harness** (golden Q&A): adopt a technique only if it
measurably improves faithfulness / retrieval relevance without unacceptable latency.

---

## 7. Expected impact & success metrics

| Metric | Baseline | Target after Tier 1–2 |
|---|---|---|
| Citation coverage (claims traced to a source) | partial | ~100% (Self-RAG) |
| Retrieval relevance on ambiguous/entity queries | good, some misses | improved (self-query, contextual) |
| Multi-turn follow-up success | not supported | supported (coreference) |
| Comparison/multi-hop questions | weak | supported (decomposition) |
| Hallucinated figures | low (gate) | ~zero (Self-RAG + CRAG) |
| Latency (simple queries) | fast | unchanged (adaptive router) |

---

## 8. Risks & trade-offs

- **Latency/cost:** agentic loops multiply deepseek's already-high latency — mitigated by the
  adaptive router (deep paths only for complex queries) and by caching.
- **Over-engineering:** GraphRAG / multi-agent add real complexity; adopt only when relationship
  queries are a proven need.
- **Reasoning-model quirks:** deepseek needs forced tool choice and generous token budgets;
  agentic steps amplify this — consider routing the lightweight critique/rewrite steps to a
  faster model (Groq/llama3.3) via our provider switch.
- **Evaluation dependency:** every upgrade must be validated against the golden set to avoid
  regressions — the eval harness is a prerequisite for Tier 2+.

---

## 9. Sources

- 12 Advanced RAG Techniques (2026) — atlan.com/know/advanced-rag-techniques
- Build RAG Systems in 2026: 8 Architecture Patterns — aithinkerlab.com
- Agentic RAG: Five Production Retrieval Patterns — brightter.com
- Agentic Retrieval-Augmented Generation: A Survey — arXiv:2501.09136
- Self-Correcting RAG (MMKP / NLI-guided MCTS) — arXiv:2604.10734
- Contextual Retrieval (chunk-context embedding) — Anthropic
```
```
