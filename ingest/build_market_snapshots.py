"""Generate dated top-down market snapshot docs for the RAG corpus:
  - index performance (broad indices)
  - sector performance (ranked by 1Y)
  - macro & commodities

Run:  INSECURE_SSL=1 python ingest/build_market_snapshots.py
"""
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import insecure_ssl  # noqa: E402
insecure_ssl.maybe_disable_tls_verification()

from data import market_indices as M  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "corpus", "market")
os.makedirs(OUT, exist_ok=True)
ASOF = date.today().isoformat()
COLS = ["1M", "3M", "6M", "1Y", "3Y", "5Y"]
SRC_NOTE = ("_Source: Yahoo Finance (delayed), computed point-to-point on daily closes; "
            "3Y/5Y also shown annualized (CAGR). Educational use only, not advice._")


def collect(mapping):
    rows = {}
    for name, ticker in mapping.items():
        try:
            rows[name] = M.fetch_perf(ticker)
        except Exception:
            rows[name] = {}
        time.sleep(0.4)
    return rows


def cell(v):
    return f"{v:+.2f}%" if isinstance(v, (int, float)) else "n/a"


def perf_table(rows):
    lines = ["| Instrument | Level | " + " | ".join(COLS) + " |",
             "|---|---|" + "|".join(["---"] * len(COLS)) + "|"]
    for name, d in rows.items():
        if not d:
            lines.append(f"| {name} | n/a | " + " | ".join(["n/a"] * len(COLS)) + " |")
            continue
        r = d.get("returns", {})
        lvl = f"{d.get('level'):,}" if d.get("level") is not None else "n/a"
        lines.append(f"| {name} | {lvl} | " + " | ".join(cell(r.get(c)) for c in COLS) + " |")
    return "\n".join(lines)


def write(fname, title, body):
    path = os.path.join(OUT, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {title} — {ASOF}\n\n{SRC_NOTE}\n\n{body}\n")
    print("wrote", path, flush=True)


def main():
    print("fetching broad indices...", flush=True)
    broad = collect(M.BROAD)
    write("index_performance.md", "Indian Index Performance", perf_table(broad))

    print("fetching sectors...", flush=True)
    sectors = collect(M.SECTORS)
    ranked = dict(sorted(sectors.items(),
                         key=lambda kv: (kv[1].get("returns", {}).get("1Y") is None,
                                         -(kv[1].get("returns", {}).get("1Y") or 0))))
    body = perf_table(ranked) + "\n\n_Sectors ranked by 1-year return (best first)._"
    write("sector_performance.md", "Indian Sector Index Performance", body)

    print("fetching macro & commodities...", flush=True)
    macro = collect(M.MACRO)
    write("macro_commodities.md", "Macro & Commodities", perf_table(macro))

    print("DONE", flush=True)


if __name__ == "__main__":
    main()
