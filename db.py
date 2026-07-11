"""Postgres / pgvector connection helper."""
import psycopg2

from config import PG


def connect():
    return psycopg2.connect(**PG)


def ensure_vector_extension(conn):
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    conn.commit()
