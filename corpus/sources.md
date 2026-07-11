# WealthPilot Corpus — Sources & Provenance

All data below is **public, delayed, and for educational use only**. No redistribution.
Every quantitative claim in a WealthPilot answer must trace back to one of these
sources (RAG citation) or a live tool output. Figures are snapshots — see as-of dates.

## Equities data (structured → auto-generated company fact sheets)

| File | Source | As-of | Notes |
|------|--------|-------|-------|
| `nifty100_constituents.csv` | NSE official index file (`ind_nifty100list.csv`) | 2026-07-10 | 100 companies: name, industry, symbol, series, ISIN |
| `nifty100_fundamentals.csv` | Yahoo Finance via `yfinance` (`.NS` tickers) | 2026-07-10 | price, m-cap, P/E, P/B, div yield, 52w range, beta. Some fields legitimately blank (non-payers, loss-making, unreported). Delayed data. |

## Fund fact sheets (`funds/`) — narrative RAG documents

| File | Source | Type |
|------|--------|------|
| `funds/nse_nifty100_index_factsheet.pdf` | niftyindices.com / NSE archives | Index factsheet (Nifty 100 index methodology, as of Jun 30 2026) |
| `funds/nippon_india_etf_nifty100.pdf` | Nippon India MF product note | Real ETF tracking Nifty 100 (expense ratio, tracking error, returns) |
| `funds/axis_nifty100_index_fund.pdf` | Axis MF | Real index fund leaflet (NAV performance, cap split, tracking error) |
| `funds/nifty_index_methodology.pdf` | NSE Indices Ltd | Equity-index methodology (how Nifty 100 is constructed) — 328p, chunk relevant sections only |
| `funds/nifty100_equalweight_factsheet.pdf` | niftyindices.com | Nifty 100 Equal Weight index variant (Jun 30 2026) |
| `funds/nifty100_quality30_factsheet.pdf` | niftyindices.com | Nifty 100 Quality 30 factor index (Jun 30 2026) |

## Market reports (`reports/`)

| File | Source | Type |
|------|--------|------|
| `reports/amfi_monthly_note_mar2026.pdf` | AMFI Monthly Note, Mar 2026 | Industry AUM, flows, category returns (1m/6m/1y/3y) — 19 pages |

## Educational concept content (`education/`) — authored, not scraped

Curated educational docs (general financial knowledge, India context, descriptive/
non-directive) that let the assistant *educate*, not just quote numbers:
`01-index-funds`, `02-costs-and-expense-ratio`, `03-risk-and-return`, `04-diversification`,
`05-asset-allocation-and-rebalancing`, `06-risk-profiles`, `07-equities-vs-speculative-assets`.
Model allocations are framed as illustrative frameworks, never targets to act on.

Machine-readable companion: `../data/reference/risk_profiles.json` (risk profile →
illustrative allocation ranges + speculative cap) for tool/agent grounding.

## Top-down market data (`market/`) — dated snapshot docs

| File | Source | Content |
|------|--------|---------|
| `market/index_performance.md` | yfinance (`^NSEI`, `^CNX100`, `^NSEMDCP50`, `^BSESN`) | NIFTY 50/100, Midcap 50, Sensex — returns 1M/3M/6M/1Y/3Y/5Y (+CAGR) |
| `market/sector_performance.md` | yfinance (9 Nifty sector indices) | Sector returns, ranked by 1Y |
| `market/macro_commodities.md` | yfinance (`^INDIAVIX`, `INR=X`, `GC=F`, `CL=F`, `BZ=F`) | India VIX, USD/INR, gold, crude, Brent |

Ticker maps adapted from india-trade-cli. Also exposed live via the `get_index(name)`
tool (`tools/get_index.py`), mirroring `get_quote`. Returns are descriptive only —
framed as "what happened", never as a forecast (no-directive guardrail).

## Synthetic user data (`../data/profiles/`) — NOT corpus, powers memory/personalization

| File | Content |
|------|---------|
| `data/profiles/users.json` | 10 synthetic users: risk tolerance, goals, crypto cap, monthly investment, nested stock holdings |
| `data/profiles/portfolios.csv` | Flat holdings table: user, symbol, sector, buy_date, quantity, buy_price, invested_value (57 positions) |

Holdings are individual NIFTY 100 **stocks** (project focus is stocks, not mutual funds).
Buy prices drawn realistically from each stock's current price / 52-week range so a
portfolio-summarizer agent can compute plausible P&L. Fully synthetic — no real PII.
U001 = "Marcus Chen" (the spec persona).

## Environment note
`yfinance` requires `CURL_CA_BUNDLE` pointing at a Windows-cert-store PEM to work
behind the corporate SSL-inspecting proxy (see project memory).
