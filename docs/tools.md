# WealthPilot — Tool Specs (Week 2, task 10)

All tools are **read-only / pure-compute** — none place trades or write anything except
`update_preference`, which only ever writes to the user's own stated profile (never
holdings, never market data). Every tool returns a plain dict; on failure it returns
either a raised `ValueError` (live-data tools) or an `{"error": "..."}` dict (pure/derived
tools), so the caller never has to guess whether a number is real.

---

## `get_quote(ticker: str) -> dict`
_File: `tools/get_quote.py`_

Live/last price for one NSE-listed equity.

**Input**
| Field | Type | Notes |
|---|---|---|
| `ticker` | str | Bare NSE symbol (`"RELIANCE"`) or yfinance-style (`"RELIANCE.NS"`) |

**Output**
```json
{
  "ticker": "RELIANCE",
  "price": 1301.70,
  "currency": "INR",
  "timestamp": "2026-07-10T07:23:17+00:00",
  "source": "yfinance",
  "cache_hit": false
}
```

**Error case:** unresolvable ticker → raises `ValueError` with both attempted sources'
failure reasons, e.g. `Could not resolve quote for 'FAKESYM'. Tried -> yfinance: ... | nse: ...`.
The orchestrator catches this and returns a clean "I couldn't fetch a live price for
'FAKESYM'" message rather than a fabricated number.

**Behavior:** tries `yfinance` first, falls back to NSE (`nsepython`) on failure; result
is cached 60s (`tools/cache.py`) — a repeat call within the window returns `cache_hit: true`
with no network call.

**Test (from `tools/get_quote.py:__main__`):**
```
$ python tools/get_quote.py RELIANCE
{"ticker": "RELIANCE", "price": 1301.7, ..., "cache_hit": false}
{"ticker": "RELIANCE", "price": 1301.7, ..., "cache_hit": true}   # 2nd call, same 60s window
```

---

## `portfolio_calc(allocation: dict, changes: dict | None = None) -> dict`
_File: `tools/portfolio_calc.py`_

Pure rebalance math — no I/O, no live data. Moves money between asset-class buckets and
returns the before/after mix.

**Input**
| Field | Type | Notes |
|---|---|---|
| `allocation` | dict[str, float] | Current INR amount per asset, e.g. `{"equity": 60000, "debt": 35000, "gold": 5000}` |
| `changes` | dict[str, float] | Optional signed INR delta per asset, e.g. `{"debt": -5000, "equity": 5000}` |

**Output (success)**
```json
{
  "before_pct": {"equity": 60.0, "debt": 35.0, "gold": 5.0},
  "after_amounts": {"equity": 65000, "debt": 30000, "gold": 5000},
  "after_pct": {"equity": 65.0, "debt": 30.0, "gold": 5.0},
  "before_total": 100000,
  "after_total": 100000
}
```

**Error cases** (returns `{"error": "..."}`, never raises):
- `allocation` empty/missing → `"current allocation is required"`
- `allocation` total ≤ 0 → `"current allocation total must be positive"`
- a change would push any bucket negative → `"change would make <asset> negative"`

**Test (from `tools/portfolio_calc.py:__main__`):**
```
$ python tools/portfolio_calc.py
{"before_pct": {"equity": 60.0, "debt": 35.0, "gold": 5.0}, "after_pct": {"equity": 65.0, "debt": 30.0, "gold": 5.0}, ...}
{"error": "change would make equity negative"}
```

---

## Other tools (built ahead of schedule, documented for completeness)

### `get_index(name: str) -> dict`
_File: `tools/get_index.py`_ — mirrors `get_quote` for an index/sector/macro series
(e.g. `"NIFTY 50"`, `"Nifty IT"`, `"India VIX"`). Same cache/error contract.
```json
{"name": "NIFTY 50", "ticker": "^NSEI", "level": 24194.75,
 "change": 220.4, "change_pct": 0.92, "timestamp": "...", "cache_hit": false}
```
Unknown name → `ValueError`.

### `portfolio_summary(user: dict) -> dict`  (`tools/portfolio_summary.py`)
Reads a user's holdings, prices each with `get_quote`, and returns invested/current
value, P&L, and sector-weighted mix. A single failed quote is marked `price: null,
"note": "live price unavailable"` for that holding — never guessed — the rest of the
summary still computes.

### `rebalance` (`agent/orchestrator.py:_rebalance_answer`, also exposed via MCP)
Applies the user's risk-profile model allocation (from `data/reference/risk_profiles.json`)
to their invested value as a baseline, then calls `portfolio_calc` with the requested
move. Illustrative only — never a suggestion to act.

### `update_preference` (`agent/orchestrator.py`, backed by `memory.update_preferences`)
Not a data-fetching tool — writes a user-stated risk tolerance / preference back to
`data/profiles/users.json` so it's recalled in later sessions. See
`docs/memory-schema.md` for the schema and write/read contract.

---

## MCP exposure

All of `get_quote`, `get_index`, `portfolio_summary`, `rebalance`, and `list_users` are
also exposed to external MCP clients via `mcp_server/server.py` (`python mcp_server/server.py`),
with the same input/output contracts as above but errors returned as `{"error": "..."}`
dicts instead of raised exceptions (an MCP client can't catch a Python exception).
