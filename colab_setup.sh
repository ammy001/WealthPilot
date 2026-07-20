#!/usr/bin/env bash
# WealthPilot — Google Colab setup: Ollama + pgvector + Python deps.
# Run in a Colab cell:  !bash colab_setup.sh
# (Start the Ollama server + pull models from a *Python* cell afterwards so it
#  persists for the session — see the notebook cells in the chat.)
set -e

# Never let psql invoke an interactive pager (hangs headless environments like Colab).
export PAGER=cat
export PSQL_PAGER=cat

echo "==================================================================="
echo " 1/4  Python deps (sentence-transformers, psycopg2, pgvector client)"
echo "==================================================================="
pip install -q sentence-transformers psycopg2-binary pgvector requests

echo "==================================================================="
echo " 2/4  Ollama binary (server started separately from a Python cell)"
echo "==================================================================="
# The Ollama installer now extracts a zstd-compressed tarball; Colab lacks zstd.
apt-get -qq update
apt-get -qq install -y zstd >/dev/null
curl -fsSL https://ollama.com/install.sh | sh
ollama --version || true

echo "==================================================================="
echo " 3/4  PostgreSQL + build pgvector from source"
echo "==================================================================="
apt-get -qq update
apt-get -qq install -y postgresql postgresql-contrib build-essential git >/dev/null

# Detect the installed major version (Colab: 14 on 22.04, 16 on 24.04, etc.)
PG_VER="$(ls /usr/lib/postgresql/ | sort -n | tail -1)"
echo "PostgreSQL major version: ${PG_VER}"
apt-get -qq install -y "postgresql-server-dev-${PG_VER}" >/dev/null

# Build + install the pgvector extension.
if [ ! -d /tmp/pgvector ]; then
  git clone --quiet --branch v0.8.0 https://github.com/pgvector/pgvector.git /tmp/pgvector
fi
cd /tmp/pgvector
make -s
make -s install
cd -

echo "==================================================================="
echo " 4/4  Start Postgres, create DB + enable the vector extension"
echo "==================================================================="
service postgresql start
# Give postgres a password and create the WealthPilot DB + extension.
sudo -u postgres psql -v ON_ERROR_STOP=1 <<'SQL'
ALTER USER postgres PASSWORD 'password';
SELECT 'CREATE DATABASE wealthpilot'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'wealthpilot')\gexec
SQL
sudo -u postgres psql -d wealthpilot -v ON_ERROR_STOP=1 -P pager=off -c "CREATE EXTENSION IF NOT EXISTS vector;"
sudo -u postgres psql -d wealthpilot -P pager=off -c "SELECT extversion AS pgvector FROM pg_extension WHERE extname='vector';"

echo
echo "DONE. Postgres DSN:  postgresql://postgres:password@localhost:5432/wealthpilot"
echo "Next: start Ollama + pull models from a Python cell (see notebook)."
