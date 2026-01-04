"""
DART Major Report Type Collection (Backfill) DAG (Curated endpoints)
====================================================================

Purpose:
- Chunked backfill (default 500 companies per run) for selected structured "major report" endpoints.
- Prioritize the Airflow universe JSON first, then continue with all other listed companies.
- Store to the SAME PostgreSQL as `daily_stock_price` (Airflow Connection: postgres_default).

Why a separate DAG?
- The daily DAG uses a short lookback window to be safe and idempotent.
- Backfill needs a long historical range and usually runs for a long time.

Airflow Variables:
- OPEN_DART_API_KEY: "<your key>"
- OPEN_DART_API_KEYS (optional): "key1,key2,..." (comma/whitespace separated). If set, rotates keys on 020.
- DART_CURATED_BACKFILL_YEARS (optional): "20" (default: 20)
- DART_CURATED_BACKFILL_END_DATE (optional): "YYYYMMDD" (default: today in Asia/Seoul)
- DART_CURATED_BACKFILL_CHUNK_SIZE (optional): "500" (default: 500)
- DART_CURATED_UNIVERSE_JSON (optional): path to priority universe JSON (processed first)
- DART_CURATED_MAJOR_REPORT_ENDPOINTS (optional): JSON list or comma-separated endpoints to collect.
  If unset, defaults to the curated set defined in this DAG.
- DART_CURATED_SLEEP_SECONDS (optional): sleep seconds between OpenDART calls (default: 0.2)
- DART_CURATED_TIMEOUT_SECONDS (optional): OpenDART request timeout seconds (default: 30)
- DART_CURATED_MAX_RETRIES (optional): max retries per endpoint (default: 3)
"""

from __future__ import annotations

from datetime import datetime

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

from modules.common.airflow_settings import get_required_setting, get_setting, get_setting_json
from modules.common.logging_config import setup_logger

logger = setup_logger(__name__)


def _today_seoul_yyyymmdd() -> str:
    return pendulum.now("Asia/Seoul").format("YYYYMMDD")


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    # If we hit OpenDART limit(020), retrying soon is pointless; wait a day.
    "retry_delay": pendulum.duration(hours=24),
    # Backfill can be long-running; adjust via Airflow UI if needed.
    "execution_timeout": pendulum.duration(hours=24),
}

# 수집 대상 Major Report 엔드포인트 (엄선된/선별된 세트)
DEFAULT_MAJOR_REPORT_ENDPOINTS: list[str] = [
    "piicDecsn",  # 유상증자 결정
    "fricDecsn",  # 무상증자 결정
    "pifricDecsn",  # 유무상증자 결정
    "crDecsn",  # 감자 결정
    "cvbdIsDecsn",  # 전환사채권 발행결정
    "bdwtIsDecsn",  # 신주인수권부사채권 발행결정
    "tsstkAqDecsn",  # 자기주식 취득 결정
    "tsstkDpDecsn",  # 자기주식 처분 결정
    "tsstkAqTrctrCnsDecsn",  # 자기주식취득 신탁계약 체결 결정
    "tsstkAqTrctrCcDecsn",  # 자기주식취득 신탁계약 해지 결정
    "bsnInhDecsn",  # 영업양수 결정
    "bsnTrfDecsn",  # 영업양도 결정
    "tgastInhDecsn",  # 유형자산 양수 결정
    "tgastTrfDecsn",  # 유형자산 양도 결정
    "otcprStkInvscrInhDecsn",  # 타법인 주식 및 출자증권 양수결정
    "otcprStkInvscrTrfDecsn",  # 타법인 주식 및 출자증권 양도결정
    "cmpMgDecsn",  # 회사합병 결정
    "cmpDvDecsn",  # 회사분할 결정
    "cmpDvmgDecsn",  # 회사분할합병 결정
    "stkExtrDecsn",  # 주식교환·이전 결정
]


def load_universe_template(**context):
    """Load universe template JSON and push it to XCom."""
    import json
    from pathlib import Path

    default_path = (
        "/opt/airflow/modules/dart_disclosure/universe.ai-sector.template.json"
    )
    universe_path = get_setting("DART_CURATED_UNIVERSE_JSON", default_path)

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


def collect_curated_major_reports_backfill(**context):
    """Backfill curated(엄선된) major report endpoints in daily chunks (default 500 companies)."""
    from airflow.models import Variable
    import re
    from stockelper_kg.collectors.dart_major_reports import DartMajorReportCollector
    from modules.postgres.postgres_connector import get_postgres_engine

    engine = get_postgres_engine(conn_id="postgres_default")
    api_keys_raw = get_setting("OPEN_DART_API_KEYS")
    api_keys = [k for k in re.split(r"[,\s]+", str(api_keys_raw or "").strip()) if k]
    if not api_keys:
        api_keys = [get_required_setting("OPEN_DART_API_KEY")]

    years = int(get_setting("DART_CURATED_BACKFILL_YEARS", "20") or "20")
    # IMPORTANT:
    # - This DAG runs daily. If end_date moves every day, progress keys change and you'll re-run forever.
    # - If user didn't set DART_CURATED_BACKFILL_END_DATE, freeze it once in Airflow Variable.
    locked_key = "DART_CURATED_BACKFILL_LOCKED_END_DATE"
    configured_end = get_setting("DART_CURATED_BACKFILL_END_DATE")
    if configured_end:
        end_s = str(configured_end)
    else:
        try:
            end_s = str(Variable.get(locked_key))
        except Exception:  # noqa: BLE001
            end_s = _today_seoul_yyyymmdd()
            Variable.set(locked_key, end_s)

    end_s = end_s.replace("-", "")
    if len(end_s) != 8 or not end_s.isdigit():
        raise ValueError(f"Invalid DART_CURATED_BACKFILL_END_DATE: {end_s!r}")

    end_dt = datetime.strptime(end_s, "%Y%m%d")
    start_dt = pendulum.instance(end_dt, tz="Asia/Seoul").subtract(years=years)
    start_s = start_dt.format("YYYYMMDD")

    chunk_size = int(get_setting("DART_CURATED_BACKFILL_CHUNK_SIZE", "500") or "500")
    # Priority universe: start with this file first, then continue with other listed companies.
    priority_universe_path = get_setting(
        "DART_CURATED_UNIVERSE_JSON",
        "/opt/airflow/modules/dart_disclosure/universe.ai-sector.template.json",
    )

    report_types = get_setting_json("DART_CURATED_MAJOR_REPORT_ENDPOINTS", default=None)
    if not report_types:
        report_types = get_setting_json("DART_MAJOR_REPORT_ENDPOINTS", default=DEFAULT_MAJOR_REPORT_ENDPOINTS)

    collector = DartMajorReportCollector(
        api_keys=api_keys,
        engine=engine,
        sleep_seconds=float(get_setting("DART_CURATED_SLEEP_SECONDS", "0.2") or "0.2"),
        timeout_seconds=float(get_setting("DART_CURATED_TIMEOUT_SECONDS", "30") or "30"),
        max_retries=int(get_setting("DART_CURATED_MAX_RETRIES", "3") or "3"),
        report_types=report_types,
    )

    logger.info(
        "Starting DART major-report BACKFILL CHUNK (types=%s, chunk_size=%s, priority_universe=%s, range=%s..%s, years=%s)",
        len(report_types) if isinstance(report_types, list) else "custom",
        chunk_size,
        priority_universe_path,
        start_s,
        end_s,
        years,
    )

    result = collector.collect_backfill_chunk(
        start_date=start_s,
        end_date=end_s,
        chunk_size=chunk_size,
        priority_universe_path=str(priority_universe_path) if priority_universe_path else None,
    )

    total_inserted = int(result.get("inserted_total") or 0) if isinstance(result, dict) else 0

    context["ti"].xcom_push(
        key="backfill_summary",
        value={
            "start_date": start_s,
            "end_date": end_s,
            "years": years,
            "chunk_size": chunk_size,
            "priority_universe_path": str(priority_universe_path),
            "processed_count": int(result.get("processed_count") or 0) if isinstance(result, dict) else None,
            "stopped_reason": result.get("stopped_reason") if isinstance(result, dict) else None,
            "total_inserted_best_effort": total_inserted,
        },
    )
    return True


def report(**context):
    summary = context["ti"].xcom_pull(
        task_ids="collect_curated_major_reports_backfill", key="backfill_summary"
    )
    logger.info("Backfill summary: %s", summary)


with DAG(
    dag_id="dart_disclosure_collection_curated_major_reports_backfill",
    default_args=default_args,
    description="(BACKFILL) Collect curated(엄선된) DART major-report endpoints for ALL listed companies (Postgres=postgres_default)",
    schedule="@daily",  # run once per day (24h interval) to respect OpenDART daily limits
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Seoul"),
    catchup=False,
    max_active_runs=1,
    tags=["dart", "disclosure", "postgres", "curated-major-reports", "backfill"],
) as dag:
    t_collect = PythonOperator(
        task_id="collect_curated_major_reports_backfill",
        python_callable=collect_curated_major_reports_backfill,
    )
    t_report = PythonOperator(task_id="report", python_callable=report)

    t_collect >> t_report


