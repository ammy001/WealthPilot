# WealthPilot — Data Architecture & Query Flow

_Educational conversational finance assistant (India / NIFTY 100). Grounded, cited,
no-directive-advice. This doc describes how data is organised and how an answer is
produced end-to-end._

---

## 1. Principles

1. **Three isolated lanes.** Static knowledge (RAG corpus), live numbers (tools), and
   user state (memory) never mix — each answer traces to exactly one origin per fact.
2. **Nothing invented.** Every quantitative claim comes from a retrieved chunk (with
   citation) or a tool output. Missing data is stated as missing.
3. **Descriptive, never directive.** No buy/sell/invest-now. Analysis fields that imply
   a verdict were stripped at ingestion.
4. **Provenance + as-of on everything.** Snapshots are dated so answers can say "as of X".

---

## 2. The three lanes

```
                          ┌────────────────────────────────────────────┐
                          │              USER (Gradio chat)             │
                          └───────────────────┬────────────────────────┘
                                              │  turn + user_id + trace_id
                                 ┌────────────▼─────────────┐
                                 │   INPUT GUARDRAIL          │ classify intent / risky ask
                                 └────────────┬─────────────┘
                                 ┌────────────▼─────────────┐
                                 │   AGENT ORCHESTRATOR       │ LLM (llama3.3 / groq / custom)
                                 │   tool-calling loop        │ decides which lane(s) to use
                                 └──┬──────────┬──────────┬──┘
              ┌──────────────────────┘          │          └───────────────────────┐
   ┌──────────▼───────────┐        ┌────────────▼───────────┐        ┌──────────────▼─────────────┐
   │  LANE A — RAG CORPUS  │        │   LANE B — LIVE TOOLS   │        │   LANE C — USER MEMORY       │
   │  (pgvector + mxbai)   │        │                         │        │                              │
   │  • company fact sheets│        │  • get_quote(ticker)    │        │  • profile (risk, goals)     │
   │  • fund fact sheets    │        │  • get_index(name)      │        │  • holdings (buy px/qty/date)│
   │  • market/sector/macro │        │  • portfolio_calc()     │        │  • preferences (crypto cap)  │
   │  • education docs       │        │    (pure math)          │        │  • conversation state        │
   │  → returns cited chunks│        │  → returns fresh JSON   │        │  → returns user record       │
   └──────────┬───────────┘        └────────────┬───────────┘        └──────────────┬─────────────┘
              └──────────────────────┬──────────┴───────────────────────────────────┘
                                 ┌────▼─────────────────────┐
                                 │   SYNTHESIS (LLM)          │ compose grounded answer
                                 └────────────┬─────────────┘
                                 ┌────────────▼─────────────┐
                                 │   OUTPUT GUARDRAIL         │ block directives, enforce
                                 │   + citation + disclaimer  │ citations, inject disclaimer
                                 └────────────┬─────────────┘
                                 ┌────────────▼─────────────┐
                                 │   OBSERVABILITY (trace_id) │ log retrievals/tools/guardrail
                                 └────────────────────────────┘
```

---

## 3. Data inventory (what feeds which lane)

| Asset | Lane | Format | Role in answers |
|---|---|---|---|
| `corpus/companies/*.md` (100) | A | markdown | Company profiles: About, valuation, profitability, growth, health, ownership, returns, float |
| `corpus/funds/*.pdf` (6) | A | PDF→text | Index-fund facts: TER, tracking error, returns, methodology |
| `corpus/market/{index,sector,macro}_*.md` | A | markdown | Index/sector/commodity performance (1M–5Y) |
| `corpus/reports/*` (AMFI PDF, RSS md) | A | PDF/md | Industry AUM, flows, category returns, headlines |
| `corpus/education/01..07` | A | markdown | Concepts: index funds, cost, risk, diversification, allocation, profiles, speculation |
| `data/reference/risk_profiles.json` | A/B | JSON | Illustrative allocation ranges per risk profile |
| `tools/get_quote.py` | B | live | Current stock price (yfinance→NSE, cached 60s) |
| `tools/get_index.py` | B | live | Current index/sector/macro level (cached 60s) |
| `portfolio_calc` (pure) | B | compute | Rebalance math on a supplied allocation |
| `data/profiles/users.json`, `portfolios.csv` | C | JSON/CSV (seed) | 10 users: risk, goals, holdings (buy px/qty/date), crypto cap |

Support data (not embedded): `nifty100_constituents.csv` (universe/keying),
`nifty100_fundamentals*.csv` (fact-sheet source + dividend/price seed), `sources.md` (provenance).

---

## 4. Ingestion pipeline (Lane A)

```
ACQUIRE ──► NORMALIZE ──► MANIFEST ──► CHUNK ──► EMBED ──► pgvector ──► RETRIEVE
 (done)     md ✅ / PDF     (planned)   (planned)  mxbai     (planned)   hybrid + rerank
            extract 🟡                            1024-d                 + confidence gate
```

**Chunking rules per doc type (planned):**
- Company fact sheet → one chunk per `##` section, **ticker + company name prepended** to every chunk (numerical-fidelity: keeps each metric tied to its entity).
- Education / market docs → one chunk per heading.
- PDFs → per page/section; the 328-page methodology → only Nifty-100 sections.

**Proposed pgvector schema:**
```sql
CREATE TABLE chunks (
  id           bigserial PRIMARY KEY,
  doc_id       text,           -- e.g. company:RELIANCE, fund:nippon_etf, edu:06-risk-profiles
  doc_type     text,           -- company | fund | market | report | education
  entity       text,           -- ticker / sector / null
  title        text,
  section      text,
  chunk_text   text,
  embedding    vector(1024),
  source       text,           -- Screener.in / Yahoo / AMFI / niftyindices / authored
  url          text,
  as_of        date,
  locator      text            -- page N / section name
);
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON chunks USING gin (to_tsvector('english', chunk_text));  -- BM25/keyword
```

**Retrieval (planned, per financial-RAG best practice):** hybrid (vector + keyword) →
rerank → **confidence gate** (if top score < threshold, abstain: "I don't have that").
Every retrieved chunk carries `source/url/as_of/locator` → becomes the citation.

---

## 5. Memory (Lane C)

`data/profiles/users.json` is **seed** data. Runtime store (planned) in Postgres:
```sql
CREATE TABLE user_profile (
  user_id     text PRIMARY KEY,
  risk_tolerance text, goals jsonb, preferences jsonb, updated_at timestamptz );
CREATE TABLE user_holding (
  user_id text, symbol text, buy_date date, quantity numeric, buy_price numeric );
```
Read at every turn (personalisation), written when the user states a new preference.
Cross-session recall (query 4) reads `risk_tolerance` back in a later session.

---

## 6. Query-time orchestration

1. **Input guardrail** — flag directive/risky asks ("should I buy…", "sell everything").
2. **Orchestrator LLM** picks lanes via tool-calling: `rag_search(query, filter)`,
   `get_quote`, `get_index`, `portfolio_calc`, `get_user`.
3. **Gather** — retrieved chunks + tool JSON + user record, all tagged with source.
4. **Synthesis** — LLM writes the answer **only** from gathered context, citing each fact.
5. **Output guardrail** — block buy/sell language, verify every number has a source,
   inject the educational disclaimer, add risk-tolerance caution on risky topics.
6. **Observability** — one `trace_id` logs retrievals, tool calls, guardrail events, latency.

---

## 7. Sample queries by type

**RAG-only (education + funds)**
- "What's a good low-cost index fund for a moderate-risk investor?"
- "What does expense ratio mean and why does it matter?"
- "What was the Nifty 100 index's return last year?"

**Company RAG**
- "Tell me about TCS." / "What are Reliance's key financials?"
- "Which Nifty 100 companies are in the IT sector?"

**Live tools**
- "What's the current price of Reliance?" / "Where is the Nifty right now?"
- "How has the IT sector performed this year?"

**Memory / personal**
- "Remind me what my risk tolerance is."
- "How is my portfolio doing?" (portfolio-summarizer)

**Compute**
- "If I move ₹5,000 from bonds to equities, what's my new allocation?"

**Guardrail**
- "Should I sell everything and buy Bitcoin?"
- "Which stock will make me the most money?"

---

## 8. Detailed answer-generation traces

### Q1 — "What's a good low-cost index fund for a moderate-risk investor?"
- **Input guardrail:** advice-shaped but educational → allow, tag "recommendation-sensitive".
- **Orchestrator:** `rag_search("low-cost index fund moderate risk", filter type in [fund,education])`.
- **Lane A retrieves:** `education/02-costs-and-expense-ratio` (what low-cost/TER means),
  `education/06-risk-profiles` (moderate ≈ 50–60% equity), `funds/nippon_india_etf_nifty100`
  & `funds/axis_nifty100_index_fund` (real TER + tracking error).
- **Synthesis:** explains that a low-cost index fund = low TER + low tracking error; a Nifty 100
  index fund/ETF is a broad-equity option; notes it is *all equity*, so for a moderate profile
  it is typically one component alongside debt/gold (cites risk-profiles doc).
- **Output guardrail:** no "buy X"; reframed as "here's how to evaluate low-cost index funds";
  disclaimer appended; each figure cited to a fund doc.
- **Answer (shape):** "A 'low-cost' index fund mainly means a low expense ratio and low tracking
  error [education/02]. Among Nifty 100 options, e.g. the Nippon India Nifty 100 ETF lists a TER
  of X% and tracking error of Y% [funds/nippon…, as of Jun 2026]. Note an index fund is fully
  equity; a moderate-risk profile is often ~50–60% equity with the rest in debt/gold
  [education/06]. This is educational, not a recommendation."

### Q2 — "What's the current price of Reliance?"
- **Input guardrail:** benign → allow.
- **Orchestrator:** resolves "Reliance" → `RELIANCE`; calls `get_quote("RELIANCE")` (Lane B).
- **Tool:** yfinance→NSE, returns `{price, currency, timestamp, source, cache_hit}`.
- **Synthesis:** states price + as-of time + source; **no RAG** (a price is never a corpus fact).
- **Output guardrail:** disclaimer (delayed data); no directive.
- **Answer:** "RELIANCE is ₹1,301.70 (delayed, source: yfinance, as of 2026-07-10 12:03 UTC).
  Cache: miss." A repeat within 60s shows `cache_hit=true` (UI badge).

### Q3 — "Remind me what my risk tolerance is."
- **Orchestrator:** `get_user(user_id)` (Lane C) — no RAG, no tools.
- **Memory returns:** `risk_tolerance="moderate"`, plus crypto_cap=5%.
- **Answer:** "You told me your risk tolerance is **moderate** (with a 5% cap on crypto)." Pure
  recall; demonstrates cross-session memory.

### Q4 — "How is my portfolio doing?" (portfolio-summarizer)
- **Orchestrator:** `get_user(user_id)` → holdings (Lane C); then `get_quote` per symbol (Lane B).
- **Compute:** current value = Σ(qty × live price); P&L = current − Σ(qty × buy_price); sector mix
  from holdings' sectors; benchmark vs Nifty 100 (Lane B `get_index`).
- **Synthesis:** table of holdings with buy vs current, total invested vs current value, P&L %,
  sector concentration, and a neutral observation (e.g. "72% in Financials — concentrated").
- **Output guardrail:** describes state; **no** "sell/trim" instruction; if concentration is high,
  it *notes* it and references the diversification education doc, not a directive.

### Q5 — "If I move ₹5,000 from bonds to equities, what's my new allocation?"
- **Orchestrator:** needs current allocation. If the user has a stated allocation use it; else use
  their holdings / an illustrative base. Calls `portfolio_calc(current_allocation, {bonds:-5000, equity:+5000})`.
- **Tool (pure):** returns new percentages + validation (must sum to 100; error if invalid).
- **Synthesis:** shows before → after percentages; cites `education/05-asset-allocation` for what
  rebalancing means. No advice on whether to do it.
- **Answer:** "Moving ₹5,000 changes your mix from 60/35/5 to ~62/33/5 (equity/debt/gold).
  Rebalancing simply realigns to a target [education/05]. Educational only."

### Q6 — "Should I sell everything and buy Bitcoin?" (guardrail showcase)
- **Input guardrail:** matches directive + high-risk pattern → **flag**.
- **Orchestrator:** `get_user` (risk_tolerance, crypto_cap) + `rag_search` education
  (`07-equities-vs-speculative-assets`, `04-diversification`) + optional `get_index` macro context.
- **Synthesis + output guardrail (hard):** must NOT say buy/sell. Produces educational framing:
  concentration risk, crypto volatility (50–80% drawdowns) [education/07], contrast with your
  **stated moderate tolerance and 5% crypto cap** [memory], value of diversification [education/04].
  Ends with disclaimer + "decision is yours".
- **Answer (shape):** "I can't tell you to buy or sell. Here's context: putting everything into one
  highly volatile asset removes diversification [education/04]; crypto has historically seen very
  large swings [education/07]. You've set a moderate risk tolerance with a 5% crypto cap [your
  profile] — a full switch would be far outside that. Educational only."

### Q7 — "Tell me about TCS." (company RAG)
- **Orchestrator:** `rag_search("TCS", filter entity=TCS, type=company)` → `companies/TCS.md`.
- **Synthesis:** About (business), sector, key descriptive metrics (P/E, ROE, margins, returns),
  each cited to the fact sheet with as-of date. May add IT-sector context [market/sector].
- **Output guardrail:** descriptive only; if user asks "is it a good buy?" → decline the verdict,
  offer the descriptive facts + how to evaluate (education), never a recommendation.

---

## 9. Guardrail enforcement (cross-cutting)

| Rule | Where enforced |
|---|---|
| No buy/sell/invest-now directive | Output guardrail (deterministic block) + system prompt |
| Every number cited to source/tool | Synthesis instruction + output check (no uncited figures) |
| Disclaimer on every answer | Output guardrail (auto-inject) |
| Risk asks reference user's tolerance | Orchestrator pulls memory + output caution |
| No sensitive PII collected | Memory schema limited to profile/preferences |
| Full explainability | trace_id logs retrievals, tools, guardrail events |
```
```
