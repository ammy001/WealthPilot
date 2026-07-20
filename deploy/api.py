"""WealthPilot — FastAPI service (for containerized deployment).

Wraps the same agent used by the Gradio UI (`agent.orchestrator.respond`) behind a JSON API.
Lives in deploy/ but imports the app package from the project root (added to sys.path below).

Endpoints:
  GET  /health          -> liveness + provider/model + reranker readiness
  GET  /users           -> synthetic user profiles (for a user selector)
  POST /chat            -> {message, user_id?} -> {answer, route, sources, trace}

Run (from project root):  python deploy/api.py
                          uvicorn deploy.api:app --host 0.0.0.0 --port 8000
Container env: HOST, PORT, plus the usual INSECURE_SSL/CA_BUNDLE/CURL_CA_BUNDLE,
               HF_HUB_OFFLINE, and the LLM/embeddings/PG settings from .env.
"""
import os
import sys

# Make the project root importable (this file lives in deploy/).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# TLS / offline setup BEFORE importing anything that makes network calls (mirrors app.py).
os.environ.setdefault("INSECURE_SSL", "1")        # corporate SSL-inspection proxy
os.environ.setdefault("HF_HUB_OFFLINE", "1")      # reranker loads from local cache

import insecure_ssl  # noqa: E402
insecure_ssl.maybe_disable_tls_verification()

import logging  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from typing import Any, Dict, List, Optional  # noqa: E402

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import memory  # noqa: E402
from agent.orchestrator import respond  # noqa: E402
from llm import MODEL, PROVIDER  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wealthpilot")

# The cross-encoder reranker and DB access are shared, non-reentrant state; serialize
# request handling. This is an educational single-node service (low concurrency).
_LOCK = threading.Lock()
_RERANKER_READY = False


class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    route: str
    sources: List[Dict[str, Any]] = []
    trace: Dict[str, Any] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load the cross-encoder reranker at startup (before serving) so the first /chat
    # doesn't pay the ~60s cold-load. Loads from the local HF cache (HF_HUB_OFFLINE=1).
    from rag.retrieve import RERANKER_MODEL, _get_reranker
    log.info("Loading reranker model %s ...", RERANKER_MODEL)
    t = time.perf_counter()
    try:
        _get_reranker()
        global _RERANKER_READY
        _RERANKER_READY = True
        log.info("Reranker loaded in %.1fs — WealthPilot API ready (provider=%s model=%s)",
                 time.perf_counter() - t, PROVIDER, MODEL)
    except Exception as e:
        # Fail loudly in logs but still serve: /health stays up so the container is diagnosable;
        # knowledge queries will error until the model is available in the HF cache.
        log.error("Reranker FAILED to load (%s: %s). Ensure the model is in the HF cache and "
                  "HF_HUB_OFFLINE=1. Serving anyway; RAG queries will fail until fixed.",
                  type(e).__name__, e)
    yield


app = FastAPI(title="WealthPilot API", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "provider": PROVIDER, "model": MODEL,
            "reranker_ready": _RERANKER_READY}


@app.get("/users")
def users():
    return [{"user_id": uid, "name": name, "risk_tolerance": risk}
            for uid, name, risk in memory.list_users()]


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    user = memory.get_user(req.user_id) if req.user_id else None
    if req.user_id and user is None:
        raise HTTPException(status_code=404, detail=f"unknown user_id {req.user_id!r}")
    try:
        with _LOCK:
            r = respond(req.message, user=user)
    except Exception as e:  # never leak a stack trace to the client
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    return ChatResponse(answer=r["answer"], route=r.get("route", ""),
                        sources=r.get("sources") or [], trace=r.get("trace") or {})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))
