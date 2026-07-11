"""Generate educational per-company fact sheets (markdown) + an enriched CSV
from data/fundamentals.analyse() over the NIFTY 100 constituents.

Educational framing: DIRECTIVE / OPINION fields (analyst_rating, price targets,
verdict, score) are deliberately EXCLUDED to respect the no-directive-advice
guardrail. Only descriptive, sourced figures go into the corpus. Missing values
are left blank (never fabricated).

Run:  INSECURE_SSL=1 python ingest/build_factsheets.py [limit]
"""
import csv
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import insecure_ssl  # noqa: E402
insecure_ssl.maybe_disable_tls_verification()

from data import fundamentals as F  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "corpus", "nifty100_constituents.csv")
DOCS = os.path.join(ROOT, "corpus", "companies")
OUT_CSV = os.path.join(ROOT, "corpus", "nifty100_fundamentals_enriched.csv")
ASOF = date.today().isoformat()

os.makedirs(DOCS, exist_ok=True)

# Screener's dividend_yield/payout_ratio come through swapped/misparsed, so we
# override dividend yield with the validated value from the yfinance CSV and
# drop payout ratio rather than publish a wrong number (no-fabrication guardrail).
_YF_CSV = os.path.join(ROOT, "corpus", "nifty100_fundamentals.csv")
YF_DIV = {}
if os.path.exists(_YF_CSV):
    for _r in csv.DictReader(open(_YF_CSV, encoding="utf-8")):
        YF_DIV[_r["symbol"]] = _r.get("dividend_yield", "")

# (label, attr, unit) — descriptive fields only; opinion/directive fields omitted.
SECTIONS = [
    ("Valuation", [
        ("P/E", "pe", "x"), ("P/B", "pb", "x"), ("EV/EBITDA", "ev_ebitda", "x"),
        ("Price/Sales", "price_to_sales", "x"), ("Forward P/E", "forward_pe", "x"),
    ]),
    ("Profitability", [
        ("ROE", "roe", "%"), ("ROCE", "roce", "%"), ("Net margin", "npm", "%"),
        ("Operating margin", "operating_margin", "%"), ("EBITDA margin", "ebitda_margin", "%"),
    ]),
    ("Growth", [
        ("Sales growth", "sales_growth", "%"), ("Profit growth", "profit_growth", "%"),
    ]),
    ("Financial health", [
        ("Debt/Equity", "debt_equity", "x"), ("Current ratio", "current_ratio", "x"),
        ("Interest coverage", "interest_coverage", "x"), ("Free cash flow", "free_cash_flow", " cr"),
        ("Total cash", "total_cash_cr", " cr"), ("Total debt", "total_debt_cr", " cr"),
    ]),
    ("Ownership", [
        ("Promoter holding", "promoter_holding", "%"),
        ("Institutional (FII+DII)", "institutional_holding", "%"),
        ("Pledged", "pledged_pct", "%"),
    ]),
    # Dividend handled separately (see YF_DIV override) — Screener values unreliable.
    ("Price context", [
        ("Market cap", "market_cap", " cr"), ("52-week high", "week52_high", ""),
        ("52-week low", "week52_low", ""), ("% from 52w high", "pct_from_52w_high", "%"),
        ("50-day avg", "avg_50d", ""), ("200-day avg", "avg_200d", ""), ("Beta", "beta", ""),
    ]),
]

CSV_FIELDS = ["symbol", "name", "sector", "industry", "pe", "pb", "roe", "roce", "npm",
              "sales_growth", "profit_growth", "debt_equity", "promoter_holding",
              "institutional_holding", "pledged_pct", "dividend_yield", "market_cap",
              "week52_high", "week52_low", "status"]


def fmt(val, unit):
    if val is None or val == "":
        return "_n/a_"
    if isinstance(val, float):
        val = f"{val:,.2f}".rstrip("0").rstrip(".")
    return f"{val}{unit}"


RET_WINDOWS = [("1Y", 252), ("3Y", 756), ("5Y", 1260)]


def mcap_band(cr):
    """Rough market-cap class from value in INR crore."""
    if not cr:
        return None
    if cr >= 20000:
        return "Large-cap"
    if cr >= 5000:
        return "Mid-cap"
    return "Small-cap"


def fetch_extra(sym):
    """Descriptive context from yfinance: business summary, identity, float,
    trailing stock returns, extra valuation. Returns {} on failure (never fabricates)."""
    import yfinance as yf
    out = {"returns": {}}
    tk = None
    try:
        tk = yf.Ticker(f"{sym}.NS")
        info = tk.info or {}
    except Exception:
        info = {}
    if info:
        out["summary"] = (info.get("longBusinessSummary") or "").strip()
        out["website"] = info.get("website")
        out["city"] = info.get("city")
        out["country"] = info.get("country")
        out["employees"] = info.get("fullTimeEmployees")
        so, fl = info.get("sharesOutstanding"), info.get("floatShares")
        out["shares_out"] = so
        out["free_float_pct"] = round(fl / so * 100, 1) if so and fl else None
        out["eps_ttm"] = info.get("trailingEps")
        out["eps_fwd"] = info.get("forwardEps")
        out["book_value"] = info.get("bookValue")
        out["peg"] = info.get("pegRatio")
        out["roa"] = round(info["returnOnAssets"] * 100, 2) if info.get("returnOnAssets") is not None else None
        out["rev_per_share"] = info.get("revenuePerShare")
    try:
        close = tk.history(period="6y")["Close"].dropna() if tk is not None else []
        if len(close):
            last = float(close.iloc[-1])
            for lbl, off in RET_WINDOWS:
                if len(close) > off:
                    past = float(close.iloc[-(off + 1)])
                    if past:
                        out["returns"][lbl] = round((last / past - 1) * 100, 2)
    except Exception:
        pass
    return out


def render(snap, nse_industry, div_yield="", extra=None):
    extra = extra or {}
    lines = [f"# {snap.name or snap.symbol} ({snap.symbol})", ""]
    band = mcap_band(snap.market_cap)
    hdr = f"**Sector:** {snap.sector or nse_industry} · **Industry:** {snap.industry or nse_industry}"
    if band:
        hdr += f" · **Class:** {band}"
    lines.append(hdr)
    lines.append(f"**As of:** {ASOF} · **Sources:** Screener.in, Yahoo Finance, NSE (delayed, educational use only)")
    lines.append("")
    if extra.get("summary"):
        lines.append("## About")
        lines.append(extra["summary"])
        lines.append("")
    ident = []
    if extra.get("city") or extra.get("country"):
        ident.append("HQ: " + ", ".join(x for x in [extra.get("city"), extra.get("country")] if x))
    if extra.get("employees"):
        ident.append(f"Employees: {extra['employees']:,}")
    if extra.get("website"):
        ident.append(f"Website: {extra['website']}")
    if ident:
        lines.append("## Company")
        lines += [f"- {x}" for x in ident]
        lines.append("")
    for title, rows in SECTIONS:
        vals = [(lbl, fmt(getattr(snap, attr, None), unit)) for lbl, attr, unit in rows]
        if all(v == "_n/a_" for _, v in vals):
            continue
        lines.append(f"## {title}")
        for lbl, v in vals:
            lines.append(f"- {lbl}: {v}")
        lines.append("")
    if div_yield not in ("", None):
        lines.append("## Dividend")
        lines.append(f"- Dividend yield: {div_yield}% _(Yahoo Finance)_")
        lines.append("")
    rets = extra.get("returns") or {}
    if rets:
        lines.append("## Stock price returns")
        for lbl in ("1Y", "3Y", "5Y"):
            if lbl in rets:
                lines.append(f"- {lbl}: {rets[lbl]:+.2f}%")
        lines.append("")
    liq = [("Free float", extra.get("free_float_pct"), "%"),
           ("Shares outstanding", extra.get("shares_out"), "")]
    if any(v is not None for _, v, _ in liq):
        lines.append("## Liquidity & float")
        for lbl, v, u in liq:
            if v is not None:
                lines.append(f"- {lbl}: {fmt(v, u)}")
        lines.append("")
    addl = [("EPS (TTM)", extra.get("eps_ttm"), ""), ("EPS (forward)", extra.get("eps_fwd"), ""),
            ("Book value/share", extra.get("book_value"), ""), ("PEG", extra.get("peg"), "x"),
            ("Return on assets", extra.get("roa"), "%"), ("Revenue/share", extra.get("rev_per_share"), "")]
    if any(v is not None for _, v, _ in addl):
        lines.append("## Additional valuation")
        for lbl, v, u in addl:
            if v is not None:
                lines.append(f"- {lbl}: {fmt(v, u)}")
        lines.append("")
    if snap.quarterly_revenue:
        lines.append("## Quarterly performance (most recent first)")
        for q in snap.quarterly_revenue[:4]:
            if isinstance(q, dict):
                parts = []
                if q.get("revenue_cr") is not None:
                    parts.append(f"revenue ₹{float(q['revenue_cr']):,.0f} cr")
                if q.get("profit_cr") is not None:
                    parts.append(f"profit ₹{float(q['profit_cr']):,.0f} cr")
                lines.append(f"- {q.get('quarter','')}: " + ", ".join(parts))
            else:
                lines.append(f"- {q}")
        lines.append("")
    if snap.announcements:
        lines.append("## Recent announcements")
        for a in snap.announcements[:5]:
            if isinstance(a, dict):
                lines.append(f"- {a.get('date','')}: {a.get('subject') or a.get('title') or a}")
            else:
                lines.append(f"- {a}")
        lines.append("")
    lines.append("> Educational information only. Not investment advice. "
                 "Figures are point-in-time snapshots and may be revised.")
    return "\n".join(lines)


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    if limit:
        rows = rows[:limit]
    print(f"generating fact sheets for {len(rows)} companies", flush=True)

    summary = []
    for n, r in enumerate(rows, 1):
        sym, ind = r["Symbol"], r["Industry"]
        status = "ok"
        try:
            snap = F.analyse(sym)
            if not snap.name and snap.pe is None and snap.market_cap is None:
                status = "unavailable"
            dy = YF_DIV.get(sym, "")
            extra = fetch_extra(sym)
            md = render(snap, ind, dy, extra)
            with open(os.path.join(DOCS, f"{sym}.md"), "w", encoding="utf-8") as f:
                f.write(md)
            row = {k: getattr(snap, k, "") for k in CSV_FIELDS if k not in ("symbol", "name", "industry", "status", "dividend_yield")}
            row.update(symbol=sym, name=snap.name, industry=ind, status=status, dividend_yield=dy)
            summary.append(row)
        except Exception as e:
            status = f"error:{type(e).__name__}"
            summary.append({**{k: "" for k in CSV_FIELDS}, "symbol": sym, "industry": ind, "status": status})
        print(f"[{n:3}/{len(rows)}] {sym:14} {status}", flush=True)
        time.sleep(1.2)

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(summary)
    ok = sum(1 for r in summary if r["status"] == "ok")
    print(f"\nDONE: {ok}/{len(summary)} ok  ->  {DOCS}  +  {OUT_CSV}", flush=True)


if __name__ == "__main__":
    main()
