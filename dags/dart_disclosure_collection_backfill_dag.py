"""
DART 36 Major Report Type Collection (Backfill) DAG
===================================================

Purpose:
- One-time / manual backfill for the 36 structured "major report" endpoints.
- Store to Local PostgreSQL (LOCAL_POSTGRES_CONN_STRING).

Why a separate DAG?
- The daily DAG uses a short lookback window to be safe and idempotent.
- Backfill needs a long historical range and usually runs for a long time.

Airflow Variables (recommended):
- OPEN_DART_API_KEY: "<your key>"
- LOCAL_POSTGRES_CONN_STRING: "postgresql+psycopg2://user:pass@host:port/db?options=-csearch_path%3Dstockelper-fe"

Universe:
- DART36_UNIVERSE_JSON (optional): path to universe JSON
  - default: /opt/airflow/stockelper-kg/modules/dart_disclosure/universe.ai-sector.template.json

Backfill range:
- DART36_BACKFILL_START_DATE (optional): "YYYYMMDD" (default: "20050101")
- DART36_BACKFILL_END_DATE   (optional): "YYYYMMDD" (default: today in Asia/Seoul)

Windowing (recommended for rate-limit resilience):
- DART36_BACKFILL_WINDOW_DAYS (optional): "30" (default: 30)
- DART36_BACKFILL_MAX_WINDOWS (optional): integer string to limit iterations (for testing)
"""

from __future__ import annotations

from datetime import date as _date
from datetime import datetime, timedelta

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

from modules.common.airflow_settings import get_required_setting, get_setting
from modules.common.logging_config import setup_logger

logger = setup_logger(__name__)


def _normalize_yyyymmdd(val: str) -> str:
    s = str(val or "").strip()
    if len(s) == 10 and "-" in s:
        s = s.replace("-", "")
    if len(s) != 8 or not s.isdigit():
        raise ValueError(f"Invalid date (expected YYYYMMDD or YYYY-MM-DD): {val!r}")
    return s


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
    """Backfill the 36 major report types over a historical range (windowed)."""
    from stockelper_kg.collectors.dart_major_reports import DartMajorReportCollector

    api_key = get_required_setting("OPEN_DART_API_KEY")
    postgres_conn = get_required_setting("LOCAL_POSTGRES_CONN_STRING")

    start_s = _normalize_yyyymmdd(get_setting("DART36_BACKFILL_START_DATE", "20050101"))
    end_s = _normalize_yyyymmdd(get_setting("DART36_BACKFILL_END_DATE", _today_seoul_yyyymmdd()))
    window_days = int(get_setting("DART36_BACKFILL_WINDOW_DAYS", "30"))
    max_windows_raw = get_setting("DART36_BACKFILL_MAX_WINDOWS")
    max_windows = int(max_windows_raw) if (max_windows_raw is not None and str(max_windows_raw).strip()) else None

    if window_days <= 0:
        raise ValueError("DART36_BACKFILL_WINDOW_DAYS must be positive")

    start_dt = datetime.strptime(start_s, "%Y%m%d").date()
    end_dt = datetime.strptime(end_s, "%Y%m%d").date()
    if end_dt < start_dt:
        raise ValueError(f"Backfill end_date < start_date: {end_s} < {start_s}")

    ti = context["task_instance"]
    universe_path = ti.xcom_pull(key="universe_path", task_ids="load_universe_template")

    collector = DartMajorReportCollector(
        api_key=api_key,
        postgres_conn_string=postgres_conn,
        sleep_seconds=float(get_setting("DART36_SLEEP_SECONDS", "0.2")),
        timeout_seconds=float(get_setting("DART36_TIMEOUT_SECONDS", "30")),
        max_retries=int(get_setting("DART36_MAX_RETRIES", "3")),
    )

    logger.info(
        "Starting DART 36-type BACKFILL (range=%s..%s, window_days=%s, max_windows=%s)",
        start_s,
        end_s,
        window_days,
        max_windows,
    )

    cur_end: _date = end_dt
    windows_done = 0
    total_inserted = 0

    while cur_end >= start_dt:
        windows_done += 1
        cur_end_s = cur_end.strftime("%Y%m%d")

        logger.info(
            "Backfill window %s: ending at %s (window_days=%s)",
            windows_done,
            cur_end_s,
            window_days,
        )

        result = collector.collect_universe(
            universe_path=str(universe_path),
            lookback_days=window_days,
            end_date=cur_end_s,
        )

        # Aggregate inserted counts for operator logs/XCom (best-effort).
        inserted_this_window = 0
        if isinstance(result, dict):
            for _, per_company in result.items():
                if isinstance(per_company, dict):
                    inserted_this_window += sum(
                        int(v or 0) for v in per_company.values() if isinstance(v, (int, float, str))
                    )

        total_inserted += int(inserted_this_window or 0)
        logger.info(
            "Backfill window %s completed: inserted=%s (cumulative=%s)",
            windows_done,
            inserted_this_window,
            total_inserted,
        )

        if max_windows is not None and windows_done >= max_windows:
            logger.info("Reached max_windows=%s; stopping early.", max_windows)
            break

        # Move the window back. We allow an overlap on the boundary day; duplicates are ignored in DB.
        cur_end = cur_end - timedelta(days=window_days)

    ti.xcom_push(
        key="backfill_summary",
        value={
            "start_date": start_s,
            "end_date": end_s,
            "window_days": window_days,
            "windows_done": windows_done,
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
    description="(BACKFILL) Collect DART 36 major report types for universe (Local PostgreSQL)",
    schedule=None,  # manual trigger
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Seoul"),
    catchup=False,
    tags=["dart", "disclosure", "postgres", "36-types", "backfill"],
) as dag:
    t_universe = PythonOperator(
        task_id="load_universe_template",
        python_callable=load_universe_template,
    )
    t_collect = PythonOperator(
        task_id="collect_36_major_reports_backfill",
        python_callable=collect_36_major_reports_backfill,
    )
    t_report = PythonOperator(task_id="report", python_callable=report)

    t_universe >> t_collect >> t_report


