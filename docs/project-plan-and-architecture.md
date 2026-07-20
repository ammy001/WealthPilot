# WealthPilot — Complete Project Plan & Architecture
### Educational Conversational Finance Assistant for Indian Markets (NIFTY 100)

**Document type:** Master project & architecture document (management review)
**Version:** 1.0 · **Date:** 2026-07-10 · **Audience:** Management / stakeholders
**Related deep-dives:** `docs/project-overview.md` (data report), `docs/data-architecture.md` (query flow)

---

## Table of contents
1. Executive summary
2. Background & problem statement
3. Project purpose & objectives
4. Scope
5. Stakeholders & user persona
6. Solution overview (capabilities)
7. System architecture
8. Component design (detailed)
9. Data architecture & governance
10. Agentic design & orchestration
11. Guardrails, safety & compliance
12. Conversation flows (sample Q&A)
13. Technology stack & infrastructure
14. Delivery plan & roadmap (phased)
15. Team roles & responsibilities
16. Evaluation & quality strategy
17. Risks & mitigations
18. Assumptions & dependencies
19. Current status
20. Future enhancements
21. Appendices (code structure, glossary, sources)

---

## 1. Executive summary

WealthPilot is an **educational, conversational finance assistant** for the Indian equity
market. Users ask questions in plain language ("what's a good low-cost index fund for a
moderate-risk investor?", "how is my portfolio doing?", "what's the price of Reliance?")
and receive **grounded, cited, and personalised** answers.

The distinguishing principle is **trust by design**:
- **No hallucination** — every number is traceable to a source document or a live tool.
- **No directive advice** — the assistant educates and contextualises; it never says
  "buy/sell/invest now."
- **Personalised** — it remembers each user's risk profile and stock portfolio across sessions.
- **Explainable** — every response logs the documents and tools that produced it.

The system is built on three pillars: **Retrieval-Augmented Generation (RAG)** over a curated
financial corpus, **live tools** for real-time data and calculations, and **cross-session
memory**. An LLM agent orchestrates these, wrapped in deterministic safety guardrails.

**Current state:** the complete data foundation (100 company profiles, fund documents, market
data, educational content, synthetic users) is built and quality-checked. The retrieval,
agent, UI, and evaluation layers are designed and scheduled in the delivery plan below.

---

## 2. Background & problem statement

Retail investors are underserved by two extremes:
- **Generic robo-advisers** that issue opaque, one-size-fits-all recommendations with no
  explanation and no memory of the individual.
- **Raw information sources** (news, screeners) that overwhelm rather than educate.

Large Language Models can converse naturally but, used naively, they **hallucinate numbers**
and **drift into unlicensed advice** — unacceptable in finance, where accuracy and compliance
are paramount. Industry research is consistent: financial AI must use RAG for grounding, must
enforce guardrails at multiple layers, and must provide provenance and numerical fidelity.

WealthPilot addresses this by grounding every answer in verifiable sources, wrapping the LLM
in hard guardrails, and adding memory for genuine personalisation — delivering an assistant
that **teaches** rather than **tells**.

---

## 3. Project purpose & objectives

**Purpose:** empower retail investors to *understand* their investments through a transparent,
personalised, and safe conversational assistant.

**Objectives (measurable):**
| # | Objective | Success measure |
|---|---|---|
| O1 | Grounded answers | 100% of quantitative claims cite a source or tool output |
| O2 | No directive advice | 0 buy/sell/invest-now directives pass the output guardrail |
| O3 | Personalisation | Risk profile stated in session 1 recalled unprompted in session 2 |
| O4 | Accuracy | Golden-set evaluation score improves measurably after error analysis |
| O5 | Explainability | Every response reconstructable from a single trace ID |
| O6 | Responsiveness | Repeated quote lookups served from cache with visible speed-up |

---

## 4. Scope

**In scope**
- Universe: **NIFTY 100** stocks (India's 100 largest listed companies).
- Asset focus: **individual equities** (user portfolios hold stocks).
- Education focus: **index funds** and core investing concepts.
- Capabilities: RAG Q&A, live stock/index quotes, portfolio rebalance math, portfolio
  summarisation, cross-session memory, guardrails, observability, evaluation.
- Market: India (INR); free/public delayed data sources.

**Out of scope**
- Mutual funds beyond index-fund education (no debt/gold/ELSS advice).
- Live order placement, trading, or brokerage integration.
- Directive advice, price predictions, buy/sell signals.
- Technical-analysis signals (RSI/MACD), sentiment scoring, derivatives/options.
- Collection of sensitive PII (PAN, bank/demat numbers, passwords).

**Guiding constraints:** descriptive not directive; never fabricate figures; delayed
educational-use data only.

---

## 5. Stakeholders & user persona

**Reference persona — "Marcus Chen"** (34, IT professional, moderate risk tolerance): wants
transparent explanations tailored to his risk profile, with the assistant remembering his
preferences and holdings across conversations. He is curious and wants to learn — not to be
handed a "buy this now" instruction.

Broader users: first-time and intermediate retail investors seeking to understand funds,
risk, diversification, and their own portfolios.

---

## 6. Solution overview (capabilities)

1. **Ask about companies** — descriptive profiles of any NIFTY 100 company (business, financials).
2. **Learn concepts** — index funds, expense ratios, risk, diversification, asset allocation.
3. **Check live data** — current stock prices, index/sector levels (delayed).
4. **Understand their portfolio** — value, profit/loss, sector mix, benchmark vs Nifty 100.
5. **Explore "what-ifs"** — rebalance math ("move ₹5,000 from bonds to equities").
6. **Get context on risk** — how a query relates to their stated risk tolerance.
7. **Be protected** — refusal of directive/risky requests with educational framing instead.

---

## 7. System architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          GRADIO CHAT UI                                    │
│   chat · expandable "agent trace" panel · guardrail & cache-hit badges     │
└───────────────────────────────┬────────────────────────────────────────────┘
                                │  user turn + user_id + trace_id
                     ┌──────────▼───────────┐
                     │   INPUT GUARDRAIL      │  (deterministic) intent / risk classification
                     └──────────┬───────────┘
                     ┌──────────▼───────────┐
                     │  AGENT ORCHESTRATOR    │  LLM tool-calling loop
                     │  (llama3.3/groq/custom)│  MAX_TOOL_ROUNDS cap
                     └──┬────────┬────────┬──┘
        ┌───────────────┘        │        └───────────────────┐
 ┌───────▼────────┐     ┌─────────▼─────────┐        ┌──────────▼──────────┐
 │ LANE A: RAG     │     │ LANE B: TOOLS      │        │ LANE C: MEMORY       │
 │ pgvector+mxbai  │     │ (MCP-exposed)      │        │ Postgres             │
 │ hybrid retrieval│     │ get_quote          │        │ user_profile         │
 │ + rerank        │     │ get_index          │        │ user_holding         │
 │ + confidence gate│    │ portfolio_calc     │        │ read every turn,     │
 │ → cited chunks  │     │ portfolio_summary  │        │ write on new prefs   │
 └───────┬────────┘     └─────────┬─────────┘        └──────────┬──────────┘
         └───────────────────────┬┴────────────────────────────┘
                     ┌───────────▼────────────┐
                     │   SYNTHESIS (LLM)        │  compose answer ONLY from gathered context
                     └───────────┬────────────┘
                     ┌───────────▼────────────┐
                     │   OUTPUT GUARDRAIL       │  block directives · enforce citations ·
                     │                          │  inject disclaimer · risk caution
                     └───────────┬────────────┘
                     ┌───────────▼────────────┐
                     │   OBSERVABILITY          │  trace_id → retrievals, tools, guardrail, latency
                     │   + EVAL HARNESS         │  golden Q&A scoring
                     └─────────────────────────┘
```

**Design principle:** the LLM decides *what* to do (retrieve / call a tool / recall memory)
via tool-calling; **code is reserved for executing tools deterministically and for the
guardrail layer as a hard, non-bypassable safety gate.**

---

## 8. Component design (detailed)

### 8.1 User interface (Gradio)
Chat interface plus an expandable **agent-trace panel** (shows each tool call and the recalled
profile per response) and **badges** for guardrail status and cache hit/miss.

### 8.2 Input guardrail (deterministic)
Classifies each turn; flags directive ("should I buy…") and high-risk ("sell everything")
patterns so the orchestrator and output guardrail apply extra caution.

### 8.3 Agent orchestrator
An LLM-driven tool-calling loop. The provider is switchable via environment variable —
**Ollama (llama3.3)**, **Groq**, or a **custom OpenAI-compatible endpoint** — all through one
OpenAI-compatible client. A round cap prevents runaway loops. Tools are registered once and
exposed to the model with JSON schemas.

### 8.4 Lane A — RAG corpus
- **Ingestion pipeline:** acquire → normalise (PDF→text) → metadata manifest → chunk → embed.
- **Chunking:** per-section for fact sheets (company name/ticker prepended to each chunk for
  numerical fidelity); per-heading for education/market; per-section for PDFs.
- **Embeddings:** mxbai-embed-large (1024-d).
- **Store:** PostgreSQL + pgvector (HNSW index) with per-chunk metadata
  (`doc_id, type, entity, source, url, as_of, locator`).
- **Retrieval:** hybrid (vector + keyword/BM25) → reranker → **confidence gate** (abstain if
  weak). Every chunk carries its citation metadata.

### 8.5 Lane B — Tools (MCP-exposed)
- `get_quote(ticker)` — live stock price (yfinance primary, NSE fallback), cached ~60s.
- `get_index(name)` — live index/sector/macro level, cached.
- `portfolio_calc(allocation, changes)` — deterministic rebalance math; validates allocation
  sums to 100%; returns error on invalid input.
- `portfolio_summary(user_id)` — an agent that reads holdings, fetches live prices, and
  computes value, P&L, sector mix, and benchmark comparison (descriptive only).

### 8.6 Lane C — Memory
Postgres tables: `user_profile` (risk tolerance, goals, preferences) and `user_holding`
(symbol, buy_date, quantity, buy_price). Read every turn for personalisation; written when the
user states a new preference. Enables cross-session recall.

### 8.7 Output guardrail (deterministic)
The hard safety gate: blocks buy/sell/invest-now language, verifies no uncited numbers,
auto-injects the educational disclaimer, and adds risk-tolerance caution on risky topics.

### 8.8 Observability & evaluation
Every request emits events under one `trace_id` (retrievals, tool calls, guardrail triggers,
latency). An evaluation harness scores answers against a golden Q&A set (faithfulness, answer
relevance, retrieval relevance) before and after error-analysis fixes.

---

## 9. Data architecture & governance

Three isolated data lanes; a fact never crosses lanes. _(Full inventory: `docs/project-overview.md`.)_

**Corpus (Lane A):** 100 company fact sheets · 6 fund/methodology PDFs · 3 market/sector/macro
docs · 2 market reports · 7 education docs · risk-profile reference.
**Tool data (Lane B):** live quotes/levels (not stored) + pure calculations.
**User data (Lane C):** 10 synthetic users, 57 stock positions (buy price/qty/date).

**Sources (all free/public, delayed):** NSE, Yahoo Finance, Screener.in, AMFI, niftyindices,
RSS (ET/MoneyControl/Business Standard).

**Governance:**
- **No fabrication** — missing values shown as "n/a"; directive/opinion fields (analyst
  ratings, targets, verdicts) excluded at ingestion.
- **Provenance** — every document dated and logged in `corpus/sources.md`; every chunk carries
  citation metadata.
- **Privacy** — user data is synthetic; no sensitive PII (PAN, bank, passwords) collected.
- **Freshness** — snapshots are dated; live data delayed and labelled as such.

---

## 10. Agentic design & orchestration

WealthPilot is **agent-driven**: the LLM reasons about the user's request and autonomously
selects tools, rather than following a hard-coded script. This keeps the system flexible
(new tools/data slot in) while code enforces only execution and safety.

- **Tool registry** emits provider-agnostic schemas (OpenAI/Anthropic) from a single
  registration; all tools are read-only (no order/trade tools exist).
- **Persona:** the assistant embodies an educational voice ("Marcus Chen's adviser"),
  defined in the system prompt with mandatory disclaimer and no-directive rules.
- **Portfolio-summarizer agent:** a specialised flow that composes the memory + quote tools to
  produce a descriptive portfolio view.

---

## 11. Guardrails, safety & compliance

Three-layer guardrail model (prompt · RAG · agentic), aligned with financial-AI best practice:

| Rule | Enforcement |
|---|---|
| No buy/sell/invest-now directive | System prompt + deterministic output block |
| Every figure cited to a source/tool | Synthesis rule + uncited-number check |
| Mandatory educational disclaimer | Auto-injected on every answer |
| Risky asks reference user's risk tolerance | Orchestrator pulls memory + caution language |
| No sensitive PII collected | Memory schema limited to profile/preferences |
| No fabricated data | "n/a" for missing; opinion fields excluded at ingestion |
| Full explainability | Per-response trace_id |

Guardrails are **deterministic code**, not prompt-only — the model cannot talk its way past
the output gate.

---

## 12. Conversation flows (sample Q&A)

Illustrative of designed behaviour (each answer cites and disclaims):

- **"Low-cost index fund for a moderate-risk investor?"** → explains TER/tracking error
  [education] + real fund figures [fund docs] + moderate ≈ 50–60% equity [risk-profiles].
- **"Current price of Reliance?"** → `get_quote` → price + as-of + source; cache-hit on repeat.
- **"Remind me my risk tolerance."** → memory recall: "moderate, 5% crypto cap."
- **"How is my portfolio doing?"** → holdings × live prices → value, P&L, sector mix; describes,
  never advises to trade.
- **"Move ₹5,000 bonds→equities?"** → `portfolio_calc` → before/after allocation + rebalancing
  explanation.
- **"Sell everything and buy Bitcoin?"** → refuses directive; explains concentration risk +
  crypto volatility, references user's moderate profile.
- **"Tell me about TCS."** → descriptive profile with cited metrics; no verdict.

_(Detailed step-by-step traces in `docs/data-architecture.md` §8.)_

---

## 13. Technology stack & infrastructure

| Layer | Technology |
|---|---|
| LLM (switchable) | Ollama (llama3.3), Groq, or custom OpenAI-compatible endpoint |
| Embeddings | mxbai-embed-large (1024-d) via Ollama |
| Vector store & memory | PostgreSQL + pgvector |
| Tool transport | MCP (Model Context Protocol) |
| UI | Gradio |
| Language / runtime | Python 3.11+ |
| Data sources | NSE, Yahoo Finance, Screener.in, AMFI, niftyindices, RSS |
| Observability | Per-trace event logging + dashboard |

Configuration is environment-driven (`.env`); corporate-network TLS handled for data pulls.

---

## 14. Delivery plan & roadmap (phased)

A four-phase plan; **Phase 0 (data foundation) is complete.**

**Phase 0 — Data foundation ✅ (done)**
Repo scaffold; provider-switch LLM client; data pipeline; 100 company fact sheets; fund/market/
education corpus; 10 synthetic users; provenance; management documentation.

**Phase 1 — RAG & UI**
Metadata manifest + PDF normalisation + validation; chunk + embed into pgvector; hybrid
retrieval + rerank + confidence gate; minimal query→cited-answer prototype; Gradio chat UI.
_Milestone: a cited RAG answer in a live chat UI._

**Phase 2 — Tools, MCP & Memory**
Finalise `portfolio_calc`; expose tools via MCP; portfolio-summarizer agent; memory store
(read/write) with cross-session recall; agent-trace panel in UI.
_Milestone: live quote + portfolio summary; profile recalled across sessions._

**Phase 3 — Guardrails & Caching**
Deterministic input/output guardrails; disclaimer injection; directive-blocking; quote caching
with visible cache-hit; run all sample queries end-to-end; UI badges.
_Milestone: guardrail fires on a risky request; cache speed-up visible._

**Phase 4 — Observability, Evaluation & Demo**
Unified trace IDs; golden-set eval harness; baseline → error analysis → fixes → re-score;
observability dashboard; edge-case handling; demo script + deployment.
_Milestone: full walkthrough + before/after eval improvement._

---

## 15. Team roles & responsibilities

| Role | Responsibility |
|---|---|
| Prompt / RAG owner | System prompt, corpus, ingestion, retrieval quality |
| Tools / MCP owner | `get_quote`, `get_index`, `portfolio_calc`, MCP integration |
| Memory owner | Profile/holdings schema, cross-session recall |
| Guardrails / caching owner | Safety gate, disclaimers, quote cache |
| Observability / UI owner | Gradio UI, trace logging, dashboard |
| Eval lead | Golden Q&A set, scoring, error analysis |

---

## 16. Evaluation & quality strategy

- **Golden Q&A set** — the canonical questions with expected/reference answers and pass criteria.
- **Metrics** — faithfulness (no hallucination), answer relevance, retrieval relevance,
  disclaimer coverage, latency, and "recommendation drift" (directive leakage).
- **Process** — baseline run → categorise failures (retrieval miss, tool error, guardrail miss,
  hallucinated figure, latency) → prioritise top fixes → re-run and record improvement.
- **Data validation** — automated range checks (P/E > 0, dividend < ~50%, allocations sum to
  100, price within 52-week range) catch bad numbers before they reach the user.

---

## 17. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| LLM hallucinates a figure | Wrong info, trust loss | RAG grounding + uncited-number check + validation layer |
| Model drifts into advice | Compliance breach | Deterministic output guardrail (not prompt-only) |
| Similar numbers confused (financial RAG failure) | Wrong-but-plausible answer | Small atomic chunks, entity tagging, hybrid retrieval + rerank |
| Data staleness | Outdated context | As-of dating; live tools for prices; refresh policy |
| Source scraping fragility/rate limits | Pipeline breakage | Multi-source fallback (yfinance→NSE), throttling, caching |
| Corporate-network TLS blocking | Data pull failures | CA-bundle / opt-in TLS handling documented |
| Over-broad scope | Delivery risk | Explicit out-of-scope list; index-fund/education focus |

---

## 18. Assumptions & dependencies

- Delayed, free/public data is acceptable for an educational assistant.
- LLM endpoints (Ollama/Groq/custom) and a PostgreSQL+pgvector instance are available.
- User portfolios are synthetic for development; a real deployment would integrate a secure
  profile source (out of current scope).
- Fund coverage is limited to Nifty 100 index funds by design.

---

## 19. Current status

| Area | Status |
|---|---|
| Data acquisition & normalisation | ✅ Complete |
| Company/fund/market/education corpus | ✅ Complete (100 + 6 + 3 + 7 docs) |
| Synthetic users & portfolios | ✅ Complete (10 users / 57 positions) |
| LLM provider abstraction + smoke test | ✅ Built |
| Live tools (quote, index) | ✅ Built |
| RAG ingestion (chunk/embed/pgvector) | ⏭ Phase 1 (next) |
| Retrieval (hybrid + rerank + confidence gate) | Planned |
| MCP, portfolio tools, memory store | Planned |
| Guardrail layer | Designed; pending |
| Gradio UI + observability | Planned |
| Evaluation harness | Planned |

**Honest summary:** the data and core plumbing exist and are verified; the intelligent
retrieval, agent, UI, and evaluation layers are designed and scheduled.

---

## 20. Future enhancements (stretch)

- Broader index-fund coverage (Nifty 50 / Next 50 as "related funds").
- Glossary and natural-language ticker resolution.
- Bond-yield / repo-rate macro context.
- Competitive analysis, security testing, richer dashboard.
- Multi-turn coreference handling for follow-up questions.

---

## 21. Appendices

### 21.1 Code structure
```
wealthpilot/
├── config.py, llm.py, embeddings.py, db.py, insecure_ssl.py, smoke_test.py
├── data/          fundamentals.py, market_indices.py, news_rss.py,
│                  reference/risk_profiles.json, profiles/{users.json,portfolios.csv}
├── ingest/        build_factsheets.py, build_market_snapshots.py,
│                  build_market_news.py, build_user_profiles.py
├── corpus/        companies/*.md (100), funds/*.pdf (6), market/*.md (3),
│                  reports/*, education/*.md (7), *.csv, sources.md
├── tools/         get_quote.py, get_index.py, cache.py
└── docs/          project-plan-and-architecture.md, project-overview.md, data-architecture.md
```
_(Planned modules: `rag/` ingestion+retrieval, `agent/` orchestrator+prompts, `memory/`,
`guardrails/`, `mcp_server/`, `obs/`, `evals/`, `app.py`.)_

### 21.2 Glossary
- **RAG** — Retrieval-Augmented Generation: grounding LLM answers in retrieved documents.
- **Embedding** — numeric vector representing text meaning; enables semantic search.
- **pgvector** — PostgreSQL extension for vector similarity search.
- **TER** — Total Expense Ratio: a fund's annual fee.
- **Guardrail** — a rule enforced on inputs/outputs to keep the assistant safe and compliant.
- **MCP** — Model Context Protocol: standard for exposing tools to an LLM agent.
- **Confidence gate** — abstaining when retrieval is too weak, to avoid fabrication.

### 21.3 Data sources
NSE (constituents, announcements), Yahoo Finance (prices, returns, identity), Screener.in
(fundamentals), AMFI (industry report), niftyindices (index factsheets/methodology), RSS
(market headlines). All public, delayed, educational-use only.
```
```
