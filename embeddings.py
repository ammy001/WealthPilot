"""mxbai embeddings via the CloudXP Ollama-native endpoint.

POST {EMBED_BASE_URL}{EMBED_PATH}  body {"model","prompt": <text>}
  -> {"embedding": [float, ... 1024]}
One text per request, so embed() loops (with light concurrency for batches).
"""
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from config import EMBED

_URL = EMBED["base_url"].rstrip("/") + EMBED["path"]
_HEADERS = {"Content-Type": "application/json"}
if EMBED["api_key"]:
    _HEADERS["apikey"] = EMBED["api_key"]

_client = httpx.Client(timeout=60.0, headers=_HEADERS)


def embed_one(text: str, retries: int = 4):
    """Embed one text; retry with backoff on transient gateway errors (502/timeout)."""
    last = None
    for attempt in range(retries):
        try:
            r = _client.post(_URL, json={"model": EMBED["model"], "prompt": text})
            r.raise_for_status()
            return r.json()["embedding"]
        except (httpx.HTTPStatusError, httpx.TransportError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def embed(texts, max_workers: int = 3):
    """Return a list of embedding vectors for a list of strings (order preserved)."""
    if isinstance(texts, str):
        texts = [texts]
    if len(texts) == 1:
        return [embed_one(texts[0])]
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(embed_one, texts))
