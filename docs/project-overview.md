# WealthPilot — Project Overview & Data Report
_Prepared for management review · Data as of 2026-07-10_

---

## 1. Executive summary

**WealthPilot** is an **educational, conversational finance assistant** for the Indian
equity market (NIFTY 100 universe). A user chats in natural language; the assistant
answers with **grounded, cited, non-directive** information — it explains, contextualises,
and personalises, but **never issues buy/sell/invest-now instructions** and **never
fabricates numbers**.

It combines three capabilities:
- **RAG** (Retrieval-Augmented Generation) over a curated corpus of company profiles,
  fund documents, market data, and financial-education material;
- **Live tools** for real-time quotes, index levels, and portfolio math;
- **Cross-session memory** of each user's risk profile and stock holdings.

Every answer is traceable to a source document or a tool output, logged for full
explainability. The system is designed around hard **guardrails** so it stays an
*educational* assistant, not a financial adviser.

---

## 2. Project purpose

| Goal | Description |
|---|---|
| **Educate, not advise** | Help retail users *understand* investing (funds, risk, diversification, valuation) instead of pushing recommendations. |
| **Grounded answers** | Eliminate LLM hallucination by grounding every quantitative claim in a retrieved document or a live tool; cite the source. |
| **Personalisation with memory** | Remember a user's stated risk tolerance, goals, and stock portfolio across sessions and tailor explanations. |
| **Safety & compliance** | Enforce no-directive-advice, mandatory disclaimers, no sensitive-PII collection, and full audit traceability. |
| **Explainability** | Show, for every response, which documents and tools produced it (regulatory-friendly). |

**Reference persona — "Marcus Chen":** a 34-year-old moderate-risk investor who wants
transparent, tailored explanations with memory across sessions — not a generic robo-adviser.

---

## 3. Project scope

### In scope
- **Universe:** NIFTY 100 stocks (India's 100 largest listed companies).
- **Asset focus:** **individual equities** (a user's portfolio holds stocks).
- **Education focus:** **index funds** and core investing concepts.
- **Capabilities:** RAG Q&A, live stock/index quotes, portfolio rebalance math, portfolio
  summarisation, cross-session memory, guardrails, observability, evaluation.
- **Market:** India (INR); data from free/public sources (delayed).

### Out of scope
- Mutual funds beyond index-fund *education* (no debt/gold/ELSS fund advice).
- Live order placement / trading / brokerage integration.
- Directive investment advice, price predictions, buy/sell signals.
- Technical-analysis signals (RSI/MACD), sentiment scoring, derivatives/options.
- Collection of sensitive PII (PAN, bank/demat numbers, passwords).

### Guiding constraints
- **Descriptive, not directive** — states facts, never a verdict.
- **No fabricated figures** — cite or abstain.
- **Delayed, educational-use data only** — no redistribution.

---

## 4. Data — detailed inventory

Total corpus ≈ **6 MB**, **~120 documents + 3 datasets**. Three functional lanes:
**(A) RAG corpus**, **(B) live tool data**, **(C) user memory**.

### 4.1 Company fact sheets — 100 documents `corpus/companies/<SYMBOL>.md`
One profile per NIFTY 100 company, auto-generated then rendered to markdown.
- **Sources:** Screener.in API (fundamentals), Yahoo Finance (`yfinance`: price/returns/identity),
  NSE (shareholding, corporate announcements).
- **~30 fields per company**, grouped:

| Section | Fields |
|---|---|
| Header | Company name, symbol, sector, industry, market-cap class, as-of date, sources |
| About | Full business description (segments, products, HQ, history) |
| Company | HQ city/country, employees, website |
| Valuation | P/E, P/B, EV/EBITDA, Price/Sales, Forward P/E |
| Profitability | ROE, ROCE, Net margin, Operating margin, EBITDA margin |
| Growth | Sales growth, Profit growth |
| Financial health | Debt/Equity, Current ratio, Interest coverage, FCF, Total cash, Total debt |
| Ownership | Promoter %, Institutional (FII+DII) %, Pledged % |
| Dividend | Dividend yield |
| Price context | Market cap, 52-week high/low, % from 52w high, 50/200-day avg, Beta |
| Stock returns | 1Y / 3Y / 5Y price return |
| Liquidity & float | Free-float %, Shares outstanding |
| Additional valuation | EPS (TTM/forward), Book value/share, PEG, ROA, Revenue/share |
| Quarterly performance | Last 4 quarters revenue & profit |
| Recent announcements | Latest 5 NSE filings |

- **Excluded by design** (guardrail): analyst buy/sell ratings, price targets, verdict/score.
- **Data quality:** 100/100 generated successfully; complete; correctly mapped (including
  post-demerger tickers — TMCV/TMPV = Tata Motors CV/PV, ENRIN = Siemens Energy).
- _Full real sample in §7.1._

### 4.2 Structured fundamentals — 3 CSVs `corpus/*.csv`
- `nifty100_constituents.csv` — the universe: Company Name, Industry, Symbol, Series, ISIN (100 rows; NSE official).
- `nifty100_fundamentals.csv` — basic yfinance snapshot (price, m-cap, P/E, P/B, div yield, 52w, beta).
- `nifty100_fundamentals_enriched.csv` — Screener+yfinance+NSE (the fuller set).

### 4.3 Fund fact sheets — 6 PDFs `corpus/funds/`
Real, public documents on the Nifty 100 index and index funds tracking it:

| File | Source | Content |
|---|---|---|
| `nse_nifty100_index_factsheet.pdf` | NSE / niftyindices | Index methodology & stats |
| `nippon_india_etf_nifty100.pdf` | Nippon India MF | Real ETF: TER, tracking error, returns |
| `axis_nifty100_index_fund.pdf` | Axis MF | Real index fund: NAV, cap split |
| `nifty_index_methodology.pdf` | NSE Indices | How Nifty indices are constructed (328 pp) |
| `nifty100_equalweight_factsheet.pdf` | niftyindices | Equal-weight variant |
| `nifty100_quality30_factsheet.pdf` | niftyindices | Quality-factor variant |

### 4.4 Market / sector / macro data — 3 docs `corpus/market/`
Computed from Yahoo Finance history; returns over 1M/3M/6M/1Y/3Y/5Y (+CAGR).
- `index_performance.md` — NIFTY 50, NIFTY 100, Midcap 50, Sensex.
- `sector_performance.md` — 9 Nifty sector indices, ranked by 1Y return.
- `macro_commodities.md` — India VIX, USD/INR, Gold, Crude WTI, Brent.

### 4.5 Market reports `corpus/reports/`
- `amfi_monthly_note_mar2026.pdf` — AMFI monthly note: industry AUM, flows, category returns (19 pp).
- `market_news_<date>.md` — 30 aggregated RSS headlines (ET, MoneyControl, Business Standard).

### 4.6 Educational content — 7 docs `corpus/education/`
Authored, India-context, descriptive/non-directive concept explainers:
1. Index funds & passive investing 2. Costs & expense ratio 3. Risk & return
4. Diversification 5. Asset allocation & rebalancing 6. Risk profiles
(conservative/moderate/aggressive) 7. Equities vs speculative assets (incl. crypto).

### 4.7 Reference data `data/reference/risk_profiles.json`
Machine-readable illustrative allocation ranges per risk profile (for grounding tool/agent logic).

### 4.8 Synthetic user data — Lane C `data/profiles/`
- `users.json` — **10 users**: risk tolerance, goals, crypto cap, monthly investment, nested holdings.
- `portfolios.csv` — flat holdings table (**57 positions**): user, symbol, sector, **buy_date,
  quantity, buy_price**, invested_value.
- Holdings are NIFTY 100 **stocks**; buy prices drawn realistically from each stock's 52-week
  range so P&L is plausible. **Fully synthetic — no real PII.** U001 = "Marcus Chen".

### 4.9 Live tool data — Lane B (not stored; fetched on demand, cached 60s)
- `get_quote(ticker)` → current stock price (yfinance primary, NSE fallback).
- `get_index(name)` → current index/sector/macro level.
- `portfolio_calc()` → deterministic rebalance math (no external data).

### 4.10 Data volume at a glance
| Category | Count | Format |
|---|---|---|
| Company fact sheets | 100 | markdown |
| Fund / methodology PDFs | 6 | PDF |
| Market/sector/macro docs | 3 | markdown |
| Market reports | 2 | PDF + md |
| Education docs | 7 | markdown |
| Structured datasets | 3 CSV + 2 JSON | CSV/JSON |
| Synthetic users / positions | 10 / 57 | JSON/CSV |

---

## 5. Data architecture (summary)

Three isolated lanes feed an LLM orchestrator; a fact never crosses lanes.
_(Full detail in `docs/data-architecture.md`.)_

```
USER → INPUT GUARDRAIL → ORCHESTRATOR (LLM tool-calling)
        ├── Lane A: RAG corpus (pgvector + mxbai embeddings) → cited chunks
        ├── Lane B: live tools (get_quote / get_index / portfolio_calc) → fresh JSON
        └── Lane C: user memory (profile + holdings)          → user record
     → SYNTHESIS (grounded only in gathered context)
     → OUTPUT GUARDRAIL (block directives, enforce citations, inject disclaimer)
     → OBSERVABILITY (one trace_id per response)
```

**Pipeline status:** data acquired & normalised ✅ · embedding into pgvector, hybrid
retrieval + rerank + confidence gate, tools/agent, UI, evals → in build plan.

---

## 6. Sample user questions & how they are answered

Grounded example answers (the assistant always cites and disclaims):

**Q1. "What's a good low-cost index fund for a moderate-risk investor?"**
_Lanes: RAG (education + funds)._ Retrieves cost/TER + risk-profile + fund docs →
"A 'low-cost' fund mainly means a low expense ratio and low tracking error [edu/costs].
E.g. the Nippon India Nifty 100 ETF reports a TER of X% [fund doc, Jun-2026]. Note an
index fund is fully equity; a *moderate* profile is often ~50–60% equity with the rest
in debt/gold [edu/risk-profiles]. Educational only — not a recommendation."

**Q2. "What's the current price of Reliance?"**
_Lane: tool._ `get_quote("RELIANCE")` → "RELIANCE is ₹1,301.70 (delayed; source yfinance;
as of 2026-07-10). " (Repeat within 60s → cache-hit badge.)

**Q3. "Remind me what my risk tolerance is."**
_Lane: memory._ → "You told me your risk tolerance is **moderate**, with a 5% cap on crypto."

**Q4. "How is my portfolio doing?"**
_Lanes: memory + tool._ Reads holdings, fetches live prices, computes value/P&L/sector mix →
"Your 5 holdings: invested ₹4.82L, now ₹X (▲/▼ Y%). Largest: HCLTECH. Sector-heavy in IT/
Financials. " (Describes; does not tell you to trade.)

**Q5. "If I move ₹5,000 from bonds to equities, what's my new allocation?"**
_Lane: compute._ `portfolio_calc` → "Your mix shifts from 60/35/5 to ~62/33/5
(equity/debt/gold). Rebalancing realigns to a target [edu/allocation]. Educational only."

**Q6. "Should I sell everything and buy Bitcoin?"** _(guardrail)_
_Lanes: memory + education._ → "I can't tell you to buy or sell. Context: concentrating
everything in one volatile asset removes diversification [edu/diversification]; crypto has
seen 50–80% drawdowns [edu/speculation]. You've set a moderate tolerance with a 5% crypto
cap [your profile] — a full switch is far outside that. The decision is yours."

**Q7. "Tell me about TCS."**
_Lane: company RAG._ → business summary + descriptive metrics, each cited to the fact sheet
(P/E 15.3x, ROE 45.9%, 1Y return −36.8%, as of 2026-07-10). No verdict.

**Q8. "What was the Nifty 100's return last year?"**
_Lane: RAG (market)._ → "As of 2026-07-10, the Nifty 100's 1-year return was −3.44%
[market/index_performance]. Over 5 years: +62.6%."

**Q9. "How has the IT sector done this year?"**
_Lane: RAG (market)._ → "Nifty IT is down ~28% over 1 year — the weakest sector; Metal and
Pharma led [market/sector_performance]. Descriptive only."

**Q10. "What does expense ratio mean?"**
_Lane: RAG (education)._ → plain-language explanation + why low cost compounds [edu/costs].

**Q11. "Which stock will give me the highest returns?"** _(guardrail)_
→ Declines to predict/recommend; explains no one can guarantee returns [edu/risk-return];
offers to show descriptive metrics instead.

**Q12. "Compare TCS and Infosys."**
_Lane: company RAG (two entities)._ → side-by-side descriptive metrics from both fact sheets,
each cited; no "better buy" verdict.

**Q13. "What are my holdings?"**
_Lane: memory._ → lists portfolio with buy date/price/quantity from the user record.

**Q14. "Is now a good time to invest?"** _(guardrail)_
→ No market-timing call; explains time-in-market vs timing [edu/risk-return], shows current
index context [market], defers the decision to the user.

---

## 7. Sample data (real records)

### 7.1 Company fact sheet — `corpus/companies/TCS.md` (excerpt)
```markdown
# Tata Consultancy Services Limited (TCS)
**Sector:** Technology · **Industry:** IT Services · **Class:** Large-cap
**As of:** 2026-07-10 · **Sources:** Screener.in, Yahoo Finance, NSE (delayed, educational use only)

## About
Tata Consultancy Services Limited provides IT and IT-enabled services … founded in 1968,
based in Mumbai, a subsidiary of Tata Sons Private Limited.  [full description in file]

## Company
- HQ: Mumbai, India   - Employees: 584,519   - Website: https://www.tcs.com
## Valuation
- P/E: 15.32x · P/B: 7x · EV/EBITDA: 10.12x · Price/Sales: 2.81x · Forward P/E: 12.67x
## Profitability
- ROE: 45.9% · ROCE: 54.9% · Net margin: 18.4% · Operating margin: 25.3% · EBITDA margin: 26.4%
## Growth
- Sales growth: 9.6% · Profit growth: 12.2%
## Financial health
- Debt/Equity: 0.1x · Current ratio: 2.23x · Interest coverage: 54.4x · FCF: 47,948 cr
## Ownership
- Promoter: 71.77% · Institutional (FII+DII): 17.6% · Pledged: 0%
## Price context
- Market cap: 750,789 cr · 52w high: 3,399 · 52w low: 1,976.8 · Beta: 0.24
## Dividend
- Dividend yield: 6.03% (Yahoo Finance)
## Stock price returns
- 1Y: -36.79% · 3Y: -29.68% · 5Y: -25.61%
## Liquidity & float
- Free float: 28.2% · Shares outstanding: 3,618,087,518
## Additional valuation
- EPS (TTM): 135.47 · EPS (fwd): 163.81 · Book value/share: 296.4 · PEG: 2.23x · ROA: 24.44%
## Quarterly performance (most recent first)
- 2026-06-30: revenue ₹72,275 cr, profit ₹13,349 cr
- 2026-03-31: revenue ₹70,698 cr, profit ₹13,718 cr  … (4 quarters)
## Recent announcements
- 09-Jul-2026: financial results, dividend payment date, press release … (5 items)
> Educational information only. Not investment advice.
```

### 7.2 Synthetic user + portfolio — `data/profiles/`
`users.json` (record):
```json
{
  "user_id": "U001", "name": "Marcus Chen", "age": 34,
  "risk_tolerance": "moderate", "goals": ["retirement", "house down-payment"],
  "preferences": {"crypto_cap_pct": 5, "base_currency": "INR"},
  "monthly_investment_inr": 60000,
  "holdings": [
    {"symbol": "HCLTECH", "sector": "Information Technology",
     "buy_date": "2023-03-03", "quantity": 106, "buy_price": 959.54}
  ]
}
```
`portfolios.csv` (Marcus Chen):
```
user_id,user_name,risk_tolerance,symbol,sector,buy_date,quantity,buy_price,invested_value
U001,Marcus Chen,moderate,HCLTECH,Information Technology,2023-03-03,106,959.54,101711.24
U001,Marcus Chen,moderate,BPCL,Oil Gas & Consumable Fuels,2024-07-23,375,285.57,107088.75
U001,Marcus Chen,moderate,UNIONBANK,Financial Services,2026-01-21,953,161.23,153652.19
U001,Marcus Chen,moderate,DIVISLAB,Healthcare,2026-01-21,11,5127.23,56399.53
U001,Marcus Chen,moderate,ETERNAL,Consumer Services,2026-05-17,308,203.63,62718.04
```

### 7.3 Market performance — `corpus/market/index_performance.md`
```
| Instrument | Level | 1M | 3M | 6M | 1Y | 3Y | 5Y |
| NIFTY 50   | 24,194.75 | +4.22% | +0.82% | -7.46% | -5.27% | +29.00% | +54.20% |
| NIFTY 100  | 25,238.95 | +4.29% | +2.32% | -5.43% | -3.45% | +35.26% | +62.60% |
| Sensex     | 77,475.98 | +4.72% | -0.11% | -9.05% | -7.43% | +23.52% | +49.18% |
```

### 7.4 Risk-profile reference — `data/reference/risk_profiles.json`
```json
"moderate": { "summary": "Balances growth and stability…",
  "equity_pct": [50,60], "debt_pct": [30,40], "gold_cash_pct": [5,10],
  "midpoint": {"equity":55,"debt":37,"gold_cash":8}, "speculative_cap_pct": 5 }
```

### 7.5 Live tool output — `get_quote("RELIANCE")`
```json
{ "ticker": "RELIANCE", "price": 1301.70, "currency": "INR",
  "timestamp": "2026-07-10T07:23:17Z", "source": "yfinance", "cache_hit": false }
```

---

## 8. Project code structure

```
wealthpilot/
├── README.md, requirements.txt, .env.example, .gitignore
│
├── config.py            # env-driven config; LLM provider switch (ollama|groq|custom)
├── llm.py               # provider-switching chat client
├── embeddings.py        # mxbai embeddings via Ollama
├── db.py                # Postgres / pgvector connection
├── insecure_ssl.py      # corporate-proxy TLS handling for data pulls
├── smoke_test.py        # verifies LLM tool-calling + embeddings + pgvector
│
├── data/                # DATA LAYER (reusable modules + datasets)
│   ├── fundamentals.py      # Screener.in + yfinance + NSE company fundamentals
│   ├── market_indices.py    # index/sector/macro ticker maps + returns
│   ├── news_rss.py          # free RSS market-news fetcher
│   ├── reference/risk_profiles.json
│   └── profiles/            # users.json, portfolios.csv (synthetic)
│
├── ingest/              # DATA PIPELINE (generators)
│   ├── build_factsheets.py       # → corpus/companies/*.md + enriched CSV
│   ├── build_market_snapshots.py # → corpus/market/*.md
│   ├── build_market_news.py      # → corpus/reports/market_news_*.md
│   └── build_user_profiles.py    # → data/profiles/*
│
├── corpus/              # RAG CORPUS (what gets embedded)
│   ├── companies/*.md   (100)   ├── funds/*.pdf (6)
│   ├── market/*.md      (3)     ├── reports/*   (2)
│   ├── education/*.md   (7)     ├── *.csv       (3, source data)
│   └── sources.md               # provenance ledger
│
├── tools/               # LIVE TOOLS (Lane B)
│   ├── get_quote.py     # live stock price (yfinance→NSE, cached)
│   ├── get_index.py     # live index/sector/macro level (cached)
│   └── cache.py         # TTL cache (drives cache-hit badge)
│
└── docs/
    ├── project-overview.md    # this document
    └── data-architecture.md   # detailed architecture & query flow
```

**Build plan (not yet implemented):** RAG ingestion into pgvector (chunk + embed +
metadata), hybrid retrieval + rerank + confidence gate, agent orchestrator + MCP tool
exposure, `portfolio_calc` + portfolio-summarizer agent, guardrail layer, Gradio UI,
observability dashboard, evaluation harness.

---

## 9. Guardrails & compliance

| Rule | Enforcement |
|---|---|
| No buy/sell/invest-now directive | Deterministic output check + system prompt |
| Every figure cited to a source/tool | Synthesis rule + uncited-number check |
| Mandatory educational disclaimer | Auto-injected on every answer |
| Risky asks reference user's risk tolerance | Orchestrator pulls memory + caution language |
| No sensitive PII collected | Memory limited to profile/preferences |
| Full explainability | Per-response trace_id logs retrievals, tools, guardrail events |
| No fabricated data | Missing values shown as "n/a"; directive/opinion fields excluded at ingestion |

---

## 10. Technology stack

- **LLM:** switchable via env — Ollama (llama3.3), Groq, or custom OpenAI-compatible endpoint.
- **Embeddings:** mxbai-embed-large (1024-d).
- **Vector store + memory:** PostgreSQL + pgvector.
- **Tool transport:** MCP. **UI:** Gradio.
- **Data sources (all free/public, delayed):** NSE, Yahoo Finance, Screener.in, AMFI,
  niftyindices, RSS (ET/MoneyControl/Business Standard).
- **Language:** Python 3.11+.

---

## 11. Status & roadmap

| Phase | Status |
|---|---|
| Data acquisition & normalisation | ✅ Complete (this report) |
| RAG ingestion (chunk + embed → pgvector) | ⏭ Next |
| Retrieval (hybrid + rerank + confidence gate) | Planned |
| Tools + MCP + agent orchestrator | Partial (quote/index built) |
| Memory store (cross-session) | Seed data ready; store pending |
| Guardrail layer | Designed; pending |
| Gradio UI + observability | Planned |
| Evaluation harness (golden Q&A) | Planned |
```
```
