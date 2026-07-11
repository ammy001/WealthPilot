"""Index / sector / macro market data via yfinance.

Ticker maps adapted from india-trade-cli `market/yfinance_provider._INDEX_MAP`
and `market/indices.py`. Used by both the corpus snapshot generator
(ingest/build_market_snapshots.py) and the live get_index tool.
"""
from __future__ import annotations

# Display name -> yfinance ticker
BROAD = {
    "NIFTY 50": "^NSEI",
    "NIFTY 100": "^CNX100",
    "Nifty Midcap 50": "^NSEMDCP50",
    "Sensex": "^BSESN",
}

SECTORS = {
    "Nifty Bank": "^NSEBANK",
    "Nifty IT": "^CNXIT",
    "Nifty Pharma": "^CNXPHARMA",
    "Nifty Auto": "^CNXAUTO",
    "Nifty FMCG": "^CNXFMCG",
    "Nifty Metal": "^CNXMETAL",
    "Nifty Energy": "^CNXENERGY",
    "Nifty Realty": "^CNXREALTY",
    "Nifty Fin Services": "NIFTY_FIN_SERVICE.NS",
}

MACRO = {
    "India VIX": "^INDIAVIX",
    "USD/INR": "INR=X",
    "Gold (USD/oz)": "GC=F",
    "Crude WTI (USD)": "CL=F",
    "Brent (USD)": "BZ=F",
}

ALL = {**BROAD, **SECTORS, **MACRO}

# Approx trading-day offsets per window
WINDOWS = [("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252), ("3Y", 756), ("5Y", 1260)]


def fetch_perf(ticker: str) -> dict:
    """Return {level, currency, returns:{window:pct}, cagr:{3Y,5Y}} or {} on failure.

    Returns are point-to-point % change of daily close; 3Y/5Y also annualized (CAGR).
    Missing windows are simply absent (never fabricated).
    """
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period="6y")
    if hist is None or hist.empty:
        return {}
    close = hist["Close"].dropna()
    if close.empty:
        return {}
    last = float(close.iloc[-1])
    out = {"level": round(last, 2), "returns": {}, "cagr": {}}
    n = len(close)
    for label, off in WINDOWS:
        if n > off:
            past = float(close.iloc[-(off + 1)])
            if past:
                pct = (last / past - 1) * 100
                out["returns"][label] = round(pct, 2)
                if label in ("3Y", "5Y"):
                    years = off / 252
                    out["cagr"][label] = round(((last / past) ** (1 / years) - 1) * 100, 2)
    return out


def get_index_live(name: str) -> dict:
    """Live level + day change for a named index/sector/macro instrument."""
    ticker = ALL.get(name) or _resolve(name)
    if not ticker:
        raise ValueError(f"Unknown index {name!r}. Known: {list(ALL)}")
    import yfinance as yf

    tk = yf.Ticker(ticker)
    fi = tk.fast_info
    last = fi.get("last_price")
    prev = fi.get("previous_close")
    if last is None:
        h = tk.history(period="5d")
        if h.empty:
            raise ValueError(f"No data for {name} ({ticker})")
        last = float(h["Close"].iloc[-1])
        prev = float(h["Close"].iloc[-2]) if len(h) > 1 else last
    change = (last - prev) if prev else 0.0
    pct = (change / prev * 100) if prev else 0.0
    return {
        "name": name,
        "ticker": ticker,
        "level": round(float(last), 2),
        "change": round(float(change), 2),
        "change_pct": round(float(pct), 2),
    }


def _resolve(name: str):
    key = name.strip().lower()
    for disp, tk in ALL.items():
        if disp.lower() == key:
            return tk
    return None
