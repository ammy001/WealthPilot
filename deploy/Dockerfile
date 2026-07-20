# WealthPilot FastAPI service.
# Build from the PROJECT ROOT so the whole app package is in the build context:
#     docker build -f deploy/Dockerfile -t wealthpilot-api .
#     docker run --env-file .env -p 8000:8000 wealthpilot-api
FROM python:3.12-slim

WORKDIR /app

# System deps: build tools for psycopg2/torch wheels are usually not needed with binary
# wheels; keep the image slim. Add build-essential here only if a wheel fails to install.
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    HF_HUB_OFFLINE=1 \
    HF_HUB_ENABLE_HF_TRANSFER=0

# Install deps first (better layer caching).
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the application code.
COPY . .

# Pre-bake the reranker model into the image's HF cache so startup works offline.
# Requires network at BUILD time (HF_HUB_OFFLINE is only enforced at runtime above).
RUN HF_HUB_OFFLINE=0 python -c "from sentence_transformers import CrossEncoder; \
    CrossEncoder('BAAI/bge-reranker-v2-m3', max_length=512)"

EXPOSE 8000

# Loads the reranker at startup (lifespan), then serves. Uses HOST/PORT env (defaults below).
ENV HOST=0.0.0.0 PORT=8000
CMD ["python", "deploy/api.py"]
