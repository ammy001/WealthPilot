# WealthPilot — Detailed System Workflow

_How the system processes a request, end to end, grounded in the actual code.
Version 1.0 · 2026-07-11._

Legend: `file.py:function()` references real code. "Lane A" = RAG corpus,
"Lane B" = live tools, "Lane C" = user memory.

---

## 0. Component map (files → responsibility)

```
app.py                     Gradio UI, session, TLS/offline startup
agent/orchestrator.py      respond(): route + dispatch + assemble trace
guardrails/rules.py        classify_input(), enforce()  (deterministic safety gate)
rag/answer.py              answer(): cited RAG synthesis + abstain
rag/retrieve.py            search(): hybrid retrieve + rerank + confidence gate
rag/chunk.py               build_all(): corpus -> chunks (offline)
rag/ingest.py              main(): embed + load pgvector (offline)
embeddings.py              embed_one()/embed(): mxbai vectors
tools/get_quote.py         get_quote(): live stock price (cached)
tools/get_index.py         get_index(): live index/sector level (cached)
tools/portfolio_calc.py    portfolio_calc(): pure rebalance math
tools/portfolio_summary.py summarize(): holdings x live quotes -> value/P&L/sector
tools/cache.py             get_or_set(): TTL cache (drives cache badge)
memory.py                  get_user(): user profile + holdings (Lane C)
llm.py                     chat(): provider-switch LLM client (deepseek/groq/ollama)
db.py                      connect(): pgvector (schema hcmp_aiml)
config.py                  env-driven config
```

---

## 1. Startup / initialization workflow (`app.py`)

Runs once when the app launches, **before any network client is built**:

1. `os.environ.setdefault("INSECURE_SSL","1")` and `HF_HUB_OFFLINE="1"`.
2. `insecure_ssl.maybe_disable_tls_verification()` — monkeypatches httpx / requests /
   curl_cffi to tolerate the corporate SSL-inspection proxy (covers the LLM SDK and
   yfinance). *(Production hardening: replace with a real CA bundle.)*
3. Import `gradio`, `memory`, `agent.orchestrator`.
4. `memory.list_users()` → populate the user dropdown (10 synthetic users).
5. Build `gr.Blocks`: chatbot, textbox, user dropdown, **agent-trace** accordion,
   **badges** markdown, example prompts.
6. `demo.launch(server_port=7860)` — serves the UI.

The reranker model (`bge-reranker-v2-m3`) is **lazy-loaded** on the first RAG query
(`rag/retrieve.py:_get_reranker()`), not at startup.

---

## 2. Ingestion workflow (offline, `python -m rag.ingest`)

Run once (and whenever the corpus changes) to build the searchable store.

```
rag/chunk.py:build_all()
  ├─ markdown docs (companies/education/market/reports)
  │    split on '## ' sections; prepend "Company <name> — <section>" (entity tagging)
  │    → chunk dicts {doc_id, doc_type, entity, title, section, text, source, as_of, locator}
  └─ PDF docs (funds/reports)
       pypdf extract per page → ~1500-char windows with page-range locators
       (big reference PDFs capped, e.g. methodology → 40 pp)
  ⇒ 1,613 chunks

rag/ingest.py:main()
  1. embeddings.embed(texts, workers=3)        # mxbai, retry+backoff (endpoint 502s under load)
  2. db.connect()                              # DSN + SET search_path hcmp_aiml
  3. CREATE TABLE wp_chunks (... embedding vector(1024) ...)   # namespaced (shared schema)
  4. TRUNCATE wp_chunks; execute_batch INSERT (embedding as %s::vector)
  5. CREATE INDEX: HNSW (vector_cosine_ops), GIN (to_tsvector), entity, doc_type
  ⇒ 1,613 chunks / 118 docs loaded
```

Output: `hcmp_aiml.wp_chunks` — the retrieval store.

---

## 3. Runtime query workflow (the main path)

### 3.1 Top-level sequence

```
User types in UI
   │
app.py:chat_fn(message, history, user_label)
   │   user = memory.get_user(<uid>)                     # Lane C
   ▼
agent/orchestrator.py:respond(query, user)
   │
   ├─ (A) guardrails.classify_input(query)               # input flags
   │        directive? risky?
   │
   ├─ (B) IF directive OR risky  ─────────────► SAFETY PATH → rag.answer() (§3.4)
   │
   ├─ (C) ELSE _route(query)                              # forced tool_choice router (§3.2)
   │        └─ picks ONE of: get_quote | get_index | portfolio_summary
   │                          | rebalance | general_knowledge
   │
   ├─ (D) dispatch to the chosen lane (§3.3)
   │
   ├─ (E) guardrails.enforce(text)                        # output gate (§3.5)
   │
   └─ (F) build trace + badges  ──────────────► back to chat_fn → UI
```

### 3.2 Routing (`orchestrator._route`) — the agentic decision

deepseek won't auto-call tools, so routing = **one forced call**:

1. `llm.chat(messages=[router_sys, query], tools=ROUTER_TOOLS, tool_choice="required")`.
2. The model MUST return exactly one `tool_call` → this is simultaneously the **route
   decision** and the **argument extraction** (e.g. ticker="RELIANCE", name="NIFTY 50").
3. `json.loads(tool_call.arguments)` → `(route, args)`.
4. Fallback: no tool_call → `("general_knowledge", {query})`.

`ROUTER_TOOLS` = get_quote, get_index, portfolio_summary, rebalance, general_knowledge
(the last is the catch-all for concepts/companies/education/opinions).

### 3.3 Dispatch — the five lanes

**get_quote** (Lane B): `tools/get_quote.py:get_quote(ticker)`
```
normalize ticker (RELIANCE → RELIANCE.NS / RELIANCE)
cache.get_or_set("quote:<sym>", ttl=60)
  ├─ miss → yfinance fast_info.last_price  (fallback: NSE nsepython)  → cache_hit=False
  └─ hit  → cached value                                             → cache_hit=True
→ _fmt_quote(): "RELIANCE is trading at ₹1,307.8 (delayed; yfinance, as of …). Live fetch."
```

**get_index** (Lane B): `tools/get_index.py:get_index(name)` — same cache pattern over
`data/market_indices.get_index_live()` → `_fmt_index()`: "NIFTY 50 is at 24,206.9 (▲ +1.02%)".

**portfolio_summary** (Lane B+C): `tools/portfolio_summary.py:summarize(user)`
```
for each holding: iv = qty×buy_price;  get_quote(symbol) → cv = qty×price
aggregate: invested, current_value, pnl, pnl_pct, sector_pct (by value)
a failed quote → "live price unavailable" (never guessed)
→ _fmt_portfolio(): table + "Note: <sector> is X% — concentrated" if ≥40%
```

**rebalance** (Lane B pure + Lane C): `orchestrator._rebalance_answer(args, user)`
```
baseline = risk_profiles.json[user.risk].midpoint  × total_invested   # illustrative
tools/portfolio_calc.py:portfolio_calc(baseline, {from:-amt, to:+amt})
  validate (no negative, positive total) → before_pct / after_pct
→ "moving ₹5,000 from bonds to equities: 55/37/8 → 56/36/8 … illustrative, not a suggestion"
```

**general_knowledge** (Lane A): → `rag/answer.py:answer(query, user)` (§3.4).

### 3.4 RAG sub-workflow (`rag/answer.py:answer` → `rag/retrieve.py:search`)

```
answer(query, user):
  flags = classify_input(query)
  IF risky/directive → SAFETY PATH: search(filters=doc_type='education'), never abstain
  ELSE               → search(query)                         # §retrieval below
  IF not confident and not risky → return ABSTAIN            # "I don't have that…"

  retrieval  rag/retrieve.py:search(query, k=6):
    qvec = embeddings.embed_one(query)                       # mxbai 1024-d
    vec  = _vector_search : ORDER BY embedding <=> qvec::vector  (HNSW cosine)  top 20
    kw   = _keyword_search: websearch_to_tsquery @@ tsvector, ts_rank            top 20
    fused = _rrf(vec, kw)          # Reciprocal Rank Fusion  score=Σ 1/(60+rank)
    rerank: bge-reranker-v2-m3.predict[(query, chunk) …top30] → sort desc
    confident = top_score ≥ 0.02                             # confidence gate
    → results (each: doc_id, section, chunk_text, source, as_of, score)

  synthesis:
    context = _format_sources(results)   # [S1] doc_id — section (as of …)\n<text>
    system  = SYSTEM (+caution if risky) (+user profile if provided)
    llm.chat(system, "Question:…\nSOURCES:…", max_tokens=2048)
    text = strip <think> blocks from content
  guardrail: enforce(text)                                   # §3.5
  return {answer, sources(cited), flags, guardrail_*}
```

Grounding rules baked into `SYSTEM`: answer ONLY from SOURCES; cite `[S#]`; no directives;
no invented numbers; always end with the disclaimer.

### 3.5 Output guardrail (`guardrails/rules.py:enforce`) — the hard gate

```
enforce(text):
  violations = output_violations(text)          # regex: "you should buy/sell", "invest now", …
  IF violations and rewrite:
      text = _rewrite_safe(text)                 # LLM pass strips directive, keeps facts+citations
      violations = output_violations(text)       # re-check
  IF still violations:
      blocked = True; text = safe refusal template
  text = ensure_disclaimer(text)                 # inject if missing
  return {text, blocked, violations}
```

Patterns target genuine imperatives only, so educational mentions ("selling everything is
risky") are not false-positived.

### 3.6 Trace + badges assembly (`orchestrator.respond` → `app.chat_fn`)

`respond` returns `{answer, route, sources, trace}` where
`trace = {flags, route, args, cache_hit, guardrail:{blocked,violations}}`.
`app._badges()` → "🛡️ Guardrail: clean · Route: `get_index` · 🐢 Cache: miss".
`app._trace_md()` → the expandable explainability panel (route, args, flags, guardrail, cited sources).

---

## 4. Decision flow (branching)

```
                 ┌─────────────────────────────┐
                 │ classify_input(query)        │
                 └───────────────┬─────────────┘
             directive/risky?    │
              ┌── yes ───────────┤── no ──┐
              ▼                            ▼
   SAFETY PATH: rag.answer            _route(query)  (forced tool_choice)
   (education docs, never                    │
    abstain, ref user risk)   ┌──────────────┼───────────────┬────────────┬───────────────┐
              │               ▼              ▼               ▼            ▼               ▼
              │           get_quote      get_index    portfolio_summary rebalance   general_knowledge
              │               │              │               │            │               │
              │          live price     live level     holdings×quotes  calc math      rag.answer
              │               └──────────────┴───────┬───────┴────────────┘               │
              │                                       ▼                                    ▼
              └──────────────────────────────► enforce() (output guardrail) ◄──────────────┘
                                                      ▼
                                              answer + trace + badges
```

---

## 5. Worked examples (real traces)

**E1 — "What's the current price of Reliance?"**
classify → clean → `_route` → `get_quote(ticker="RELIANCE")` → cache miss → yfinance
→ `_fmt_quote` → enforce (disclaimer) →
> "RELIANCE is trading at ₹1,307.8 INR (delayed; source yfinance, as of 2026-07-11T09:45Z). Live fetch. — Educational information only, not investment advice."
Badges: Guardrail clean · Route get_quote · Cache miss.

**E2 — "How is my portfolio doing?" (user U001 Marcus Chen)**
classify → clean → `_route` → `portfolio_summary` → `summarize(user)` → 5× `get_quote` →
> Invested ₹481,570 · Current ₹560,737 · **P&L +16.4%**; DIVISLAB +33.3%, ETERNAL +42.2% …;
> Financial Services 28%, IT 22% …
Descriptive only; no trade suggestion.

**E3 — "How has the IT sector performed this year?"**
classify → clean → `_route` → `general_knowledge` → `rag.answer` → `search`:
vector alone favoured `company:ITC`; **keyword caught "sector"**, RRF+rerank promoted
`market:sector_performance` (top) → grounded answer citing the sector table.

**E4 — "Good low-cost index fund for a moderate-risk investor?"**
`general_knowledge` → `search` → education (costs, index-funds, risk-profiles) + Axis Nifty100
fund doc → synthesis cites them → notes index fund is all-equity; a moderate profile is
~50–60% equity. Disclaimer appended.

**E5 — "Should I sell everything and buy Bitcoin?" (guardrail showcase)**
classify → **directive + risky** → SAFETY PATH → `rag.answer` with education filter + caution +
user profile → answer explains concentration risk, crypto 50–80% drawdowns, **references the
user's 5% crypto cap**, "the decision is yours" → enforce passes (no imperative) → disclaimer.

**E6 — "What's the weather in Mumbai?" (out of scope)**
`general_knowledge` → `search` → top rerank score 0.000 < gate → **ABSTAIN**:
> "I don't have information on that in my sources yet…"

---

## 6. Data flow across lanes (per response)

```
Lane A (RAG):   wp_chunks (pgvector)  ──embed(query)──►  cited chunks ──►  synthesis
Lane B (tools): yfinance/NSE (cached) ──get_quote/index──►  fresh JSON ──►  deterministic format
Lane C (memory): users.json (→ Postgres later) ──get_user──►  profile/holdings ──►  personalise
                                     ▼
                            OUTPUT GUARDRAIL → answer + trace_id events
```

A fact never crosses lanes: prices come only from tools, narrative only from cited chunks,
personal data only from memory.

---

## 7. Error & edge handling

| Situation | Handling |
|---|---|
| Retrieval too weak (off-topic) | Confidence gate → ABSTAIN |
| Directive request | Input flag → SAFETY PATH (educate, never instruct) |
| Directive leaks into output | `enforce` rewrite → hard-fallback template |
| Live quote fails | multi-source (yfinance→NSE); else "live price unavailable" (no guess) |
| Embedding endpoint 502 under load | retry+backoff, 3 workers |
| Unknown ticker/index | tool raises → friendly "couldn't fetch" message |
| Corporate TLS | startup TLS handling (INSECURE_SSL / CA bundle) |
| Reasoning model tool-calling | forced `tool_choice="required"` |

---

## 8. Sequence diagram — a tool query

```
UI → chat_fn → respond → classify_input        (clean)
                       → _route  ──llm.chat(tools, required)──► deepseek → tool_call
                       → get_quote ──cache──► yfinance ──► price JSON
                       → _fmt_quote
                       → enforce (disclaimer)
             ← {answer, trace}
UI ← chatbot + trace panel + badges
```

## 9. Sequence diagram — a knowledge query

```
UI → chat_fn → respond → classify_input (clean) → _route → general_knowledge
                       → rag.answer → search:
                              embed_one(query) → mxbai vector
                              vector + keyword search (pgvector)
                              RRF fuse → rerank (bge) → confidence gate
                       → llm.chat(SYSTEM+context) → grounded text (cite [S#])
                       → enforce → disclaimer
             ← {answer, sources, trace}
UI ← answer + cited sources in trace panel
```
```
```
