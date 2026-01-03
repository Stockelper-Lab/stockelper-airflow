"""
DART 36 Major Report Type Collection (Backfill) DAG
===================================================

Purpose:
- One-time / manual backfill for the 36 structured "major report" endpoints for ALL listed companies.
- Store to the SAME PostgreSQL as `daily_stock_price` (Airflow Connection: postgres_default).

Why a separate DAG?
- The daily DAG uses a short lookback window to be safe and idempotent.
- Backfill needs a long historical range and usually runs for a long time.

Airflow Variables:
- OPEN_DART_API_KEY: "<your key>"
- DART36_BACKFILL_YEARS (optional): "20" (default: 20)
- DART36_BACKFILL_END_DATE (optional): "YYYYMMDD" (default: today in Asia/Seoul)
"""

from __future__ import annotations

from datetime import datetime

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

from modules.common.airflow_settings import get_required_setting, get_setting
from modules.common.logging_config import setup_logger

logger = setup_logger(__name__)


def _today_seoul_yyyymmdd() -> str:
    return pendulum.now("Asia/Seoul").format("YYYYMMDD")


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": pendulum.duration(minutes=10),
    # Backfill can be long-running; adjust via Airflow UI if needed.
    "execution_timeout": pendulum.duration(hours=24),
}


def load_universe_template(**context):
    """Load universe template JSON and push it to XCom."""
    import json
    from pathlib import Path

    default_path = (
        "/opt/airflow/stockelper-kg/modules/dart_disclosure/universe.ai-sector.template.json"
    )
    universe_path = get_setting("DART36_UNIVERSE_JSON", default_path)

    path = Path(str(universe_path)).expanduser()
    data = json.loads(path.read_text(encoding="utf-8"))
    stocks = data.get("stocks") or []
    corp_codes = [
        s["corp_code"] for s in stocks if isinstance(s, dict) and s.get("corp_code")
    ]

    ti = context["task_instance"]
    ti.xcom_push(key="universe_path", value=str(path))
    ti.xcom_push(key="corp_codes", value=corp_codes)
    ti.xcom_push(key="universe_size", value=len(corp_codes))

    logger.info("Loaded universe: %s stocks (path=%s)", len(corp_codes), path)
    return len(corp_codes)


def collect_36_major_reports_backfill(**context):
    """Backfill the 36 major report types for ALL listed companies over last N years."""
    from stockelper_kg.collectors.dart_major_reports import DartMajorReportCollector
    from modules.postgres.postgres_connector import get_postgres_engine

    api_key = get_required_setting("OPEN_DART_API_KEY")
    engine = get_postgres_engine(conn_id="postgres_default")

    years = int(get_setting("DART36_BACKFILL_YEARS", "20"))
    end_s = str(get_setting("DART36_BACKFILL_END_DATE", _today_seoul_yyyymmdd()) or _today_seoul_yyyymmdd())
    end_s = end_s.replace("-", "")
    if len(end_s) != 8 or not end_s.isdigit():
        raise ValueError(f"Invalid DART36_BACKFILL_END_DATE: {end_s!r}")

    end_dt = datetime.strptime(end_s, "%Y%m%d")
    start_dt = pendulum.instance(end_dt, tz="Asia/Seoul").subtract(years=years)
    start_s = start_dt.format("YYYYMMDD")

    collector = DartMajorReportCollector(
        api_key=api_key,
        engine=engine,
        sleep_seconds=float(get_setting("DART36_SLEEP_SECONDS", "0.2")),
        timeout_seconds=float(get_setting("DART36_TIMEOUT_SECONDS", "30")),
        max_retries=int(get_setting("DART36_MAX_RETRIES", "3")),
    )

    logger.info(
        "Starting DART 36-type BACKFILL for ALL listed companies (range=%s..%s, years=%s)",
        start_s,
        end_s,
        years,
    )

    result = collector.collect_all_listed_range(start_date=start_s, end_date=end_s)

    # Aggregate inserted counts (best-effort).
    total_inserted = 0
    if isinstance(result, dict):
        for _, per_company in result.items():
            if isinstance(per_company, dict):
                total_inserted += sum(int(v or 0) for v in per_company.values() if isinstance(v, (int, float, str)))

    context["ti"].xcom_push(
        key="backfill_summary",
        value={
            "start_date": start_s,
            "end_date": end_s,
            "years": years,
            "total_inserted_best_effort": total_inserted,
        },
    )
    return True


def report(**context):
    summary = context["ti"].xcom_pull(
        task_ids="collect_36_major_reports_backfill", key="backfill_summary"
    )
    logger.info("Backfill summary: %s", summary)


with DAG(
    dag_id="dart_disclosure_collection_36_types_backfill",
    default_args=default_args,
    description="(BACKFILL) Collect DART 36 major report types for ALL listed companies (Postgres=postgres_default)",
    schedule=None,  # manual trigger
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Seoul"),
    catchup=False,
    tags=["dart", "disclosure", "postgres", "36-types", "backfill"],
) as dag:
    t_collect = PythonOperator(
        task_id="collect_36_major_reports_backfill",
        python_callable=collect_36_major_reports_backfill,
    )
    t_report = PythonOperator(task_id="report", python_callable=report)

    t_collect >> t_report


