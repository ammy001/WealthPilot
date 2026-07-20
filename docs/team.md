# WealthPilot — Team & Stack (Week 1, task 1)

Solo build — one person covering all five role areas defined in the course's task plan.

| Role | Responsibility | Owner |
|---|---|---|
| Prompt / RAG | System prompt, corpus, ingestion, retrieval quality | Ravindra Holalkere |
| Tools / MCP | `get_quote`, `get_index`, `portfolio_calc`, MCP integration | Ravindra Holalkere |
| Memory | Profile/holdings schema, cross-session recall | Ravindra Holalkere |
| Guardrails / caching | Safety gate, disclaimers, quote cache | Ravindra Holalkere |
| Observability / UI | Gradio UI, trace logging, dashboard | Ravindra Holalkere |

## Requirements read
`requirements.md` (Marcus Chen persona, sample queries, constraints, guardrail
requirements) reviewed before starting Week 1.

## Agreed stack

| Layer | Choice |
|---|---|
| LLM | Switchable — Ollama (llama3.3), Groq, custom OpenAI-compatible endpoint, or Azure OpenAI (`config.py`) |
| Embeddings | mxbai-embed-large, 1024-d |
| Vector store + memory (seed) | PostgreSQL + pgvector (chunks); JSON file (user profiles, see `docs/memory-schema.md`) |
| Reranker | `BAAI/bge-reranker-v2-m3` cross-encoder |
| Tool transport | MCP (`mcp_server/server.py`) |
| UI | Gradio |
| Language | Python 3.11+ |

Rationale: an env-driven, provider-switchable LLM client (`llm.py`) so the same code
runs against a free local model (Ollama) during development and a hosted model for
the demo, without touching orchestration/RAG/guardrail code.
