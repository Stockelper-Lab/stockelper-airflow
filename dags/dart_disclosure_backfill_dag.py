"""
DART Disclosure Backfill DAG
===========================

Initial one-time backfill:
- From each stock's listing date (or fallback) to today
- Fetch filings + documents from OpenDART
- Store raw filings to MongoDB
- Extract ontology-aligned event + sentiment (LLM) and store to MongoDB

NOTE:
- This DAG is intended to be triggered manually (no schedule).
"""

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

from modules.common.airflow_settings import get_setting
from modules.common.logging_config import setup_logger
from modules.dart_disclosure.runner import bulk_backfill
from modules.dart_disclosure.universe import load_universe
from modules.neo4j.dart_event_uploader import load_dart_events_to_neo4j

logger = setup_logger(__name__)

NEO4J_CONN_ID = get_setting("NEO4J_CONN_ID", "neo4j_default")
NEO4J_BACKFILL_START_DATE = get_setting("DART_NEO4J_BACKFILL_START_DATE")  # YYYY-MM-DD
NEO4J_BACKFILL_END_DATE = get_setting("DART_NEO4J_BACKFILL_END_DATE")  # YYYY-MM-DD
NEO4J_BACKFILL_LIMIT = get_setting("DART_NEO4J_BACKFILL_LIMIT")  # optional int

# Optional: separate universe for backfill vs daily
BACKFILL_UNIVERSE_JSON = get_setting("DART_UNIVERSE_JSON_BACKFILL") or get_setting(
    "DART_UNIVERSE_JSON"
)


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": pendulum.duration(minutes=10),
}


def backfill(**kwargs):
    logger.info("Starting DART disclosure bulk backfill")
    universe = (
        load_universe(universe_json_path=BACKFILL_UNIVERSE_JSON)
        if BACKFILL_UNIVERSE_JSON
        else None
    )
    result = bulk_backfill(universe=universe) if universe else bulk_backfill()
    kwargs["ti"].xcom_push(key="result", value=result)


def upload_neo4j(**kwargs):
    """After backfill, optionally load DART events into Neo4j (idempotent MERGE)."""
    limit = int(NEO4J_BACKFILL_LIMIT) if NEO4J_BACKFILL_LIMIT else None
    logger.info(
        "Uploading DART events to Neo4j after backfill (conn_id=%s, range=%s..%s, limit=%s)",
        NEO4J_CONN_ID,
        NEO4J_BACKFILL_START_DATE,
        NEO4J_BACKFILL_END_DATE,
        limit,
    )
    result = load_dart_events_to_neo4j(
        neo4j_conn_id=NEO4J_CONN_ID,
        start_date=NEO4J_BACKFILL_START_DATE,
        end_date=NEO4J_BACKFILL_END_DATE,
        limit=limit,
    )
    kwargs["ti"].xcom_push(key="neo4j_result", value=result)


def report(**kwargs):
    result = kwargs["ti"].xcom_pull(task_ids="backfill", key="result")
    neo4j_result = kwargs["ti"].xcom_pull(task_ids="upload_neo4j", key="neo4j_result")
    logger.info("Backfill result: %s", result)
    logger.info("Neo4j upload result: %s", neo4j_result)


with DAG(
    dag_id="dart_disclosure_backfill",
    default_args=default_args,
    description="One-time bulk backfill for DART disclosures",
    schedule=None,  # manual trigger
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    catchup=False,
    tags=["dart", "mongodb", "neo4j", "backfill"],
) as dag:
    t_backfill = PythonOperator(task_id="backfill", python_callable=backfill)
    t_upload = PythonOperator(task_id="upload_neo4j", python_callable=upload_neo4j)
    t_report = PythonOperator(task_id="report", python_callable=report)

    t_backfill >> t_upload >> t_report


