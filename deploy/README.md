# WealthPilot — FastAPI deployment

JSON API over the WealthPilot agent (`agent.orchestrator.respond`). Same brain as the
Gradio UI; loads the cross-encoder reranker at startup, then serves.

## Files
- `api.py` — the FastAPI service (entrypoint).
- `Dockerfile` — container image (bakes the reranker model into the HF cache).
- `.dockerignore` — keeps the build context small and secrets out.

## Endpoints
| Method | Path | Body / notes |
|---|---|---|
| GET | `/health` | `{status, provider, model, reranker_ready}` — use for readiness probe |
| GET | `/users` | list of synthetic users (`user_id`, `name`, `risk_tolerance`) |
| POST | `/chat` | `{"message": "...", "user_id": "U001"}` (`user_id` optional) → `{answer, route, sources, trace}` |
| GET | `/docs` | Swagger UI |

## Run without Docker (from project root)
```bash
pip install -r requirements.txt
python deploy/api.py                                  # reads HOST/PORT env
# or: uvicorn deploy.api:app --host 0.0.0.0 --port 8000
```

## Run with Docker (build from the PROJECT ROOT)
```bash
docker build -f deploy/Dockerfile -t wealthpilot-api .
docker run --env-file .env -p 8000:8000 wealthpilot-api
```

## Required runtime environment
Provide via `--env-file .env` (or your container's secret store):
- **LLM (Azure):** `LLM_PROVIDER=azure`, `AZURE_OPENAI_ENDPOINT`, `OPENAI_API_VERSION`,
  `DEPLOYMENT_NAME`, `OPENAI_AIML_KEY`
- **Embeddings:** `EMBED_BASE_URL`, `EMBED_PATH`, `EMBED_MODEL`, `EMBED_DIM`
- **Postgres/pgvector:** `PG_DSN`, `PG_SCHEMA`
- **TLS / offline:** `INSECURE_SSL=1` (or a mounted `CA_BUNDLE`/`CURL_CA_BUNDLE`),
  `HF_HUB_OFFLINE=1`

## Deployment notes
- **Network:** the embeddings endpoint and Postgres are internal `10.169.x.x` hosts — the
  container must be able to reach them (VPN/overlay network).
- **Reranker:** the image bakes `BAAI/bge-reranker-v2-m3` into the HF cache at build time
  (needs network during `docker build`). At runtime `HF_HUB_OFFLINE=1` loads it from cache.
- **CPU:** the reranker is CPU-bound (~1.3s/pair). Give the container several cores, and/or
  tune `RAG_RERANK_POOL` (default 40) and `RAG_MAX_ITERS` (default 2) down for lower latency.
- **Fast helper model:** `FAST_LLM_PROVIDER` / `FAST_LLM_MODEL` route the agentic
  subquery/grading steps to a cheap fast model (defaults to the main LLM).

## Quick test
```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"how did the FMCG sector perform in the last 6 months?","user_id":"U001"}'
```
