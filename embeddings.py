"""mxbai embeddings via the Ollama OpenAI-compatible endpoint."""
from openai import OpenAI

from config import EMBED

_client = OpenAI(base_url=EMBED["base_url"], api_key=EMBED["api_key"] or "unused")


def embed(texts):
    """Return a list of embedding vectors for a list of strings."""
    if isinstance(texts, str):
        texts = [texts]
    resp = _client.embeddings.create(model=EMBED["model"], input=texts)
    return [d.embedding for d in resp.data]


def embed_one(text):
    return embed([text])[0]
