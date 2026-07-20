"""WealthPilot MCP server (stdio) — exposes WealthPilot's tools to external agents.

Educational only. These tools return descriptive market/portfolio data and simple
rebalance math. They give NO investment advice and are intentionally non-directive.

Run:  python mcp_server/server.py
"""
import os
import sys

# ── TLS / offline setup BEFORE importing anything that makes network calls ──
# Mirrors app.py so the server works behind a corporate SSL-inspection proxy
# and loads the reranker/tokenizers from the local HF cache.
os.environ.setdefault("INSECURE_SSL", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

# Put the project root on sys.path so this module works when launched from the
# subfolder (python mcp_server/server.py) or imported as mcp_server.server.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import insecure_ssl  # noqa: E402
insecure_ssl.maybe_disable_tls_verification()

import json as _json  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

import memory  # noqa: E402
from tools.get_quote import get_quote as _get_quote  # noqa: E402
from tools.get_index import get_index as _get_index  # noqa: E402
from tools.portfolio_summary import summarize as _summarize  # noqa: E402
from tools.portfolio_calc import portfolio_calc  # noqa: E402

# Risk-profile model allocations (same source app/orchestrator use for rebalance).
_RP = _json.load(open(os.path.join(_ROOT, "data", "reference", "risk_profiles.json"),
                      encoding="utf-8"))

mcp = FastMCP("wealthpilot")


@mcp.tool()
def get_quote(ticker: str) -> dict:
    """Get a live/last stock quote for an Indian (NSE) equity.

    Accepts a bare symbol ('RELIANCE'), or a yfinance-style symbol ('RELIANCE.NS').
    Uses yfinance first, NSE as fallback, with a short TTL cache.

    Returns a dict: {ticker, price, currency, timestamp (ISO UTC), source, cache_hit}.
    On an unresolvable ticker returns {"error": "..."} instead of a fabricated number.
    """
    try:
        return _get_quote(ticker)
    except Exception as e:  # noqa: BLE001 - surface a clean error, never guess
        return {"error": f"Could not resolve quote for {ticker!r}: {e}"}


@mcp.tool()
def get_index(name: str) -> dict:
    """Get a live level for a market index / sector / macro series (e.g. 'NIFTY 50').

    Returns a dict: {name, ticker, level, change, change_pct, timestamp, cache_hit}.
    On an unknown index name returns {"error": "..."}.
    """
    try:
        return _get_index(name)
    except Exception as e:  # noqa: BLE001
        return {"error": f"Could not fetch index {name!r}: {e}"}


@mcp.tool()
def portfolio_summary(user_id: str) -> dict:
    """Summarize a known user's portfolio: value, P&L and sector mix (descriptive only).

    Resolve the user by id ('U001') or name via WealthPilot's memory store, price each
    holding with live quotes, and return invested/current value, P&L and sector weights.

    Returns the summary dict, or {"error": "..."} if the user id is unknown.
    """
    user = memory.get_user(user_id)
    if not user:
        return {"error": f"Unknown user {user_id!r}. Use list_users() to see valid ids."}
    return _summarize(user)


@mcp.tool()
def rebalance(user_id: str, from_asset: str, to_asset: str, amount_inr: float) -> dict:
    """Illustrate a simple rebalance for a known user (educational, non-directive).

    Uses the user's risk-profile model allocation applied to their invested value as
    the baseline (mirrors the app), then moves `amount_inr` from `from_asset` to
    `to_asset`. Asset names are coarsely bucketed into equity / debt / gold.

    Returns {user, risk_tolerance, from_asset, to_asset, amount_inr, before_pct,
    after_pct, after_amounts, before_total, after_total, note}, or {"error": "..."}.
    This only realigns toward a target mix — it is illustrative, not a recommendation.
    """
    user = memory.get_user(user_id)
    if not user:
        return {"error": f"Unknown user {user_id!r}. Use list_users() to see valid ids."}

    risk = user.get("risk_tolerance", "moderate")
    rp = _RP["profiles"].get(risk, _RP["profiles"]["moderate"])
    mid = rp["midpoint"]
    total = sum(h["quantity"] * h["buy_price"] for h in user.get("holdings", [])) or 100000
    alloc = {
        "equity": total * mid["equity"] / 100,
        "debt": total * mid["debt"] / 100,
        "gold": total * mid["gold_cash"] / 100,
    }

    def _bucket(a: str) -> str:
        a = a.lower()
        if "bond" in a or "debt" in a or "fixed" in a:
            return "debt"
        if "gold" in a or "cash" in a:
            return "gold"
        return "equity"

    amt = float(amount_inr)
    res = portfolio_calc(alloc, {_bucket(from_asset): -amt, _bucket(to_asset): amt})
    if "error" in res:
        return {"error": res["error"]}

    return {
        "user": user.get("name"),
        "risk_tolerance": risk,
        "from_asset": from_asset,
        "to_asset": to_asset,
        "amount_inr": round(amt, 2),
        "before_pct": res["before_pct"],
        "after_pct": res["after_pct"],
        "after_amounts": res["after_amounts"],
        "before_total": res["before_total"],
        "after_total": res["after_total"],
        "note": ("Baseline uses a typical model allocation for the user's risk profile. "
                 "Rebalancing realigns to a target mix; illustrative, not a suggestion to act."),
    }


@mcp.tool()
def list_users() -> list:
    """List the known users in WealthPilot's memory store.

    Returns a list of [user_id, name, risk_tolerance] entries usable with
    portfolio_summary() and rebalance().
    """
    return memory.list_users()


if __name__ == "__main__":
    mcp.run()
