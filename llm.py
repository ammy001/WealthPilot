"""Provider-switching chat client.

Two clients:
  - `chat(...)`  — the main answer model (LLM_PROVIDER / MODEL).
  - `chat_fast(...)` — a cheaper/faster helper for lightweight agentic steps
    (query reformulation, chunk grading). Defaults to the same model as `chat`,
    but can be pointed at a fast model (e.g. gpt-4o-mini) via FAST_LLM_* env vars
    even when the main answer model is a slower/heavier one.

Usage:
    from llm import chat, chat_fast, MODEL, PROVIDER
    resp = chat(messages=[...], tools=[...])
"""
import os

import httpx
from openai import AzureOpenAI, OpenAI

from config import FAST_LLM, FAST_LLM_PROVIDER, LLM, LLM_PROVIDER

PROVIDER = LLM_PROVIDER
MODEL = LLM["model"]
FAST_PROVIDER = FAST_LLM_PROVIDER
FAST_MODEL = FAST_LLM["model"]


def _tls_verify():
    """Handle corporate SSL-inspection proxies. Priority:
    INSECURE_SSL=1 -> no verify; else a CA bundle from env; else default (certifi)."""
    if os.getenv("INSECURE_SSL") == "1":
        return False
    ca = os.getenv("CA_BUNDLE") or os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE")
    return ca if ca else True


def _build_client(provider, cfg):
    http_client = httpx.Client(verify=_tls_verify(), timeout=httpx.Timeout(180.0))
    if provider.lower() == "azure":
        # Azure: model=deployment name; endpoint + api_version instead of base_url.
        return AzureOpenAI(
            api_key=cfg["api_key"] or "unused",
            api_version=cfg["api_version"],
            azure_endpoint=cfg["azure_endpoint"],
            http_client=http_client,
        )
    kwargs = {
        "base_url": cfg["base_url"],
        # OpenAI SDK requires a non-empty api_key even when auth is via a custom header.
        "api_key": cfg["api_key"] or "unused",
        "http_client": http_client,
    }
    if cfg["header_name"]:
        kwargs["default_headers"] = {cfg["header_name"]: cfg["api_key"]}
    return OpenAI(**kwargs)


client = _build_client(LLM_PROVIDER, LLM)
# Reuse the main client when the helper is identical, so we don't open a needless connection.
_fast_same = FAST_PROVIDER.lower() == PROVIDER.lower() and FAST_MODEL == MODEL
fast_client = client if _fast_same else _build_client(FAST_LLM_PROVIDER, FAST_LLM)


def _complete(cli, model, messages, tools, temperature, kwargs):
    args = {"model": model, "messages": messages, "temperature": temperature, **kwargs}
    if tools:
        args["tools"] = tools
        args.setdefault("tool_choice", "auto")
    return cli.chat.completions.create(**args)


def chat(messages, tools=None, temperature=0.2, **kwargs):
    """Main answer model."""
    return _complete(client, MODEL, messages, tools, temperature, kwargs)


def chat_fast(messages, tools=None, temperature=0.2, **kwargs):
    """Cheaper/faster helper model for lightweight agentic steps (falls back to `chat`)."""
    return _complete(fast_client, FAST_MODEL, messages, tools, temperature, kwargs)
