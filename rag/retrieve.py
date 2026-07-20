"""Hybrid retrieval: vector + keyword, fused with RRF, reranked, gated.

Flow:  query
   -> vector search (pgvector cosine, HNSW)      top k_vec
   -> keyword search (Postgres full-text, GIN)   top k_kw
   -> Reciprocal Rank Fusion (RRF)               merged candidates
   -> cross-encoder rerank (bge-reranker-v2-m3)  precise order
   -> confidence gate                            abstain if weak

search() returns (results, confident). Each result: doc_id, entity, title,
section, chunk_text, source, as_of, locator, score.
"""
import os

import db
from embeddings import embed_one

RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
CONF_THRESHOLD = float(os.getenv("RAG_CONF_THRESHOLD", "0.02"))  # min top rerank score (tune)
RRF_K = 60

_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder(RERANKER_MODEL, max_length=512)
    return _reranker


def _vlit(vec):
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def _filters_sql(filters):
    if not filters:
        return "", []
    clauses, params = [], []
    if filters.get("entity"):
        clauses.append("entity = %s")
        params.append(filters["entity"])
    if filters.get("doc_type"):
        clauses.append("doc_type = %s")
        params.append(filters["doc_type"])
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _vector_search(cur, qvec, k, filters):
    where, params = _filters_sql(filters)
    cur.execute(
        f"""SELECT id, doc_id, entity, title, section, chunk_text, source, as_of, locator
            FROM wp_chunks {where}
            ORDER BY embedding <=> %s::vector LIMIT %s""",
        params + [qvec, k],
    )
    return cur.fetchall()


def _keyword_search(cur, query, k, filters):
    where, params = _filters_sql(filters)
    joiner = " AND " if where else " WHERE "
    cur.execute(
        f"""SELECT id, doc_id, entity, title, section, chunk_text, source, as_of, locator
            FROM wp_chunks {where}{joiner}
                 to_tsvector('english', chunk_text) @@ websearch_to_tsquery('english', %s)
            ORDER BY ts_rank(to_tsvector('english', chunk_text),
                             websearch_to_tsquery('english', %s)) DESC
            LIMIT %s""",
        params + [query, query, k],
    )
    return cur.fetchall()


def _rrf(*ranked_lists, k=RRF_K):
    """Fuse ranked lists of rows (row[0]=id) by Reciprocal Rank Fusion."""
    scores, rows = {}, {}
    for lst in ranked_lists:
        for rank, row in enumerate(lst):
            rid = row[0]
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank + 1)
            rows[rid] = row
    order = sorted(scores, key=lambda r: scores[r], reverse=True)
    return [rows[r] for r in order]


def _row_to_dict(row, score=None):
    _id, doc_id, entity, title, section, text, source, as_of, locator = row
    return dict(doc_id=doc_id, entity=entity, title=title, section=section,
                chunk_text=text, source=source, as_of=str(as_of) if as_of else None,
                locator=locator, score=score)


def fuse_candidates(query, filters=None, k_vec=20, k_kw=20):
    """Hybrid vector+keyword candidates for ONE query, fused by RRF. Returns raw rows
    (row[0]=id). Exposed so the agentic layer can fuse across many reformulations."""
    conn = db.connect()
    cur = conn.cursor()
    try:
        qvec = _vlit(embed_one(query))
        vec_rows = _vector_search(cur, qvec, k_vec, filters)
        kw_rows = _keyword_search(cur, query, k_kw, filters)
    finally:
        conn.close()
    return _rrf(vec_rows, kw_rows)


def rerank_rows(query, rows, k=6, pool=30):
    """Cross-encoder rerank raw rows against `query`. Returns (list[dict], top_score)."""
    if not rows:
        return [], 0.0
    cands = rows[:pool]
    reranker = _get_reranker()
    raw = reranker.predict([(query, r[5]) for r in cands])
    scored = sorted(zip(cands, raw), key=lambda x: x[1], reverse=True)
    top = [_row_to_dict(r, float(s)) for r, s in scored[:k]]
    return top, float(scored[0][1]) if scored else 0.0


def search(query, k=6, filters=None, k_vec=20, k_kw=20, rerank=True):
    """Return (results, confident)."""
    fused = fuse_candidates(query, filters, k_vec, k_kw)
    if not fused:
        return [], False
    if not rerank:
        return [_row_to_dict(r) for r in fused[:k]], True
    top, top_score = rerank_rows(query, fused, k=k)
    return top, top_score >= CONF_THRESHOLD


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "how has the IT sector performed this year"
    res, ok = search(q)
    print(f"Q: {q}  (confident={ok})")
    for r in res:
        print(f"  {r['score']:+.2f}  {r['doc_id']:30} | {r['section']}")
