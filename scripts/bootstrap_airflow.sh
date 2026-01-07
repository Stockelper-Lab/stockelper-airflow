#!/usr/bin/env bash
set -euo pipefail

echo "[bootstrap] Starting Airflow bootstrap..."

# -----------------------------
# 0) Environment sanity checks
# -----------------------------
: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_PORT:?POSTGRES_PORT is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"            # main data DB (e.g., postgres)
: "${AIRFLOW_META_DB_NAME:?AIRFLOW_META_DB_NAME is required}"  # airflow metadb (e.g., airflow_meta)

NEO4J_HOST="${NEO4J_HOST:-stockelper-neo4j}"
NEO4J_PORT="${NEO4J_PORT:-7687}"

# ----------------------------------------------------------
# 1) Wait for Postgres to become available (TCP connect test)
# ----------------------------------------------------------
echo "[bootstrap] Waiting for Postgres (${POSTGRES_HOST}:${POSTGRES_PORT})..."
python3 - <<'PY'
import os
import time

import psycopg2

host = os.environ["POSTGRES_HOST"]
port = int(os.environ["POSTGRES_PORT"])
user = os.environ["POSTGRES_USER"]
password = os.environ["POSTGRES_PASSWORD"]
admin_db = os.environ.get("POSTGRES_ADMIN_DB", "postgres")

deadline = time.time() + 300  # 5 min
last_err = None
while time.time() < deadline:
    try:
        conn = psycopg2.connect(host=host, port=port, dbname=admin_db, user=user, password=password)
        conn.close()
        print("[bootstrap] Postgres is ready.")
        raise SystemExit(0)
    except Exception as e:  # noqa: BLE001
        last_err = e
        time.sleep(2)

raise RuntimeError(f"Postgres not ready within timeout: {last_err}")
PY

# -------------------------------------------------------------------
# 2) Ensure Airflow metadata database exists (create if missing)
# -------------------------------------------------------------------
echo "[bootstrap] Ensuring Airflow metadb exists (${AIRFLOW_META_DB_NAME})..."
python3 - <<'PY'
import os

import psycopg2
from psycopg2 import sql

host = os.environ["POSTGRES_HOST"]
port = int(os.environ["POSTGRES_PORT"])
user = os.environ["POSTGRES_USER"]
password = os.environ["POSTGRES_PASSWORD"]
admin_db = os.environ.get("POSTGRES_ADMIN_DB", "postgres")
meta_db = os.environ["AIRFLOW_META_DB_NAME"]

conn = psycopg2.connect(host=host, port=port, dbname=admin_db, user=user, password=password)
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (meta_db,))
exists = cur.fetchone() is not None
if not exists:
    cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(meta_db)))
    print(f"[bootstrap] Created database: {meta_db}")
else:
    print(f"[bootstrap] Database already exists: {meta_db}")
cur.close()
conn.close()
PY

# -------------------------------------------------------------------
# 3) Initialize / migrate Airflow metadata schema
# -------------------------------------------------------------------
echo "[bootstrap] Initializing/migrating Airflow metadb..."
airflow db migrate

# -------------------------------------------------------------------
# 4) Ensure Admin user exists
# -------------------------------------------------------------------
echo "[bootstrap] Ensuring Airflow admin user exists..."
airflow users create \
  --username "${AIRFLOW_ADMIN_USERNAME}" \
  --firstname Admin \
  --lastname User \
  --role Admin \
  --email "${AIRFLOW_ADMIN_EMAIL}" \
  --password "${AIRFLOW_ADMIN_PASSWORD}" \
  || true

# -------------------------------------------------------------------
# 5) Ensure required Connections exist (idempotent)
#    - This avoids 'conn_id ... isn't defined' even if metadb is empty.
# -------------------------------------------------------------------
echo "[bootstrap] Ensuring Airflow Connections exist..."

# Neo4j
airflow connections delete neo4j_default || true
airflow connections add neo4j_default \
  --conn-type neo4j \
  --conn-host "${NEO4J_HOST}" \
  --conn-port "${NEO4J_PORT}" \
  --conn-login "${NEO4J_USER}" \
  --conn-password "${NEO4J_PASSWORD}" \
  || true

# Postgres (data DB for KG loaders)
airflow connections delete postgres_default || true
airflow connections add postgres_default \
  --conn-type postgres \
  --conn-host "${POSTGRES_HOST}" \
  --conn-port "${POSTGRES_PORT}" \
  --conn-login "${POSTGRES_USER}" \
  --conn-password "${POSTGRES_PASSWORD}" \
  --conn-schema "${POSTGRES_DB}" \
  || true

echo "[bootstrap] Starting scheduler + webserver..."
airflow scheduler &
exec airflow webserver


