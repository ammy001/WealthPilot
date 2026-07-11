"""Live index/sector/macro lookup tool (mirrors get_quote): yfinance, cached.

Contract:
  get_index(name) -> {name, ticker, level, change, change_pct, timestamp, cache_hit}
Raises ValueError for an unknown index name.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from .cache import get_or_set
except ImportError:
    from cache import get_or_set

from data.market_indices import get_index_live, ALL  # noqa: E402

INDEX_TTL = 60


def get_index(name: str) -> dict:
    def _fetch():
        d = get_index_live(name)
        d["timestamp"] = datetime.now(timezone.utc).isoformat()
        return d

    value, hit = get_or_set(f"index:{name.lower()}", _fetch, ttl=INDEX_TTL)
    return {**value, "cache_hit": hit}


def known_indices():
    return list(ALL)


if __name__ == "__main__":
    import json
    n = sys.argv[1] if len(sys.argv) > 1 else "NIFTY 50"
    print(json.dumps(get_index(n), indent=2))
