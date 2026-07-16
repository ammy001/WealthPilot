# 💹 WealthPilot

> **An educational, agentic, cited RAG assistant for Indian markets (NIFTY 100).**
> It explains, contextualises, and personalises — but **never** tells you to buy or sell,
> and **never** fabricates a number.

WealthPilot (persona: *Marcus Chen*) is a conversational finance assistant that combines
**retrieval-augmented generation**, **live tools**, **cross-session memory**, and a hard
**guardrail** layer. Every quantitative claim is traceable to a retrieved document
(RAG citation) or a live tool output, and every answer carries an educational disclaimer.

---

## ⚠️ Disclaimer

WealthPilot is an **educational** assistant. It does **not** provide investment advice,
buy/sell/invest-now directives, price predictions, or trading signals. All market data is
delayed and for educational use only. Nothing here is a recommendation to transact.

---

## Table of contents

1. [Highlights](#highlights)
2. [Demo — the canonical queries](#demo--the-canonical-queries)
3. [Architecture](#architecture)
4. [Agentic RAG (deep dive)](#agentic-rag-deep-dive)
5. [Guardrails](#guardrails)
6. [Technology stack](#technology-stack)
7. [Data / corpus](#data--corpus)
8. [Project structure](#project-structure)
9. [Quick start (local)](#quick-start-local)
10. [Run on Google Colab (free GPU)](#run-on-google-colab-free-gpu)
11. [Deploy as an API (FastAPI + Docker)](#deploy-as-an-api-fastapi--docker)
12. [Configuration reference](#configuration-reference)
13. [How a turn is processed](#how-a-turn-is-processed)
14. [Roadmap](#roadmap)

---

## Highlights

- **📚 Cited RAG** — hybrid retrieval (dense + keyword) → RRF fusion → cross-encoder rerank →
  confidence gate → grounded answer with inline `[S#]` citations.
- **🔁 Agentic retrieval** — multi-query (RAG-Fusion) + CRAG-style grading with corrective
  re-retrieval, so the right chunk is found even when a single phrasing would miss it.
- **🛠️ Live tools** — real-time stock quotes, index/sector levels, portfolio valuation & P&L,
  and rebalance math; outputs are formatted deterministically (no invented figures).
- **🧠 Memory** — per-user risk profile & holdings for *personalised* (never directive) context.
- **🛡️ Deterministic guardrails** — block directive advice, enforce citations, inject the
  disclaimer, and route risky asks through a safe educational path.
- **🔀 Provider-switchable LLM** — `ollama` · `groq` · `azure` · custom OpenAI-compatible, with
  a **decoupled fast helper model** for the lightweight agentic steps.
- **🔎 Full explainability** — every response returns a trace (route, args, guardrail verdict,
  cache hit, sources) surfaced in the UI.

---

## Demo — the canonical queries

Select user **Marcus Chen (U001)**, open the **🔎 Agent trace** panel, and try:

| # | Query | Exercises | Route |
|---|-------|-----------|-------|
| 1 | *What's a good low-cost index fund for a moderate-risk investor?* | Cited RAG + education | `general_knowledge` |
| 2 | *What's the current price of Reliance?* | `get_quote` + cache badge | `get_quote` |
| 3 | *How did the FMCG sector perform in the last 6 months?* | **Agentic recall** (multi-query + rerank) | `general_knowledge` |
| 4 | *How is my portfolio doing?* | Memory + live valuation / P&L | `portfolio_summary` |
| 5 | *Remind me what my risk tolerance is.* | Memory recall | `general_knowledge` |
| 6 | *If I move ₹5,000 from bonds to equities, what's my new allocation?* | `portfolio_calc` | `rebalance` |
| 7 | *Should I sell everything and buy Bitcoin?* | 🛡️ Guardrail (no-directive + risk ref) | `general_knowledge(safety)` |

> **Q3 is the showcase:** a plain top-k RAG *misses* the sector table; the agentic loop
> reformulates → re-retrieves → grades until it surfaces *Nifty FMCG −10.61%*, correctly cited.

---

## Architecture

### Request flow
```
                       ┌───────────────────────────────────────────┐
                       │            Gradio UI (chat + trace)        │
                       └───────────────────────┬───────────────────┘
                                                │  user message
                                                ▼
                                   ┌────────────────────────┐
                                   │      INPUT GUARDRAIL     │  flag directive / risky
                                   └────────────┬────────────┘
                                                ▼
                                   ┌────────────────────────┐
                                   │    AGENT ORCHESTRATOR    │  1 LLM call · tool_choice=auto
                                   │  (router + arg extract)  │  → picks ONE lane
                                   └────────────┬────────────┘
        ┌──────────────┬──────────────┬─────────┴────────┬──────────────────────┐
        ▼              ▼              ▼                  ▼                      ▼
    get_quote      get_index    portfolio_summary    rebalance          general_knowledge
    (live price)   (live index) (value / P&L)        (calc)             (→ Agentic RAG)
        │              │              │                  │                      │
        └──────────────┴───────┬──────┴──────────────────┘                      │
                               ▼                                                 ▼
                  deterministic formatting                            ┌─────────────────────┐
                   (no fabricated numbers)                            │     AGENTIC RAG      │
                               │                                      └──────────┬──────────┘
                               ▼                                                 │
                                   ┌────────────────────────┐                    │
                                   │     OUTPUT GUARDRAIL     │ ◀──────────────────┘
                                   │ no-directive · cite · disclaimer            │
                                   └────────────┬────────────┘
                                                ▼
                                cited answer  +  agent trace   →   UI
```

### Data lanes
Three isolated lanes feed the orchestrator; a fact never crosses lanes:
- **Lane A — RAG corpus** (pgvector + embeddings) → cited chunks
- **Lane B — live tools** (`get_quote` / `get_index` / `portfolio_calc`) → fresh JSON
- **Lane C — user memory** (profile + holdings) → user record

---

## Agentic RAG (deep dive)

The `general_knowledge` lane is a coverage-aware loop (`rag/agentic_retrieve.py`) that fixes
the classic "only top-k chunks retrieved" recall problem:

```
   query
     │  ① multi-query : LLM writes N diverse reformulations           (RAG-Fusion)
     ▼
     ├─ ② hybrid retrieve (per query):
     │        • pgvector dense (cosine, HNSW)   • Postgres full-text (keyword, GIN)
     │        ▼
     │     ③ Reciprocal Rank Fusion  → dedup & merge candidates
     │        ▼
     │     ④ cross-encoder rerank  (against the ORIGINAL query)
     ▼
     ⑤ CRAG grader (LLM): which chunks are relevant? sufficient? what's missing?
        │
        ├─ sufficient ───────────────────────────►  ⑦ grounded answer (LLM, inline [S#])
        └─ insufficient → ⑥ add follow-up queries, relax filters ─► back to ②  (≤ RAG_MAX_ITERS)
```

Key design choices:
- **Closed-corpus CRAG:** the corrective action is query reformulation + filter relaxation
  (no web fallback) — it searches *harder* over our own corpus.
- **Top-hit safeguard:** a strongly-reranked chunk is never discarded by the grader.
- **Decoupled fast helper:** subquery generation + grading run on `chat_fast` (a cheap/fast
  model), so those steps stay cheap even if the main answer model is heavier.
- **Adaptive by env:** `RAG_AGENTIC=0` falls back to single-pass RAG; `RAG_N_SUBQUERIES`,
  `RAG_MAX_ITERS`, `RAG_RERANK_POOL` tune the cost/quality trade-off.

Tunable knobs: `RAG_N_SUBQUERIES` (3), `RAG_MAX_ITERS` (2), `RAG_RERANK_POOL` (40),
`RAG_GRADE_POOL` (10), `RAG_GRADE_SNIPPET` (1200), `RAG_CONF_THRESHOLD` (0.02), `RAG_KEEP_SCORE` (0.3).

---

## Guardrails

| Rule | Enforcement |
|---|---|
| No buy/sell/invest-now directive | Deterministic output check + LLM rewrite fallback + system prompt |
| Every figure cited to a source/tool | Grounding rule + citation enforcement |
| Mandatory educational disclaimer | Auto-injected on every answer |
| Risky asks reference the user's risk tolerance | Safety path pulls memory + caution language |
| No sensitive PII collected | Memory limited to profile/preferences |
| No fabricated data | Missing values → "n/a"; abstain when retrieval is weak |
| Full explainability | Per-response trace (route, args, guardrail, sources) |

Risky/directive inputs (e.g. *"sell everything and buy Bitcoin"*) short-circuit to a
**safety path** that answers educationally (never abstains), grounds in the concept docs,
references the user's crypto cap, and makes clear the decision is theirs.

---

## Technology stack

| Layer | Options / default |
|---|---|
| **LLM** | `ollama` (llama3.x) · `groq` (llama-3.1-8b-instant) · `azure` (gpt-4o-mini) · custom OpenAI-compatible |
| **Fast helper LLM** | `FAST_LLM_PROVIDER` / `FAST_LLM_MODEL` (defaults to the main LLM) |
| **Embeddings** | `mxbai-embed-large` (1024-d) · light option `nomic-embed-text` (768-d) |
| **Reranker** | `BAAI/bge-reranker-v2-m3` · light option `mixedbread-ai/mxbai-rerank-xsmall-v1` |
| **Vector store + memory** | PostgreSQL + **pgvector** (HNSW + GIN) |
| **UI** | Gradio |
| **API** | FastAPI + Uvicorn (`deploy/`) |
| **Data sources** | NSE, Yahoo Finance, Screener.in, AMFI, niftyindices, RSS (all free/delayed) |
| **Language** | Python 3.11+ |

---

## Data / corpus

≈ 6 MB, ~120 documents across three lanes. Highlights:

- **100 company fact sheets** (`corpus/companies/*.md`) — ~30 descriptive fields each; **no**
  analyst ratings / price targets / verdicts (guardrail).
- **6 fund / methodology PDFs** (`corpus/funds/`) — Nifty 100 index + real index funds/ETFs.
- **Market data** (`corpus/market/`) — index, sector, and macro/commodity performance tables.
- **7 education notes** (`corpus/education/`) — index funds, costs, risk/return, diversification,
  asset allocation, risk profiles, equities vs speculative assets.
- **Synthetic users** (`data/profiles/`) — 10 users / 57 positions; NIFTY 100 stock holdings with
  realistic buy prices. Fully synthetic — no real PII. `U001` = Marcus Chen.

See `docs/project-overview.md` and `docs/data-architecture.md` for the full inventory.

---

## Project structure

```
wealthpilot/
├── app.py                  # Gradio UI (chat + agent-trace panel + badges)
├── config.py               # env-driven config; LLM provider switch + fast-helper
├── llm.py                  # provider-switching chat client (chat / chat_fast)
├── embeddings.py           # embeddings via Ollama-native endpoint
├── db.py                   # Postgres / pgvector connection
├── memory.py               # user profile accessor
├── smoke_test.py           # verifies LLM + tool-calling + embeddings + pgvector
├── insecure_ssl.py         # corporate-proxy TLS handling
├── colab_setup.sh          # one-shot Colab installer (Ollama + Postgres + pgvector)
│
├── agent/
│   └── orchestrator.py     # router (forced/auto tool-choice) + lane dispatch + safety path
├── rag/
│   ├── chunk.py            # per-doc-type chunking with citation metadata
│   ├── ingest.py           # chunk → embed → pgvector (vector dim follows EMBED_DIM)
│   ├── retrieve.py         # hybrid + RRF + rerank + confidence gate
│   ├── agentic_retrieve.py # multi-query + CRAG corrective loop
│   └── answer.py           # grounded, cited answer (+ safety path)
├── tools/
│   ├── get_quote.py        # live stock price (yfinance → NSE, cached)
│   ├── get_index.py        # live index/sector level (cached)
│   ├── portfolio_calc.py   # deterministic rebalance math
│   ├── portfolio_summary.py# holdings × live quotes → value / P&L / sector mix
│   └── cache.py            # TTL cache (drives the cache-hit badge)
├── guardrails/
│   └── rules.py            # classify_input + enforce (block/rewrite/disclaimer)
├── data/                   # datasets + reusable data modules + risk_profiles.json
├── corpus/                 # the RAG corpus (companies, funds, market, education, reports)
├── ingest/                 # corpus generators (fact sheets, snapshots, news, profiles)
├── deploy/                 # FastAPI service (api.py) + Dockerfile + README
└── docs/                   # overview, data-architecture, roadmap, workflow
```

---

## Quick start (local)

```bash
python -m venv .venv && . .venv/Scripts/activate      # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                                  # fill in your endpoints/keys
python smoke_test.py                                  # verify LLM + embeddings + pgvector
python -m rag.ingest                                  # chunk + embed corpus → pgvector
python app.py                                         # Gradio UI at http://127.0.0.1:7860
```

---

## Run on Google Colab (free GPU)

A fully free stack: **Groq** (LLM) + local **Ollama** embeddings + local **cross-encoder**
reranker + local **pgvector**. Set **Runtime → T4 GPU**, then (see `WealthPilot_Demo.ipynb`):

```python
# 1. upload & unzip the project
from google.colab import files; files.upload()        # wealthpilot_colab.zip
!unzip -q wealthpilot_colab.zip -d /content/ && %cd /content/wealthpilot

# 2. install stack (Ollama + Postgres + pgvector + deps)
!bash colab_setup.sh && pip install -q -r requirements.txt

# 3. start Ollama + pull embedder
import subprocess; subprocess.Popen(["ollama","serve"]); import time; time.sleep(8)
!ollama pull nomic-embed-text

# 4. write .env (LLM_PROVIDER=groq + GROQ_API_KEY, local embed/rerank/pg) — see the notebook

# 5. verify → ingest → launch
!python smoke_test.py
!python -m rag.ingest
import app; app.demo.launch(share=True)
```

The bundled **`WealthPilot_Demo.ipynb`** has the full, annotated, demo-ready sequence.

---

## Deploy as an API (FastAPI + Docker)

`deploy/api.py` wraps the same agent behind a JSON API and pre-loads the reranker at startup.

```bash
# bare
uvicorn deploy.api:app --host 0.0.0.0 --port 8000     # or: python deploy/api.py

# docker (build from project root)
docker build -f deploy/Dockerfile -t wealthpilot-api .
docker run --env-file .env -p 8000:8000 wealthpilot-api
```

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | `{status, provider, model, reranker_ready}` — readiness probe |
| GET | `/users` | synthetic user list |
| POST | `/chat` | `{"message": "...", "user_id": "U001"}` → `{answer, route, sources, trace}` |
| GET | `/docs` | Swagger UI |

---

## Configuration reference

Set via `.env` (see `.env.example`):

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `ollama` \| `groq` \| `azure` \| `custom` |
| `OLLAMA_* / GROQ_* / AZURE_* / CUSTOM_*` | per-provider base URL, key, model |
| `FAST_LLM_PROVIDER` / `FAST_LLM_MODEL` | cheap/fast helper for agentic subquery + grading |
| `EMBED_BASE_URL` / `EMBED_PATH` / `EMBED_MODEL` / `EMBED_DIM` | embeddings endpoint + dim |
| `RERANKER_MODEL` | cross-encoder id (sentence-transformers) |
| `PG_DSN` / `PG_SCHEMA` | Postgres connection + schema |
| `RAG_AGENTIC` | `1` agentic loop (default) · `0` single-pass |
| `RAG_N_SUBQUERIES` / `RAG_MAX_ITERS` / `RAG_RERANK_POOL` | agentic tuning |
| `RAG_CONF_THRESHOLD` / `RAG_KEEP_SCORE` | confidence gate thresholds |
| `INSECURE_SSL` / `CA_BUNDLE` / `HF_HUB_OFFLINE` | TLS / offline handling |

> **Changing the embedding model changes the vector dimension** — update `EMBED_DIM` and
> re-run `python -m rag.ingest` (the table is (re)built to `vector(EMBED_DIM)`).

---

## How a turn is processed

1. **Input guardrail** flags directive/risky intent.
2. **Router** (1 LLM call) picks one lane and extracts arguments.
3. **Tool lanes** return real data, formatted deterministically.
4. **Knowledge lane** runs the agentic RAG loop → grounded, cited answer.
5. **Output guardrail** blocks directives, enforces citations, injects the disclaimer.
6. **Trace** is returned for full explainability.

---

## Roadmap

- Self-RAG answer-level critique (faithfulness), self-query metadata filters, query
  decomposition for comparisons, HyDE / Contextual Retrieval re-ingest.
- Adaptive complexity router (simple single-pass vs. deep agentic).
- pgvector-backed memory store, MCP tool exposure, observability trace persistence + eval
  harness (golden Q&A), per-row/table-aware chunking.

See `docs/advanced-rag-roadmap.md`.

---

_WealthPilot is an educational project. Not investment advice._
