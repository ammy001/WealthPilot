"""Portfolio-summarizer: user holdings + live quotes -> value, P&L, sector mix.

Descriptive only (no advice). Live prices via get_quote; a failed quote is marked
n/a rather than guessed.
"""
try:
    from .get_quote import get_quote
except ImportError:
    from get_quote import get_quote


def summarize(user: dict) -> dict:
    holdings = user.get("holdings", [])
    rows, invested, current, sector_val = [], 0.0, 0.0, {}
    for h in holdings:
        iv = h["quantity"] * h["buy_price"]
        invested += iv
        try:
            q = get_quote(h["symbol"])
            price = q["price"]
            cv = price * h["quantity"]
            current += cv
            sector_val[h.get("sector", "?")] = sector_val.get(h.get("sector", "?"), 0.0) + cv
            rows.append({"symbol": h["symbol"], "sector": h.get("sector"),
                         "quantity": h["quantity"], "buy_price": h["buy_price"],
                         "price": price, "invested": round(iv, 2), "current": round(cv, 2),
                         "pnl": round(cv - iv, 2),
                         "pnl_pct": round((cv - iv) / iv * 100, 1) if iv else None})
        except Exception:
            rows.append({"symbol": h["symbol"], "sector": h.get("sector"),
                         "quantity": h["quantity"], "buy_price": h["buy_price"],
                         "price": None, "invested": round(iv, 2), "current": None,
                         "pnl": None, "pnl_pct": None, "note": "live price unavailable"})
    pnl = current - invested
    total_cur = current or 1
    sector_pct = {s: round(v / total_cur * 100, 1) for s, v in
                  sorted(sector_val.items(), key=lambda kv: -kv[1])}
    return {
        "user": user.get("name"), "risk_tolerance": user.get("risk_tolerance"),
        "positions": rows, "invested": round(invested, 2), "current_value": round(current, 2),
        "pnl": round(pnl, 2), "pnl_pct": round(pnl / invested * 100, 1) if invested else None,
        "sector_pct": sector_pct,
    }
