"""Minimal cited RAG answer: retrieve -> ground the LLM on chunks -> cited answer.

- Answers ONLY from retrieved context (no outside knowledge, no invented numbers).
- Cites sources inline as [S1], [S2]; returns the source map.
- Abstains when the confidence gate fails.
- Strips any stray reasoning tokens from the (reasoning) model's output.

Run:  INSECURE_SSL=1 HF_HUB_OFFLINE=1 python -m rag.answer "your question"
"""
import os
import re

from guardrails.rules import classify_input, enforce
from llm import chat
from rag.agentic_retrieve import agentic_search
from rag.query_ops import decompose
from rag.retrieve import search

# Agentic (multi-query + CRAG) retrieval is the default; RAG_AGENTIC=0 falls back to single-pass.
AGENTIC = os.getenv("RAG_AGENTIC", "1") == "1"
# Query decomposition for comparison / multi-part questions (on the agentic path).
DECOMPOSE = os.getenv("RAG_DECOMPOSE", "1") == "1"


def _multi_agentic(query, subs, k, filters):
    """Run agentic retrieval per sub-question and union the evidence (dedup)."""
    merged, seen, parts, confident = [], set(), [], False
    for sq in subs:
        res, conf, _tr = agentic_search(sq, k=k, filters=filters)
        confident = confident or conf
        parts.append({"subquery": sq, "confident": conf, "n": len(res)})
        for r in res:
            key = (r["doc_id"], r["section"])
            if key not in seen:
                seen.add(key)
                merged.append(r)
    merged = sorted(merged, key=lambda r: r.get("score") or -1.0, reverse=True)[:max(k, 8)]
    return merged, confident, {"strategy": "decomposed", "subqueries": subs, "parts": parts}

SYSTEM = (
    "You are WealthPilot, an EDUCATIONAL finance assistant for Indian markets "
    "(NIFTY 100 stocks and index funds). Follow these rules strictly:\n"
    "1. Answer ONLY using the SOURCES provided. If they don't contain the answer, "
    "say you don't have that information — never use outside knowledge or guess.\n"
    "2. Cite the sources you use inline as [S1], [S2], etc.\n"
    "3. Never give directive investment advice (no 'buy', 'sell', 'invest now'). "
    "Explain and educate; leave the decision to the user.\n"
    "4. Never invent numbers. Use a figure only if it appears in the SOURCES; note it is "
    "as of the stated date.\n"
    "5. Be concise, neutral, and clear.\n"
    'Always end with: "Educational information only, not investment advice."'
)

ABSTAIN = ("I don't have information on that in my sources yet, so I can't answer reliably. "
           "Educational information only, not investment advice.")

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def _format_sources(results):
    lines, srcmap = [], []
    for i, r in enumerate(results, 1):
        tag = f"S{i}"
        loc = f"{r['doc_id']} — {r['section']}"
        asof = f" (as of {r['as_of']})" if r.get("as_of") else ""
        lines.append(f"[{tag}] {loc}{asof}\n{r['chunk_text']}")
        srcmap.append({"tag": tag, "doc_id": r["doc_id"], "section": r["section"],
                       "source": r.get("source"), "as_of": r.get("as_of")})
    return "\n\n".join(lines), srcmap


def answer(query, k=6, filters=None, user=None, agentic=None):
    use_agentic = AGENTIC if agentic is None else agentic
    flags = classify_input(query)
    risky = flags["directive"] or flags["risky"]
    retrieval_trace = None
    if risky:
        # Safety path: always respond educationally (never abstain), grounded in concept docs.
        results, _ = search(query, k=k, filters={"doc_type": "education"})
        confident = bool(results)
    elif use_agentic:
        subs = decompose(query) if DECOMPOSE else [query]
        if len(subs) > 1:
            results, confident, retrieval_trace = _multi_agentic(query, subs, k, filters)
        else:
            results, confident, retrieval_trace = agentic_search(query, k=k, filters=filters)
    else:
        results, confident = search(query, k=k, filters=filters)
    if not results or (not confident and not risky):
        return {"answer": ABSTAIN, "confident": False, "sources": [], "flags": flags,
                "guardrail_blocked": False, "guardrail_violations": [],
                "retrieval_trace": retrieval_trace}

    context, srcmap = _format_sources(results)

    caution = ""
    if flags["directive"] or flags["risky"]:
        caution = ("\n\nNOTE: This request is directive/high-risk. You MUST NOT tell the user to "
                   "buy, sell, or invest. Explain the relevant risks and trade-offs educationally "
                   "and make clear the decision is theirs.")
    if user:
        caution += (f"\n\nUSER PROFILE — reference it where relevant: risk tolerance="
                    f"{user.get('risk_tolerance')}, crypto cap={user.get('preferences',{}).get('crypto_cap_pct')}%.")

    resp = chat(
        messages=[
            {"role": "system", "content": SYSTEM + caution},
            {"role": "user", "content": f"Question: {query}\n\nSOURCES:\n{context}"},
        ],
        temperature=0.2,
        max_tokens=2048,
    )
    text = _THINK.sub("", resp.choices[0].message.content or "").strip()
    gr = enforce(text)
    text = gr["text"]
    # keep only cited sources in the returned map (those the answer referenced)
    used = {m["tag"] for m in srcmap if re.search(rf"\[{m['tag']}\]", text)}
    sources = [m for m in srcmap if m["tag"] in used] or srcmap
    return {"answer": text, "confident": True, "sources": sources,
            "flags": flags, "guardrail_blocked": gr["blocked"],
            "guardrail_violations": gr["violations"], "retrieval_trace": retrieval_trace}


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "What's a good low-cost index fund for a moderate-risk investor?"
    out = answer(q)
    print("Q:", q, "\n")
    print(out["answer"], "\n")
    print("Sources used:")
    for s in out["sources"]:
        print(f"  [{s['tag']}] {s['doc_id']} — {s['section']}"
              + (f" (as of {s['as_of']})" if s.get("as_of") else ""))
