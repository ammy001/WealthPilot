# WealthPilot — Engineering Handover

_Written for whoever picks this project up next. Goal: after reading this, you should be
able to run the app, understand every module, know what's done vs. planned, and know
where to look for more detail without having to read the whole codebase cold._

Course context: this build follows a 4-week / 32-task class plan (`requirements.md` +
`tasks.md`). **Weeks 1–2 (16/32 tasks) are complete**; several Week 3–4 items
(guardrails, caching, MCP, observability, an eval harness) are also already built, ahead
of schedule. See §11 for the full status table.

---

## 1 · What this is, in one paragraph

WealthPilot is an educational, conversational finance assistant scoped to Indian equities
(the NIFTY 100 universe). A user chats in natural language; the system answers with
**grounded, cited, non-directive** information — RAG over a curated corpus, live tools for
prices/index levels/portfolio math, and per-user memory of risk tolerance and holdings —
wrapped in a **deterministic guardrail layer** that blocks buy/sell/invest-now language and
enforces a disclaimer on every answer. It never gives directive investment advice and never
fabricates a number: every quantitative claim traces back to a cited document or a tool
call. Persona: "Marcus Chen," a moderate-risk investor who wants explanations, not verdicts.

---

## 2 · Architecture — the three lanes

```
                          ┌────────────────────────────────────────────┐
                          │              USER (Gradio chat)             │
                          └───────────────────┬────────────────────────┘
                                              │  turn + user_id + history
                                 ┌────────────▼─────────────┐
                                 │   INPUT GUARDRAIL          │ classify_input(): directive/risky?
                                 └────────────┬─────────────┘
                       directive/risky? ──yes──► SAFETY PATH: rag.answer (education-filtered, never abstains)
                                 │ no
                                 ┌────────────▼─────────────┐
                                 │   AGENT ORCHESTRATOR       │ ONE tool_choice="auto" LLM call
                                 │   (router + arg extract)   │ picks exactly one lane below
                                 └──┬────┬────┬────┬────┬────┘
              ┌──────────┬─────────┘    │    │    │    └──────────────────┐
   ┌──────────▼──┐ ┌──────▼─────┐ ┌─────▼────────┐ ┌▼─────────┐ ┌─────────▼──────────┐
   │  get_quote  │ │ get_index  │ │portfolio_    │ │rebalance │ │ update_preference   │
   │ (Lane B)    │ │ (Lane B)   │ │summary       │ │(Lane B   │ │ (Lane C — WRITE)    │
   │ live price  │ │live level  │ │(Lane B+C)    │ │ pure calc)│ │ persists a stated   │
   │             │ │            │ │value/P&L/mix │ │          │ │ preference to disk  │
   └──────┬──────┘ └─────┬──────┘ └──────┬───────┘ └────┬─────┘ └──────────┬──────────┘
          └───────────────┴───────┬───────┴──────────────┘                  │
                                  ▼                                          │
                    deterministic text formatting                           │
                     (no fabricated numbers)                                │
                                  │                                          │
   ┌──────────────────────────────┼──────────────────────────────────────────┘
   │                              ▼
   │                  ┌───────────────────────┐    (general_knowledge route falls here)
   │                  │   OUTPUT GUARDRAIL      │ ◄── LANE A: Agentic RAG (rag.answer)
   │                  │  enforce(): block/      │     hybrid retrieve → rerank → confidence
   │                  │  rewrite directive,     │     gate → CRAG grading/corrective loop →
   │                  │  inject disclaimer      │     grounded synthesis, cited [S#]
   │                  └───────────┬─────────────┘
   │                              ▼
   └──────────────────► OBSERVABILITY (obs.trace.log_turn) → answer + trace → UI
```

**Design principle** (deliberate, not incidental): the LLM decides *what* to do
(retrieve / call a tool / recall or update memory) via tool-calling. Code is reserved for
(a) executing each lane deterministically — so no lane can invent a number — and (b) the
guardrail layer, which is regex, not a prompt instruction, so the model cannot reason its
way past it.

### 2.1 The three data lanes

| Lane | What | Backing | Read/Write |
|---|---|---|---|
| **A — RAG corpus** | Company/fund/market/education documents | Postgres + pgvector (`wp_chunks`) | Read (ingested offline via `rag/ingest.py`) |
| **B — Live tools** | Prices, index levels, portfolio math | yfinance / NSE (cached), pure functions | Read/compute, not stored |
| **C — User memory** | Risk tolerance, goals, preferences, holdings | `data/profiles/users.json` | **Read and write** (`memory.py`) |

A fact never crosses lanes: a price only ever comes from Lane B, narrative only from a
cited Lane A chunk, personal data only from Lane C.

---

## 3 · Full code map

### 3.1 Root — config & infra

| File | Purpose |
|---|---|
| `config.py` | Env-driven config. `LLM_PROVIDER` switches between `ollama`/`groq`/`custom`/`azure` (each returns a `{base_url, api_key, model, header_name}` dict from `_provider_config`). Also defines `FAST_LLM` (a cheaper/faster model for lightweight agentic steps, defaults to same as main), `EMBED` (mxbai/Ollama-native embedding endpoint config), and `PG`/`PG_DSN`/`PG_SCHEMA` (Postgres connection). |
| `llm.py` | Builds the actual OpenAI-compatible (or `AzureOpenAI`) client(s) from `config.py`. Exposes `chat()` (main answer model) and `chat_fast()` (the fast helper, reuses the main client if identical). `_tls_verify()` handles corporate SSL-inspection proxies via `INSECURE_SSL`/`CA_BUNDLE` env vars. |
| `db.py` | `connect()` — psycopg2 connection using `PG_DSN` or assembled `PG` parts; sets `search_path` to `PG_SCHEMA` if not `public`. `ensure_vector_extension()` creates the pgvector extension if missing. |
| `embeddings.py` | `embed_one(text)` / `embed(texts, max_workers=3)` — calls the mxbai (Ollama-native) embedding endpoint, with retry/backoff for 502s under load. |
| `memory.py` | Lane C accessor. `get_user(user_id)` / `list_users()` read `data/profiles/users.json`. **`update_preferences(user_id, **fields)`** (added Week 2) writes a stated preference back to the same file — routes top-level fields (`risk_tolerance`, `goals`, `monthly_investment_inr`) vs. anything else into the nested `preferences` dict, then rewrites the whole file. See `docs/memory-schema.md`. |
| `insecure_ssl.py` | `maybe_disable_tls_verification()` — if `INSECURE_SSL=1`, monkeypatches `httpx`, `requests`, `curl_cffi`, and stdlib `ssl` to skip cert verification, for corporate MITM proxies. Explicitly documented as insecure/opt-in only. |
| `smoke_test.py` | Standalone plumbing check — chat completion, tool-calling, embedding dimension, pgvector reachability. Each check is independent (one failure doesn't stop the others); prints PASS/FAIL + a final JSON summary; exits non-zero on any failure. |
| `app.py` | The Gradio UI — see §4. |
| `azure_test.py` | Ad-hoc personal script for testing the Azure OpenAI provider directly; not part of the app's import graph. |
| `requirements.txt` | `openai`, `python-dotenv`, `psycopg2-binary`, `pgvector`, `gradio>=6.0`, `pypdf`, `mcp`, `yfinance`, `niftystocks`, `nsepython`, `sentence-transformers`, `torch`, `feedparser`, `httpx`, `fastapi`, `uvicorn`, `matplotlib`. |
| `colab_setup.sh` | Installs Ollama + builds pgvector from source + starts Postgres, for a fresh Colab VM. Idempotent-ish (checks before re-cloning pgvector). |

### 3.2 `agent/` — orchestration

| File | Purpose |
|---|---|
| `orchestrator.py` | The single entry point: **`respond(query, user=None, history=None)`**. Flow: (1) if `history` given, rewrite a follow-up into a standalone query via `rag.query_ops.rewrite_with_history`; (2) `guardrails.classify_input` — if directive/risky, force the **safety path** straight into `rag.answer` (never abstains, always educational); (3) else `_route(query)` — one `tool_choice="auto"` LLM call against 6 tool schemas (`get_quote`, `get_index`, `portfolio_summary`, `rebalance`, `update_preference`, `general_knowledge`), retried once on a malformed tool call before defaulting to `general_knowledge`; (4) dispatch to the chosen lane, formatting tool output **deterministically** (`_fmt_quote`, `_fmt_index`, `_fmt_portfolio`, `_rebalance_answer`); (5) `guardrails.enforce()` on the result text; (6) `_finish()` → `obs.trace.log_turn` (wrapped so logging never breaks a response). Returns `{answer, route, sources, trace}`. |

### 3.3 `rag/` — retrieval-augmented generation

| File | Purpose |
|---|---|
| `chunk.py` | `build_all()` — turns the corpus into chunk dicts. Markdown docs split on `## ` headings, with the doc title (+ ticker, for companies) prepended to every chunk for numerical fidelity. PDFs windowed into ~1500-char pieces with page-range locators (large reference PDFs capped, e.g. the 328-page methodology doc → 40 pages). |
| `ingest.py` | `main()` — embeds every chunk (mxbai, dimension from `config.EMBED['dim']`) and does a DROP+CREATE+batch-INSERT into `wp_chunks`, then builds an HNSW (cosine) index, a GIN (full-text) index, and entity/doc_type indexes. Idempotent — safe to re-run after any corpus change. Run: `python -m rag.ingest`. |
| `retrieve.py` | `search(query, k=6, filters=None)` — hybrid retrieval: `_vector_search` (pgvector `<=>` cosine) + `_keyword_search` (Postgres `ts_rank`/`websearch_to_tsquery`), fused by **Reciprocal Rank Fusion** (`_rrf`), then reranked by a cross-encoder (`BAAI/bge-reranker-v2-m3`, lazy-loaded). Returns `(results, confident)` where `confident = top_rerank_score >= RAG_CONF_THRESHOLD`. `fuse_candidates()` and `rerank_rows()` are exposed separately so the agentic layer can fuse across many query reformulations. |
| `agentic_retrieve.py` | `agentic_search(query, k=6, ...)` — the default retrieval path (`RAG_AGENTIC=1`). A genuine loop: (1) `_gen_subqueries` — fast-LLM generates N reformulations (RAG-Fusion); (2) fuse+rerank across all of them; (3) `_grade` — fast-LLM CRAG-style grader decides which chunks are relevant and whether coverage is *sufficient*, proposing follow-up queries if not; (4) if insufficient, re-retrieve with the follow-ups (relaxing filters once), up to `RAG_MAX_ITERS` passes; (5) if still not confident, `_news_results` pulls live RSS market headlines as a closed-corpus corrective fallback, reranked in. A safeguard never lets the grader drop a very strongly-reranked top hit. Returns `(results, confident, trace)`. |
| `query_ops.py` | `rewrite_with_history(query, history)` — coreference resolution for follow-ups ("what about its P/E?" → a standalone query), using the fast LLM and the last few turns; degrades to the original query on any failure. `decompose(query)` — splits a comparison/multi-part question ("compare TCS and Infosys") into standalone sub-questions via the fast LLM; returns `[query]` unchanged if it's already single. |
| `answer.py` | `answer(query, k=6, filters=None, user=None, agentic=None)` — the cited-RAG synthesis entry point. Runs `classify_input`; on risky/directive, searches only `doc_type=education` and never abstains (the safety path). Otherwise uses `agentic_search` (optionally via `decompose` + `_multi_agentic` for comparison questions) or falls back to plain `search()` if `RAG_AGENTIC=0`. If not confident, returns a fixed abstention string without ever calling the answer LLM. Otherwise builds a `SOURCES` context block (`_format_sources`, tagged `[S1]`, `[S2]`...), calls the main LLM with a strict system prompt (answer ONLY from sources, cite inline, never invent a number, never give directive advice, always end with the disclaimer), strips `<think>` blocks (for reasoning models), runs `guardrails.enforce()`, and returns only the sources actually cited in the final text. |

### 3.4 `guardrails/` — the deterministic safety gate

| File | Purpose |
|---|---|
| `rules.py` | `classify_input(query)` — regex flags for `directive` ("should I buy…", "guarantee(d) return"...) and `risky` (crypto/leverage/margin/F&O, "sell everything", "all-in"...) intent; either forces the safety path. `output_violations(text)` — regex for genuine 2nd-person imperatives only ("you should buy", "invest now"), deliberately narrow so descriptive mentions aren't false-positived. `enforce(text, rewrite=True)` — if violations found, an LLM pass strips the directive language while preserving citations/figures; if still violating after that, a hard-fallback refusal template is used instead; `ensure_disclaimer()` always appends the disclaimer if missing. `DISCLAIMER = "Educational information only, not investment advice."` |

### 3.5 `tools/` — Lane B (live data + pure compute)

| File | Purpose |
|---|---|
| `get_quote.py` | `get_quote(ticker)` — normalizes the ticker to both yfinance (`.NS`) and NSE forms, tries `yfinance` first then `nsepython` as fallback, cached 60s via `tools/cache.py`. Raises `ValueError` (with both sources' failure reasons) on an unresolvable ticker — never guesses a price. |
| `get_index.py` | `get_index(name)` — same pattern for an index/sector/macro series, backed by `data/market_indices.py`'s ticker map. `known_indices()` lists valid names. |
| `cache.py` | `get_or_set(key, producer, ttl=60)` — tiny in-process TTL cache; returns `(value, hit)` so callers can surface a cache-hit badge. |
| `portfolio_calc.py` | `portfolio_calc(allocation, changes=None)` — pure rebalance math, no I/O. Validates a positive total and no negative resulting bucket; returns before/after percentages and amounts, or `{"error": ...}`. |
| `portfolio_summary.py` | `summarize(user)` — reads a user's holdings, prices each via `get_quote`, computes invested/current value, P&L, and sector-weighted mix. A single failed quote is marked `price: null` / `"live price unavailable"` — never guessed — the rest of the summary still computes. |

Full input/output/error-case contracts: `docs/tools.md`.

### 3.6 `mcp_server/` — external tool exposure

| File | Purpose |
|---|---|
| `server.py` | A `FastMCP` server (stdio transport) exposing `get_quote`, `get_index`, `portfolio_summary`, `rebalance`, and `list_users` to *external* MCP clients (Claude Desktop, other agents) — a separate surface from the internal orchestrator, reusing the same underlying tool functions but returning `{"error": ...}` dicts instead of raised exceptions (an external client can't catch a Python exception). `rebalance` here duplicates the orchestrator's baseline-allocation logic (risk-profile midpoint × invested value) since MCP clients don't go through `agent/orchestrator.py`. Run: `python mcp_server/server.py`. |

### 3.7 `obs/` — observability

| File | Purpose |
|---|---|
| `trace.py` | `log_turn(user, query, result)` — appends one compact JSONL record (timestamp, user, query, route, truncated answer, cited doc_ids, full trace dict) to `obs/traces/traces.jsonl` (gitignored). Wrapped in try/except — **logging can never break a response**. `recent_traces(n=30)` reads the tail back, most-recent-first, for the UI's Observability tab. |

### 3.8 `evals/` — quality harness

| File | Purpose |
|---|---|
| `golden.json` | 12 golden Q&A cases, each with `query`, `expected_route`, `must_include` keywords, `expect_citation`, and sometimes `expected_doc_contains` or `expect_abstain`. |
| `harness.py` | `run_case(case)` runs each query through `agent.orchestrator.respond` and scores: route match (the safety route counts as a match for an expected `general_knowledge`), keyword recall, citation presence, retrieval hit (expected doc actually cited), a directive-blacklist check (always on), and abstention correctness when expected. `print_report()` renders a per-case table + aggregate pass rates; writes `evals/results.json`. Always exits 0 — this reports quality, it doesn't gate CI. Run: `python -m evals.harness` (needs the live LLM/embeddings/pgvector stack + an ingested corpus). A commented-out RAGAS hook shows how to add faithfulness/answer-relevancy scoring later without a hard dependency. |

### 3.9 `data/` — reusable data-layer modules + datasets

| File | Purpose |
|---|---|
| `fundamentals.py` | Screener.in (+ yfinance + NSE) fetchers and a large `FundamentalSnapshot` dataclass (valuation, profitability, growth, health, ownership, dividend, price context, plus fields *not* published to the corpus — analyst ratings/targets, governance risk scores — excluded at the ingestion step, not here, so the raw fetch keeps everything but `ingest/build_factsheets.py` filters). `analyse(symbol)` is the main entry point. |
| `market_indices.py` | `BROAD`/`SECTORS`/`MACRO` display-name → yfinance-ticker maps; `fetch_perf(ticker)` computes point-to-point returns over 1M–5Y windows (+3Y/5Y CAGR); `get_index_live(name)` is what `tools/get_index.py` calls for a live level + day change. |
| `news_rss.py` | `get_market_news(n=30, feeds=4)` — merges and de-duplicates headlines from public RSS feeds (ET, MoneyControl, Business Standard, Hindu BL, LiveMint); returns `NewsItem` dataclasses. Used both by `ingest/build_market_news.py` (a corpus doc) and `rag/agentic_retrieve.py`'s closed-corpus news fallback. |
| `reference/risk_profiles.json` | Illustrative equity/debt/gold allocation ranges + a midpoint per risk tolerance — the baseline `_rebalance_answer` and the MCP `rebalance` tool apply to a user's invested value. |
| `reference/education_sources.json` | Manifest for `ingest/build_education_extra.py` (see below). |
| `profiles/users.json`, `profiles/portfolios.csv` | The Lane C seed data — 10 synthetic users / 57 positions. `users.json` is also the **runtime store**: `memory.update_preferences()` writes back to this same file. |

### 3.10 `ingest/` — one-off / periodic corpus generators (not part of the request path)

| File | Purpose |
|---|---|
| `build_factsheets.py` | Generates `corpus/companies/*.md` (one per NIFTY 100 company) + `corpus/nifty100_fundamentals_enriched.csv` from `data/fundamentals.analyse()`. Deliberately **excludes** analyst ratings/price targets/verdicts at this step (the no-directive-advice guardrail applied at the data layer, not just at answer time); missing values are left as `_n/a_`, never fabricated. Also patches a known Screener dividend-yield parsing quirk by overriding with the validated yfinance value. |
| `build_market_snapshots.py` | Generates `corpus/market/{index,sector,macro}_performance.md` from `data/market_indices.fetch_perf()` — sectors are ranked by 1-year return. |
| `build_market_news.py` | Generates a dated `corpus/reports/market_news_<date>.md` from `data/news_rss.get_market_news()`. |
| `build_user_profiles.py` | Generates the 10 synthetic users + 57 positions (`data/profiles/users.json` + `portfolios.csv`), with realistic buy prices drawn from each stock's 52-week range so P&L looks plausible. Seeded (`random.seed(42)`) for reproducibility. |
| `build_education_extra.py` | A scaffold for turning **local** reference files (PDF/md/txt you already have rights to) into `corpus/education/*.md` via a manifest (`data/reference/education_sources.json`). Dry-run by default (prints what it would do; `--write` actually writes); network fetching is opt-in and disabled by default, with a ToS warning — deliberately conservative about corpus provenance. |

### 3.11 `deploy/` — containerized API (an alternative to the Gradio UI)

| File | Purpose |
|---|---|
| `api.py` | A FastAPI wrapper around the same `agent.orchestrator.respond` used by `app.py`. `GET /health`, `GET /users`, `POST /chat {message, user_id?}`. Loads the reranker at startup (`lifespan`) so the first real request isn't slow; serializes request handling behind a lock (reranker + DB are shared, non-reentrant state — fine for an educational, low-concurrency service). Run: `python deploy/api.py` or `uvicorn deploy.api:app`. |
| `Dockerfile` | `python:3.12-slim`, installs `requirements.txt`, **pre-bakes the reranker model into the image's HF cache at build time** (needs network at build, not at runtime — runtime sets `HF_HUB_OFFLINE=1`), exposes 8000. Build from the **project root**: `docker build -f deploy/Dockerfile -t wealthpilot-api .` |

### 3.12 `corpus/` — the RAG corpus (what gets embedded)

| Folder | Count | Notes |
|---|---|---|
| `companies/*.md` | 100 | One NIFTY 100 company per file |
| `funds/*.pdf` | 6 | Real fund/index-methodology PDFs (Nippon/Axis Nifty 100 ETF/fund, methodology docs) |
| `market/*.md` | 3 | Index / sector / macro performance snapshots |
| `education/*.md` | 11 | Concept explainers (index funds, costs, risk, diversification, allocation, risk profiles, speculative assets, plus 4 newer ones: taxation of equities in India, ETF vs. index fund, reading an annual report, market cap & liquidity) |
| `reports/*` | 2 | AMFI monthly note (PDF) + dated market-news digest (md) |
| `*.csv` | 3 | Constituents + fundamentals snapshots (source data, not directly embedded as prose) |

### 3.13 `docs/` — project documentation (read these for deeper detail)

| File | Covers |
|---|---|
| `project-overview.md` | Management-facing data report (corpus inventory, sample Q&A) — **dated 2026-07-10, describes several things as "planned" that are now built**; treat as historical context, not current status (see §11 here instead). |
| `data-architecture.md` | The original three-lane design + query-flow traces — mostly still accurate, written before `update_preference`/MCP/obs/evals existed. |
| `project-plan-and-architecture.md` | The original master plan (phases, roles, risks) — same caveat as above. |
| `workflow.md` | A code-grounded walkthrough of the request path — accurate for the RAG/tool/guardrail flow, written before `update_preference`. |
| `advanced-rag-roadmap.md` | Design notes behind the agentic retrieval strategy. |
| `tools.md` | Full input/output/error-case spec for every tool (Week 2 deliverable). |
| `memory-schema.md` | The user-record schema, the `memory.py` API, and a real write/read round-trip log (Week 2 deliverable). |
| `team.md` | Roles + stack (Week 1 deliverable; solo build). |
| `HANDOVER.md` | This document. |

---

## 4 · The UI (`app.py`)

Gradio `Blocks`, 3 tabs:
- **💬 Chat** — `chat_fn` is a streaming generator: shows "⏳ thinking…", calls `respond(message, user, history=prior)`, then reveals the answer word-by-word. An expandable **🔎 Agent trace** accordion (`_trace_md`) shows route, extracted args, the rewritten query (if coreference kicked in), retrieval strategy/subqueries/news-fallback, guardrail verdict, cache hit, and cited sources. `_badges` renders a compact one-line status (guardrail/route/cache/news-fallback).
- **📊 Portfolio** — `portfolio_view` renders a sector-mix pie + per-holding P&L bar (matplotlib) from `tools.portfolio_summary.summarize()`. Purely descriptive, explicitly captioned "not a recommendation to trade."
- **🔎 Observability** — `load_traces()` renders `obs.trace.recent_traces()` as a markdown table.

`demo.queue()` is called at module scope so streaming works whether launched via `python app.py` or `import app; app.demo.launch(...)` (used by the FastAPI-free Colab notebook path).

---

## 5 · Request lifecycle — worked example

**"How did the FMCG sector perform in the last 6 months?"**

1. `app.chat_fn` → `memory.get_user(uid)` → `agent.orchestrator.respond(query, user, history)`.
2. No prior history reference needed → `rewritten = None`.
3. `classify_input` → clean (no directive/risky flags).
4. `_route()` → one LLM tool-call → `general_knowledge`.
5. `rag.answer(query, user=user)` → not risky → `RAG_AGENTIC` default → `agentic_search`:
   - `_gen_subqueries` produces reformulations (e.g. a terse keyword form, "Nifty FMCG 6M return").
   - Hybrid fuse+rerank per query, merged.
   - A plain top-k pass on the raw query alone tends to favor a company chunk (e.g. `company:ITC`) over the sector table — this is the known failure mode the agentic loop exists to fix.
   - `_grade` (CRAG) judges the top candidates; if the sector table isn't yet surfaced with high confidence, follow-up queries are added and a second pass runs.
   - Result: `market:sector_performance` chunk surfaces, confident.
6. `_format_sources` builds the `[S1]`/`[S2]` context block; main LLM synthesizes an answer citing it, e.g. "Nifty FMCG is down ~10.61% over 6 months... [S1]".
7. `guardrails.enforce()` — no violations, disclaimer appended (already present from the system prompt, so it's a no-op).
8. `_finish()` → `obs.trace.log_turn` appends a JSONL record.
9. UI streams the answer, trace panel shows `route: general_knowledge`, retrieval strategy `agentic`, subqueries used, and the cited source.

---

## 6 · Configuration reference (`.env`)

| Var | Purpose |
|---|---|
| `LLM_PROVIDER` | `ollama` \| `groq` \| `custom` \| `azure` |
| `OLLAMA_*` / `GROQ_*` / `CUSTOM_*` / `AZURE_OPENAI_*`, `OPENAI_AIML_KEY`, `DEPLOYMENT_NAME` | Provider-specific connection details (see `config.py:_provider_config`) |
| `FAST_LLM_PROVIDER` / `FAST_LLM_MODEL` | Optional — route lightweight agentic steps (subquery gen, CRAG grading, coreference rewrite) to a different/cheaper model |
| `EMBED_BASE_URL` / `EMBED_PATH` / `EMBED_MODEL` / `EMBED_DIM` | mxbai (or swapped) embedding endpoint; changing `EMBED_DIM` reshapes `wp_chunks.embedding` on next `rag.ingest` run — no code change needed |
| `PG_DSN` or `PG_HOST`/`PG_PORT`/`PG_DB`/`PG_USER`/`PG_PASSWORD`, `PG_SCHEMA` | Postgres connection |
| `RERANKER_MODEL`, `RAG_CONF_THRESHOLD`, `RAG_KEEP_SCORE` | Cross-encoder model + confidence-gate tuning (different rerankers use different score scales — see the notebook's §7) |
| `RAG_AGENTIC`, `RAG_DECOMPOSE`, `RAG_N_SUBQUERIES`, `RAG_MAX_ITERS`, `RAG_RERANK_POOL`, `RAG_GRADE_POOL`, `RAG_GRADE_SNIPPET`, `RAG_NEWS_FALLBACK`, `RAG_NEWS_N` | Agentic retrieval knobs (`rag/agentic_retrieve.py`) |
| `INSECURE_SSL`, `CA_BUNDLE` / `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` | Corporate SSL-inspection proxy handling |
| `HF_HUB_OFFLINE` | Load the reranker from local HF cache instead of hitting the network |

See `.env.example` for the full annotated template.

---

## 7 · Running it

**Local:**
```
pip install -r requirements.txt
cp .env.example .env        # fill in your provider + PG connection
python -m rag.ingest         # one-time (or after any corpus change)
python smoke_test.py         # sanity check: chat, tool-calling, embeddings, pgvector
python app.py                # Gradio UI at localhost:7860
```

**Colab:** upload `wealthpilot_colab.zip`, follow `WealthPilot_Demo.ipynb` top to bottom
(installs Ollama+Postgres+pgvector, configures `.env` for Groq, ingests, launches with
`share=True`). The notebook also has a full architecture/strategy write-up and a live demo
script (§9) including the Week 2 memory-write proof (§9b).

**Containerized API:** `docker build -f deploy/Dockerfile -t wealthpilot-api .` then
`docker run --env-file .env -p 8000:8000 wealthpilot-api` — `POST /chat` is the same agent,
headless.

**MCP:** `python mcp_server/server.py` — connect any MCP client (Claude Desktop, etc.) for
`get_quote`/`get_index`/`portfolio_summary`/`rebalance`/`list_users`.

**Evals:** `INSECURE_SSL=1 HF_HUB_OFFLINE=1 python -m evals.harness` (needs the live stack +
an ingested corpus) — prints a per-case pass/fail table and writes `evals/results.json`.

---

## 8 · Guardrails — the non-negotiable rules

| Rule | Enforced by |
|---|---|
| No buy/sell/invest-now directive | `guardrails.rules.enforce` (regex + LLM rewrite + hard fallback) — deterministic, not prompt-only |
| Every number cited to a source/tool | `rag/answer.py` system prompt + only-cited-sources-returned logic; tool lanes format deterministically |
| Mandatory educational disclaimer | `ensure_disclaimer()`, always |
| Risky asks reference the user's own risk tolerance | `rag/answer.py` injects the user profile into the system prompt as caution context |
| No sensitive PII | Memory schema is limited to risk tolerance/goals/preferences/holdings; no SSN/PAN/bank fields exist anywhere |
| No fabricated data | Missing values shown as `n/a`/`null`, never guessed (see `get_quote`, `portfolio_summary`, `ingest/build_factsheets.py`) |
| Analyst ratings/price targets/verdicts excluded | Stripped **at ingestion** (`ingest/build_factsheets.py`), not just at answer time |
| Full explainability | `obs.trace.log_turn` — one record per turn |

---

## 9 · Known gaps / not yet done

- **Lane C is file-backed, not Postgres.** `memory.py` reads/writes `data/profiles/users.json` directly. This was a deliberate choice for Week 2 (satisfies "a record can be written and read back correctly" without standing up new infra) — a Postgres `user_profile`/`user_holding` schema was sketched in `docs/data-architecture.md §5` and can back the same `get_user`/`update_preferences` API later without changing any caller.
- **No brokerage/trade execution** — out of scope by design (`rebalance` and `portfolio_calc` are illustrative math only, never executed).
- **Docs `project-overview.md`, `data-architecture.md`, `project-plan-and-architecture.md`, `workflow.md` are stale** relative to current code (dated 2026-07-10/11, before `update_preference`, MCP, `obs/`, `evals/`, and 4 of the education docs existed). This handover doc (and `tools.md`/`memory-schema.md`/`team.md`) reflect current state; treat the others as historical design records.
- **Eval harness has no CI gate** — `evals/harness.py` always exits 0 by design; it's a reporting tool, not a blocking check.
- **`.claude/` is gitignored and excluded from the Colab zip** — it holds local IDE permission state, not project config; nothing to port if you don't use Claude Code.

---

## 10 · A note on secrets

A live Azure OpenAI key was previously found embedded in `.claude/settings.local.json`
(matching `.env`'s `OPENAI_AIML_KEY`). That file is now excluded from both git
(`.gitignore`) and the Colab zip. **Rotate that Azure key** if there's any chance the old
zip was shared anywhere before this fix — don't assume it's still safe to use.

---

## 11 · Status vs. the course plan

### Week 1 — Foundations, RAG & UI ✅ 9/9
Kickoff/roles (`docs/team.md`) · repo+README · system prompt (`rag/answer.py:SYSTEM`) ·
synthetic profiles (`data/profiles/users.json`) · fund/market corpus · ingestion
(`rag/ingest.py`) · retrieval tested · minimal RAG prototype · Gradio chat UI.

### Week 2 — Tools, MCP & Memory ✅ 7/7
Tool specs (`docs/tools.md`) · `portfolio_calc` + `get_quote` implemented and tested ·
MCP round trip (`mcp_server/server.py`) · memory schema + write/read
(`docs/memory-schema.md`) · memory read/write wired into the conversation
(`update_preference` route) · agent-trace panel.

### Week 3 — Guardrails & Caching — built ahead of schedule
Guardrail layer (`guardrails/rules.py`), quote/index caching with a cache-hit badge
(`tools/cache.py`), badges surfaced in the UI.

### Week 4 — Observability, Evals & Demo — partially built ahead of schedule
Trace logging (`obs/trace.py` + Observability tab) and an eval harness
(`evals/harness.py` + `golden.json`) exist. Not yet done: a baseline-vs-error-analysis
before/after report, a dedicated metrics dashboard beyond the raw trace table, and a
rehearsed demo video — these remain genuine Week 4 work.
