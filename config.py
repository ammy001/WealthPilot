"""Central, env-driven config for WealthPilot.

Switch the chat LLM provider with LLM_PROVIDER (ollama | groq | custom | azure).
ollama/groq/custom speak the OpenAI-compatible chat-completions API, so one client
abstraction covers them; the `custom` provider additionally supports a non-Bearer
auth header (e.g. `apikey`) for endpoints like deepseek-r1-70b. `azure` uses the
AzureOpenAI client (endpoint + api_version; `model` = deployment name).
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _provider_config(provider: str) -> dict:
    p = provider.lower()
    if p == "ollama":
        return {
            "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            "api_key": os.getenv("OLLAMA_API_KEY", "ollama"),
            "model": os.getenv("OLLAMA_MODEL", "llama3.3:latest"),
            "header_name": None,
        }
    if p == "groq":
        return {
            "base_url": os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            "api_key": os.getenv("GROQ_API_KEY", ""),
            # Groq deprecated llama-3.1-8b-instant for free/dev tier (2026-06-17);
            # fall back to openai/gpt-oss-20b if it stops resolving.
            "model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            "header_name": None,
        }
    if p == "custom":
        return {
            "base_url": os.getenv("CUSTOM_BASE_URL", ""),
            "api_key": os.getenv("CUSTOM_API_KEY", ""),
            "model": os.getenv("CUSTOM_MODEL", ""),
            # e.g. "apikey" for endpoints that don't use Authorization: Bearer
            "header_name": os.getenv("CUSTOM_API_KEY_HEADER", "").strip() or None,
        }
    if p == "azure":
        # Azure OpenAI uses a different client shape: azure_endpoint + api_version, and
        # `model` is the *deployment* name (not the base model id). Supports auto tool-calling.
        return {
            "base_url": None,
            "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            "api_version": os.getenv("OPENAI_API_VERSION", "2024-08-01-preview"),
            "api_key": os.getenv("OPENAI_AIML_KEY", ""),
            "model": os.getenv("DEPLOYMENT_NAME", ""),
            "header_name": None,
        }
    raise ValueError(f"Unknown LLM_PROVIDER={provider!r} (use ollama|groq|custom|azure)")


LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
LLM = _provider_config(LLM_PROVIDER)

# Optional cheaper/faster helper model for lightweight agentic steps (query reformulation,
# chunk grading). Defaults to the same provider/model as the main LLM; set FAST_LLM_PROVIDER
# and/or FAST_LLM_MODEL to route those steps to a fast model (e.g. gpt-4o-mini) while the main
# answer model stays heavier. FAST_LLM_MODEL overrides just the model/deployment name.
FAST_LLM_PROVIDER = os.getenv("FAST_LLM_PROVIDER", LLM_PROVIDER)
FAST_LLM = _provider_config(FAST_LLM_PROVIDER)
_fast_model = os.getenv("FAST_LLM_MODEL", "").strip()
if _fast_model:
    FAST_LLM = {**FAST_LLM, "model": _fast_model}

# CloudXP mxbai embeddings use an Ollama-native endpoint: POST {base_url}{path}
# with body {"model","prompt": <text>} -> {"embedding": [floats]}  (one text per call).
EMBED = {
    "base_url": os.getenv("EMBED_BASE_URL", "http://localhost:11434"),
    "path": os.getenv("EMBED_PATH", "/api/embeddings"),
    "model": os.getenv("EMBED_MODEL", "mxbai-embed-large"),
    "dim": int(os.getenv("EMBED_DIM", "1024")),
    "api_key": os.getenv("EMBED_API_KEY", ""),
}

# Prefer a full DSN if given; else assemble from parts. PG_SCHEMA sets search_path.
PG_DSN = os.getenv("PG_DSN", "")
PG_SCHEMA = os.getenv("PG_SCHEMA", "public")
PG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DB", "wealthpilot"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", ""),
}
