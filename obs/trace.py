"""Observability sink — one JSONL record per turn, for explainability & audit.

Append-only log at obs/traces/traces.jsonl (gitignored). `log_turn` never raises
(observability must not break a response); `recent_traces` reads the tail for the UI.
"""
import datetime
import json
import os

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "obs", "traces")
_FILE = os.path.join(_DIR, "traces.jsonl")


def log_turn(user, query, result):
    """Append a compact record for one turn. Returns the record (or None on failure)."""
    try:
        os.makedirs(_DIR, exist_ok=True)
        uid = user.get("user_id") if isinstance(user, dict) else user
        rec = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "user": uid,
            "query": query,
            "route": result.get("route"),
            "answer": (result.get("answer") or "")[:2000],
            "sources": [s.get("doc_id") for s in (result.get("sources") or []) if isinstance(s, dict)],
            "trace": result.get("trace"),
        }
        with open(_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return rec
    except Exception:
        return None


def recent_traces(n=30):
    """Most-recent-first list of the last n trace records ([] if none)."""
    if not os.path.exists(_FILE):
        return []
    try:
        with open(_FILE, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [json.loads(ln) for ln in lines if ln.strip()][::-1]
    except Exception:
        return []
