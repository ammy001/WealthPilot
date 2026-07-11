"""Live-quote tool: yfinance primary, NSE (nsepython) fallback, with TTL cache.

Contract (see docs/tools.md):
  get_quote(ticker) -> {
      ticker, price, currency, timestamp (ISO, UTC), source, cache_hit
  }
Raises ValueError for an unknown/unresolvable ticker so the agent can surface
a clean error instead of fabricating a number.
"""
from datetime import datetime, timezone

try:
    from .cache import get_or_set
except ImportError:  # allow `python tools/get_quote.py`
    from cache import get_or_set

QUOTE_TTL = 60  # seconds


def _normalize(ticker: str):
    """Return (yf_symbol, nse_symbol). Accepts 'VTI', 'RELIANCE', 'RELIANCE.NS'."""
    t = ticker.strip().upper()
    nse = t[:-3] if t.endswith(".NS") else t
    yf = t if t.endswith(".NS") else f"{t}.NS"
    return yf, nse


def _from_yfinance(yf_symbol: str):
    import yfinance as yf
    tk = yf.Ticker(yf_symbol)
    price = None
    try:
        price = tk.fast_info.get("last_price")
    except Exception:
        price = None
    if price is None:  # fall back to last close
        hist = tk.history(period="1d")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
    if price is None:
        raise ValueError(f"yfinance returned no price for {yf_symbol}")
    currency = "INR"
    try:
        currency = tk.fast_info.get("currency") or "INR"
    except Exception:
        pass
    return float(price), currency


def _from_nse(nse_symbol: str):
    from nsepython import nse_eq
    data = nse_eq(nse_symbol)
    price = data["priceInfo"]["lastPrice"]
    return float(price), "INR"


def get_quote(ticker: str) -> dict:
    yf_symbol, nse_symbol = _normalize(ticker)

    def _fetch():
        errors = []
        for name, fn, arg in (("yfinance", _from_yfinance, yf_symbol),
                              ("nse", _from_nse, nse_symbol)):
            try:
                price, currency = fn(arg)
                return {
                    "ticker": nse_symbol,
                    "price": round(price, 2),
                    "currency": currency,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": name,
                }
            except Exception as e:  # noqa: BLE001 - collect and try next source
                errors.append(f"{name}: {e}")
        raise ValueError(f"Could not resolve quote for {ticker!r}. Tried -> " + " | ".join(errors))

    value, hit = get_or_set(f"quote:{nse_symbol}", _fetch, ttl=QUOTE_TTL)
    return {**value, "cache_hit": hit}


if __name__ == "__main__":
    import json
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    print(json.dumps(get_quote(sym), indent=2))
    print(json.dumps(get_quote(sym), indent=2))  # second call should be cache_hit=true
