"""Provider-switching chat client.

Usage:
    from llm import chat, MODEL, PROVIDER
    resp = chat(messages=[...], tools=[...])
"""
from openai import OpenAI

from config import LLM, LLM_PROVIDER

PROVIDER = LLM_PROVIDER
MODEL = LLM["model"]


def _build_client() -> OpenAI:
    kwargs = {
        "base_url": LLM["base_url"],
        # OpenAI SDK requires a non-empty api_key even when auth is via a custom header.
        "api_key": LLM["api_key"] or "unused",
    }
    if LLM["header_name"]:
        kwargs["default_headers"] = {LLM["header_name"]: LLM["api_key"]}
    return OpenAI(**kwargs)


client = _build_client()


def chat(messages, tools=None, temperature=0.2, **kwargs):
    """Thin wrapper over chat.completions so callers don't repeat model/plumbing."""
    args = {"model": MODEL, "messages": messages, "temperature": temperature, **kwargs}
    if tools:
        args["tools"] = tools
        args.setdefault("tool_choice", "auto")
    return client.chat.completions.create(**args)
