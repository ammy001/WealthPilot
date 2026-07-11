"""Fetch free Indian-market RSS headlines and write a dated market-report doc
into the corpus (corpus/reports/market_news_<date>.md).

Run:  INSECURE_SSL=1 python ingest/build_market_news.py
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import insecure_ssl  # noqa: E402
insecure_ssl.maybe_disable_tls_verification()

from data.news_rss import get_market_news  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "corpus", "reports")
os.makedirs(OUT_DIR, exist_ok=True)

stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
items = get_market_news(n=30)
print(f"fetched {len(items)} headlines", flush=True)

out = os.path.join(OUT_DIR, f"market_news_{stamp}.md")
with open(out, "w", encoding="utf-8") as f:
    f.write(f"# Indian Market Headlines — {stamp}\n\n")
    f.write("_Aggregated from public RSS feeds (ET, MoneyControl, Business Standard). "
            "Educational use only; headlines are third-party and time-sensitive._\n\n")
    for it in items:
        f.write(f"## {it.title}\n")
        f.write(f"*{it.source} · {it.published}* — {it.url}\n\n")
        if it.summary:
            f.write(f"{it.summary}\n\n")

print(f"wrote {out}", flush=True)
