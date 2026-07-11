"""Tiny in-process TTL cache for tool calls (quotes, market data).

Returns a (value, hit) tuple so callers can surface a cache hit/miss badge
in the UI (Week 3 requirement). Swap for Redis/SQLite later if needed.
"""
import time

_STORE = {}  # key -> (expires_at, value)


def get_or_set(key, producer, ttl=60):
    """Return (value, hit). On miss, call producer() and cache it for `ttl` seconds."""
    now = time.time()
    entry = _STORE.get(key)
    if entry and entry[0] > now:
        return entry[1], True
    value = producer()
    _STORE[key] = (now + ttl, value)
    return value, False


def clear():
    _STORE.clear()
