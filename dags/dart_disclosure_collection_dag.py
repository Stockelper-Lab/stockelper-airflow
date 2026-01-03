"""
DART 36 Major Report Type Collection DAG
======================================

Updated Strategy (2026-01-03):
- Collect 36 structured "major report" endpoints per company (no generic list/document parsing).
- Store to Local PostgreSQL (NOT remote AWS).
- Run daily at 08:00 KST.
"""

from __future__ import annotations

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

from modules.common.airflow_settings import get_required_setting, get_setting
from modules.common.logging_config import setup_logger

logger = setup_logger(__name__)


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": pendulum.duration(minutes=5),
    "execution_timeout": pendulum.duration(hours=2),
}


def load_universe_template(**context):
    """Load AI-sector universe template JSON and push it to XCom."""
    import json
    from pathlib import Path

    default_path = "/opt/airflow/stockelper-kg/modules/dart_disclosure/universe.ai-sector.template.json"
    universe_path = get_setting("DART36_UNIVERSE_JSON", default_path)

    path = Path(str(universe_path)).expanduser()
    data = json.loads(path.read_text(encoding="utf-8"))
    stocks = data.get("stocks") or []
    corp_codes = [s["corp_code"] for s in stocks if isinstance(s, dict) and s.get("corp_code")]

    ti = context["task_instance"]
    ti.xcom_push(key="universe_path", value=str(path))
    ti.xcom_push(key="corp_codes", value=corp_codes)
    ti.xcom_push(key="universe_size", value=len(corp_codes))

    logger.info("Loaded universe: %s stocks (path=%s)", len(corp_codes), path)
    return len(corp_codes)


def collect_36_major_reports(**context):
    """Collect 36 major report types for universe companies and store to Local PostgreSQL."""
    from stockelper_kg.collectors.dart_major_reports import DartMajorReportCollector

    api_key = get_required_setting("OPEN_DART_API_KEY")
    postgres_conn = get_required_setting("LOCAL_POSTGRES_CONN_STRING")

    lookback_days = int(get_setting("DART36_LOOKBACK_DAYS", "30"))

    ti = context["task_instance"]
    universe_path = ti.xcom_pull(key="universe_path", task_ids="load_universe_template")

    collector = DartMajorReportCollector(
        api_key=api_key,
        postgres_conn_string=postgres_conn,
        sleep_seconds=float(get_setting("DART36_SLEEP_SECONDS", "0.2")),
        timeout_seconds=float(get_setting("DART36_TIMEOUT_SECONDS", "30")),
        max_retries=int(get_setting("DART36_MAX_RETRIES", "3")),
    )

    logger.info("Starting DART 36-type collection (lookback_days=%s)", lookback_days)
    result = collector.collect_universe(
        universe_path=str(universe_path),
        lookback_days=lookback_days,
    )
    ti.xcom_push(key="collect_result", value=result)
    return True


def extract_events(**context):
    """Placeholder (future): Extract events/sentiment from structured disclosures."""
    logger.info("extract_events placeholder - to be implemented")
    return True


def pattern_matching(**context):
    """Placeholder (future): Neo4j pattern matching and user notification."""
    logger.info("pattern_matching placeholder - to be implemented")
    return True


with DAG(
    dag_id="dart_disclosure_collection_36_types",
    default_args=default_args,
    description="Collect DART 36 major report types for AI-sector universe (Local PostgreSQL)",
    schedule="0 8 * * *",  # 08:00 KST
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Seoul"),
    catchup=False,
    tags=["dart", "disclosure", "postgres", "36-types"],
) as dag:
    t_universe = PythonOperator(
        task_id="load_universe_template",
        python_callable=load_universe_template,
    )
    t_collect = PythonOperator(
        task_id="collect_36_major_reports",
        python_callable=collect_36_major_reports,
    )
    t_extract = PythonOperator(
        task_id="extract_events",
        python_callable=extract_events,
    )
    t_match = PythonOperator(
        task_id="pattern_matching",
        python_callable=pattern_matching,
    )

    t_universe >> t_collect >> t_extract >> t_match


