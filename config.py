"""Central, env-driven config for WealthPilot.

Switch the chat LLM provider with LLM_PROVIDER (ollama | groq | custom).
All three speak the OpenAI-compatible chat-completions API, so one client
abstraction covers them; the `custom` provider additionally supports a
non-Bearer auth header (e.g. `apikey`) for endpoints like deepseek-r1-70b.
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
            "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
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
    raise ValueError(f"Unknown LLM_PROVIDER={provider!r} (use ollama|groq|custom)")


LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
LLM = _provider_config(LLM_PROVIDER)

EMBED = {
    "base_url": os.getenv("EMBED_BASE_URL", "http://localhost:11434/v1"),
    "api_key": os.getenv("EMBED_API_KEY", "ollama"),
    "model": os.getenv("EMBED_MODEL", "mxbai-embed-large"),
    "dim": int(os.getenv("EMBED_DIM", "1024")),
}

PG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "dbname": os.getenv("PG_DB", "wealthpilot"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", ""),
}
