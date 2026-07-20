"""Postgres / pgvector connection helper.

Uses PG_DSN if set (else assembles from PG_* parts) and sets search_path to
PG_SCHEMA so all objects live in the project schema (e.g. hcmp_aiml).
"""
import psycopg2
from psycopg2 import sql

import config


def connect():
    conn = psycopg2.connect(config.PG_DSN) if config.PG_DSN else psycopg2.connect(**config.PG)
    if config.PG_SCHEMA and config.PG_SCHEMA != "public":
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SET search_path TO {}, public").format(
                    sql.Identifier(config.PG_SCHEMA)
                )
            )
        conn.commit()
    return conn


def vector_extension_version(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT extversion FROM pg_extension WHERE extname='vector';")
        row = cur.fetchone()
    return row[0] if row else None


def ensure_vector_extension(conn):
    """Create the vector extension if absent (needs privilege). No-op if present."""
    if vector_extension_version(conn) is None:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        conn.commit()
