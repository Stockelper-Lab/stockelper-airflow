"""
DART Disclosure Daily Update DAG
===============================

Daily incremental update:
- Query recent filings with a small lookback buffer
- Store new filings to MongoDB
- Extract event + sentiment via LLM

This DAG should be enabled after the initial backfill has been completed.
"""

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

from modules.common.airflow_settings import get_setting
from modules.common.logging_config import setup_logger
from modules.dart_disclosure.runner import daily_update
from modules.dart_disclosure.universe import load_universe
from modules.neo4j.dart_event_uploader import load_dart_events_to_neo4j

logger = setup_logger(__name__)

NEO4J_CONN_ID = get_setting("NEO4J_CONN_ID", "neo4j_default")
NEO4J_LOOKBACK_DAYS = int(get_setting("DART_NEO4J_UPLOAD_LOOKBACK_DAYS", "7"))

# Optional: separate universe for daily vs backfill
DAILY_UNIVERSE_JSON = get_setting("DART_UNIVERSE_JSON_DAILY") or get_setting(
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


def update(**kwargs):
    run_date = pendulum.now("Asia/Seoul").format("YYYYMMDD")
    logger.info("Starting DART disclosure daily update (run_date=%s)", run_date)
    universe = (
        load_universe(universe_json_path=DAILY_UNIVERSE_JSON) if DAILY_UNIVERSE_JSON else None
    )
    result = daily_update(run_date=run_date, universe=universe) if universe else daily_update(run_date=run_date)
    kwargs["ti"].xcom_push(key="result", value=result)


def upload_neo4j(**kwargs):
    """Upload recently ingested DART events (MongoDB) into Neo4j."""
    today = pendulum.now("Asia/Seoul").date()
    start_date = today.subtract(days=NEO4J_LOOKBACK_DAYS).format("YYYY-MM-DD")
    end_date = today.format("YYYY-MM-DD")

    logger.info(
        "Uploading DART events to Neo4j (conn_id=%s, range=%s..%s)",
        NEO4J_CONN_ID,
        start_date,
        end_date,
    )
    result = load_dart_events_to_neo4j(
        neo4j_conn_id=NEO4J_CONN_ID,
        start_date=start_date,
        end_date=end_date,
    )
    kwargs["ti"].xcom_push(key="neo4j_result", value=result)


def report(**kwargs):
    result = kwargs["ti"].xcom_pull(task_ids="update", key="result")
    neo4j_result = kwargs["ti"].xcom_pull(task_ids="upload_neo4j", key="neo4j_result")
    logger.info("Daily update result: %s", result)
    logger.info("Neo4j upload result: %s", neo4j_result)


with DAG(
    dag_id="dart_disclosure_daily",
    default_args=default_args,
    description="Daily incremental ingestion for DART disclosures",
    schedule="30 0 * * *",  # Daily at 00:30 UTC (09:30 KST)
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    catchup=False,
    tags=["dart", "mongodb", "neo4j", "daily"],
) as dag:
    t_update = PythonOperator(task_id="update", python_callable=update)
    t_upload = PythonOperator(task_id="upload_neo4j", python_callable=upload_neo4j)
    t_report = PythonOperator(task_id="report", python_callable=report)

    t_update >> t_upload >> t_report


