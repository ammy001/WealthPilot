"""Plumbing verification for WealthPilot.

Run after filling in .env:  python smoke_test.py

Checks, independently (one failure doesn't stop the others):
  1. Chat LLM responds via the selected provider.
  2. Chat LLM does tool-calling (required by the agent orchestrator).
  3. mxbai embeddings return vectors of the expected dimension.
  4. Postgres is reachable and the pgvector extension is available.
"""
import json
import sys

RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f"  ->  {detail}" if detail else ""))


def check_chat():
    from llm import chat, MODEL, PROVIDER
    resp = chat(
        messages=[{"role": "user", "content": "Reply with exactly the word: pong"}],
        temperature=0,
        max_tokens=1024,  # reasoning model spends tokens thinking before content
    )
    text = (resp.choices[0].message.content or "").strip()
    record("chat completion", bool(text), f"provider={PROVIDER} model={MODEL} reply={text!r}")


def check_tool_calling():
    from llm import chat
    tools = [{
        "type": "function",
        "function": {
            "name": "get_quote",
            "description": "Get the latest price for a stock/ETF ticker.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
        },
    }]
    resp = chat(
        messages=[
            {"role": "system", "content": "Use tools when asked for live data."},
            {"role": "user", "content": "What's the current price of VTI?"},
        ],
        tools=tools,
        temperature=0,
        max_tokens=1024,
    )
    msg = resp.choices[0].message
    calls = msg.tool_calls or []
    called = [c.function.name for c in calls]
    args = calls[0].function.arguments if calls else ""
    ok = "get_quote" in called
    record("tool-calling", ok, f"tool_calls={called} args={args}")


def check_embeddings():
    from embeddings import embed_one
    from config import EMBED
    vec = embed_one("A low-cost total market index fund for a moderate-risk investor.")
    got, want = len(vec), EMBED["dim"]
    record("embeddings (mxbai)", got == want, f"dim got={got} want={want} model={EMBED['model']}")


def check_pgvector():
    from db import connect, vector_extension_version
    import config
    conn = connect()
    try:
        ver = vector_extension_version(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT current_schema()")
            schema = cur.fetchone()[0]
        record("pgvector", ver is not None,
               f"vector={ver} schema={schema} (target {config.PG_SCHEMA})")
    finally:
        conn.close()


def main():
    for name, fn in [
        ("chat", check_chat),
        ("tool-calling", check_tool_calling),
        ("embeddings", check_embeddings),
        ("pgvector", check_pgvector),
    ]:
        try:
            fn()
        except Exception as e:
            record(name, False, f"{type(e).__name__}: {e}")

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n" + json.dumps({"passed": passed, "total": len(RESULTS)}))
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
