"""Ingest corpus chunks into pgvector.

  build chunks -> embed -> INSERT into wp_chunks (namespaced; hcmp_aiml is shared)
  + HNSW (cosine) index for vector search and GIN index for keyword (hybrid retrieval).

The embedding column width follows EMBED_DIM, so switching embedding models
(e.g. mxbai 1024 -> nomic-embed-text 768) needs no code change — just re-ingest.

Idempotent: drops + rebuilds the table each run. Run:  python -m rag.ingest
"""
import sys
import time

import db
from config import EMBED
from embeddings import embed
from rag.chunk import build_all

# DROP + CREATE so a change in EMBED_DIM re-shapes the vector column cleanly.
DDL = f"""
DROP TABLE IF EXISTS wp_chunks;
CREATE TABLE wp_chunks (
    id          bigserial PRIMARY KEY,
    doc_id      text,
    doc_type    text,
    entity      text,
    title       text,
    section     text,
    chunk_text  text,
    embedding   vector({EMBED['dim']}),
    source      text,
    url         text,
    as_of       date,
    locator     text
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS wp_chunks_embed_idx ON wp_chunks USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS wp_chunks_tsv_idx   ON wp_chunks USING gin (to_tsvector('english', chunk_text))",
    "CREATE INDEX IF NOT EXISTS wp_chunks_entity_idx ON wp_chunks (entity)",
    "CREATE INDEX IF NOT EXISTS wp_chunks_type_idx   ON wp_chunks (doc_type)",
]


def _vlit(vec):
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def main():
    chunks = build_all()
    print(f"built {len(chunks)} chunks; embedding via mxbai ...", flush=True)
    t0 = time.time()
    vecs = embed([c["chunk_text"] for c in chunks], max_workers=3)
    print(f"embedded {len(vecs)} in {time.time()-t0:.0f}s", flush=True)

    conn = db.connect()
    cur = conn.cursor()
    cur.execute(DDL)
    cur.execute("TRUNCATE wp_chunks RESTART IDENTITY")
    rows = [
        (c["doc_id"], c["doc_type"], c["entity"], c["title"], c["section"],
         c["chunk_text"], _vlit(v), c["source"], c["url"], c["as_of"], c["locator"])
        for c, v in zip(chunks, vecs)
    ]
    from psycopg2.extras import execute_batch
    execute_batch(cur, """
        INSERT INTO wp_chunks
          (doc_id, doc_type, entity, title, section, chunk_text, embedding, source, url, as_of, locator)
        VALUES (%s,%s,%s,%s,%s,%s,%s::vector,%s,%s,%s,%s)
    """, rows, page_size=200)
    for ddl in INDEXES:
        cur.execute(ddl)
    conn.commit()

    cur.execute("SELECT count(*), count(distinct doc_id) FROM wp_chunks")
    n, docs = cur.fetchone()
    conn.close()
    print(f"DONE: inserted {n} chunks from {docs} docs into hcmp_aiml.wp_chunks", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
