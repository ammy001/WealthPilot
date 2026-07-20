"""Agentic retrieval loop: multi-query fusion + CRAG-style grading + corrective re-retrieve.

Motivation: naive top-k retrieval misses relevant chunks — a single query phrasing only
surfaces a few. This layer makes retrieval a *loop* that (a) widens recall with several
query reformulations (RAG-Fusion), then (b) grades what came back and, if coverage is weak
or incomplete, reformulates and retrieves again before settling (Corrective RAG).

Flow:
    query
      -> generate N reformulations (LLM)                  [multi-query / RAG-Fusion]
      -> fuse candidates across all reformulations (RRF), dedup
      -> cross-encoder rerank against the ORIGINAL query
      -> grade top candidates + assess coverage (LLM)     [CRAG grader]
           relevant? sufficient? what's missing? follow-up queries?
      -> if NOT sufficient and iterations remain:
           add follow-up queries (and relax filters once) -> re-fuse -> re-rerank -> re-grade
      -> return the relevant, reranked chunks + a retrieval trace

Closed-corpus note: unlike web-CRAG, the corrective action is query reformulation and
filter relaxation (there is no web fallback) — we search *harder* over our own corpus.

agentic_search(query, ...) -> (results, confident, trace)

Run:  INSECURE_SSL=1 HF_HUB_OFFLINE=1 python -m rag.agentic_retrieve "your question"
"""
import json
import os
import re

from llm import chat_fast
from rag.retrieve import CONF_THRESHOLD, _get_reranker, fuse_candidates, rerank_rows

N_SUBQUERIES = int(os.getenv("RAG_N_SUBQUERIES", "3"))   # reformulations besides the original
MAX_ITERS = int(os.getenv("RAG_MAX_ITERS", "2"))         # retrieval passes (1 = no correction)
POOL = int(os.getenv("RAG_RERANK_POOL", "40"))           # candidates fed to the reranker
GRADE_POOL = int(os.getenv("RAG_GRADE_POOL", "10"))      # candidates shown to the LLM grader
GRADE_SNIPPET = int(os.getenv("RAG_GRADE_SNIPPET", "1200"))  # chars/chunk shown to the grader
KEEP_SCORE = float(os.getenv("RAG_KEEP_SCORE", "0.3"))   # top hit this strong is never dropped
# CRAG corrective action for a CLOSED corpus: when the corpus can't answer, pull live RSS
# market news as a last-resort source (self-filtering — irrelevant headlines rerank low).
NEWS_FALLBACK = os.getenv("RAG_NEWS_FALLBACK", "1") == "1"
NEWS_N = int(os.getenv("RAG_NEWS_N", "8"))

_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def _json_from(text):
    """Extract the first JSON object/array from a (possibly reasoning-model) reply."""
    if not text:
        return None
    text = _THINK.sub("", text)
    text = re.sub(r"```(?:json)?|```", "", text)
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i, j = text.find(open_c), text.rfind(close_c)
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


def _gen_subqueries(query, n=N_SUBQUERIES):
    """LLM generates alternative phrasings/keyword forms to widen recall (RAG-Fusion)."""
    sys = (
        "You expand a finance search query into diverse reformulations to improve retrieval "
        "recall over a corpus of Indian-market (NIFTY 100) company facts, sector/index "
        "performance tables, fund factsheets, and education notes. Produce short, varied "
        "queries: include at least one terse keyword form (entity + metric, no filler words) "
        "and one that uses likely document vocabulary (e.g. 'Nifty FMCG', '6M return'). "
        f'Return ONLY JSON: {{"queries": ["...", "..."]}} with exactly {n} queries.'
    )
    try:
        resp = chat_fast(messages=[{"role": "system", "content": sys},
                              {"role": "user", "content": query}],
                    temperature=0, max_tokens=1200)
        data = _json_from(resp.choices[0].message.content) or {}
        qs = [q.strip() for q in data.get("queries", []) if isinstance(q, str) and q.strip()]
    except Exception:
        qs = []
    # always keep the original; dedup case-insensitively
    out, seen = [], set()
    for q in [query] + qs:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            out.append(q)
    return out[: n + 1]


def _collect(queries, filters, k_vec, k_kw):
    """Fuse candidate rows across all queries, deduped by chunk id (row[0])."""
    by_id = {}
    for q in queries:
        for row in fuse_candidates(q, filters=filters, k_vec=k_vec, k_kw=k_kw):
            by_id.setdefault(row[0], row)
    return list(by_id.values())


def _grade(query, results):
    """CRAG grader: which chunks are relevant, is coverage sufficient, what follow-ups help.

    Returns dict {relevant: [1-based idx], sufficient: bool, missing: str, followups: [str]}.
    On parse failure returns None (caller falls back to the rerank-score gate)."""
    shown = results[:GRADE_POOL]
    lines = []
    for i, r in enumerate(shown, 1):
        snippet = r["chunk_text"].replace("\n", " ")[:GRADE_SNIPPET]
        lines.append(f"[{i}] ({r['doc_id']} — {r['section']}) {snippet}")
    sys = (
        "You grade retrieved chunks for a finance Q&A system. Decide which chunks are RELEVANT "
        "to answering the question, whether together they are SUFFICIENT to answer it fully, "
        "and if not, what is missing and which follow-up search queries would find it. Judge "
        "only by the chunk text shown. Be strict: a chunk is relevant only if it contains "
        "information that helps answer THIS question.\n"
        'Return ONLY JSON: {"relevant": [<1-based indices>], "sufficient": <true|false>, '
        '"missing": "<what info is still needed, or empty>", "followups": ["<query>", ...]}'
    )
    user = f"Question: {query}\n\nCHUNKS:\n" + "\n".join(lines)
    try:
        resp = chat_fast(messages=[{"role": "system", "content": sys},
                              {"role": "user", "content": user}],
                    temperature=0, max_tokens=1500)
        data = _json_from(resp.choices[0].message.content)
    except Exception:
        data = None
    if not isinstance(data, dict):
        return None
    rel = [i for i in data.get("relevant", []) if isinstance(i, int) and 1 <= i <= len(shown)]
    followups = [q.strip() for q in data.get("followups", [])
                 if isinstance(q, str) and q.strip()]
    return {"relevant_idx": rel, "sufficient": bool(data.get("sufficient")),
            "missing": str(data.get("missing", "")).strip(), "followups": followups}


def _news_results(query, n=NEWS_N):
    """Live RSS market headlines as pseudo-chunks (doc_id 'news:<source>') for the
    corrective fallback. Best-effort network call; returns [] on any failure."""
    try:
        from data.news_rss import get_market_news
        items = get_market_news(n=n, feeds=2)
    except Exception:
        return []
    out = []
    for it in items:
        text = f"{it.title}. {it.summary}".strip()
        day = (it.published or "")[:10] or None
        out.append(dict(doc_id=f"news:{it.source}", entity=None, title=it.title,
                        section=day or "news", chunk_text=text, source=it.url,
                        as_of=day, locator="rss", score=None))
    return out


def agentic_search(query, k=6, filters=None, k_vec=20, k_kw=20, max_iters=MAX_ITERS):
    """Coverage-aware retrieval. Returns (results, confident, trace)."""
    trace = {"strategy": "agentic", "iterations": [], "subqueries": []}

    queries = _gen_subqueries(query)
    trace["subqueries"] = queries
    active_filters = filters
    candidates = _collect(queries, active_filters, k_vec, k_kw)

    reranked, top_score = rerank_rows(query, candidates, k=max(k, GRADE_POOL), pool=POOL)
    best = reranked[:k]
    confident = top_score >= CONF_THRESHOLD

    for it in range(max_iters):
        grade = _grade(query, reranked)
        step = {"n": it + 1, "candidates": len(candidates), "top_score": round(top_score, 3)}
        if grade is None:
            # grader unavailable -> fall back to the plain rerank gate
            step["grade"] = "unavailable(fallback to score gate)"
            trace["iterations"].append(step)
            return best, confident, trace

        rel_rows = [reranked[i - 1] for i in grade["relevant_idx"]]
        # Safeguard: a strongly-reranked top hit is never dropped by the grader
        # (guards against the grader mis-judging a chunk it only partially sees).
        if reranked and top_score >= KEEP_SCORE and reranked[0] not in rel_rows:
            rel_rows = [reranked[0]] + rel_rows
            step["kept_top_hit"] = True
        step.update(relevant=len(rel_rows), sufficient=grade["sufficient"],
                    missing=grade["missing"][:160])
        trace["iterations"].append(step)

        if rel_rows:
            best = rel_rows[:k]
            confident = True
        # stop if the grader is satisfied, out of passes, or has no way forward
        if grade["sufficient"] or it == max_iters - 1 or not grade["followups"]:
            break

        # corrective action: search harder with follow-up queries; relax filters once.
        new_q = [q for q in grade["followups"] if q.lower() not in {x.lower() for x in queries}]
        queries.extend(new_q)
        step["followups"] = new_q
        if active_filters and it == 0:
            active_filters = None  # widen scope on first correction
            step["relaxed_filters"] = True
        candidates = _collect(queries, active_filters, k_vec, k_kw)
        reranked, top_score = rerank_rows(query, candidates, k=max(k, GRADE_POOL), pool=POOL)

    # CRAG closed-corpus fallback: corpus couldn't answer -> try live market news.
    if not confident and NEWS_FALLBACK:
        news = _news_results(query)
        if news:
            scores = _get_reranker().predict([(query, n["chunk_text"]) for n in news])
            for nrow, sc in zip(news, scores):
                nrow["score"] = float(sc)
            top_news = max((n["score"] for n in news), default=0.0)
            trace["news_fallback"] = {"fetched": len(news), "top_score": round(top_news, 3)}
            if top_news >= CONF_THRESHOLD:
                best = sorted(best + news, key=lambda r: r.get("score") or -1.0,
                              reverse=True)[:k]
                confident = True

    trace["confident"] = confident
    trace["returned"] = len(best)
    return best, confident, trace


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "performance for FMCG sector in last 6 months"
    res, ok, tr = agentic_search(q)
    print(f"Q: {q}  (confident={ok})")
    print("subqueries:", tr["subqueries"])
    for step in tr["iterations"]:
        print("  iter", step)
    print("results:")
    for r in res:
        sc = f"{r['score']:+.2f}" if r.get("score") is not None else "  n/a"
        print(f"  {sc}  {r['doc_id']:35} | {r['section']}")
