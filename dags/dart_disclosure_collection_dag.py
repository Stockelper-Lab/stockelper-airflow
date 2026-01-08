"""
DART Major Report Type Collection DAG (Curated endpoints)
========================================================

Updated Strategy (2026-01-03):
- Collect curated(엄선된/선별된) structured "major report" endpoints per company (no generic list/document parsing).
- Store to the SAME PostgreSQL as `daily_stock_price` (Airflow Connection: postgres_default).
- Run daily at 08:00 KST.

UPDATED - 2025-01-06:
- **이벤트 추출(LLM) / 감성지수 파이프라인은 POSTPONED**
- 공시정보의 **카테고리/유형(major-report endpoint) 자체를 Event로 사용**하며,
  Neo4j 적재는 `neo4j_kg_etl_dag`에서 Postgres를 소스로 수행합니다.

Airflow Variables:
- OPEN_DART_API_KEY: "<your key>"
- OPEN_DART_API_KEYS (optional): "key1,key2,..." (comma/whitespace separated). If set, rotates keys on 020.
- DART_CURATED_MAJOR_REPORT_ENDPOINTS (optional): JSON list or comma-separated endpoints to collect.
  If unset, defaults to the curated set defined in this DAG.
- DART_CURATED_UNIVERSE_JSON (optional): path to universe JSON
- DART_CURATED_LOOKBACK_DAYS (optional): lookback days for daily run (alias of DART_CURATED_DAILY_WINDOW_DAYS)
- DART_CURATED_SLEEP_SECONDS (optional): sleep seconds between OpenDART calls (default: 0.2)
- DART_CURATED_TIMEOUT_SECONDS (optional): OpenDART request timeout seconds (default: 30)
- DART_CURATED_MAX_RETRIES (optional): max retries per endpoint (default: 3)

# Daily (curated) collection cursor:
# - DART_CURATED_DAILY_LOCKED_END_DATE (optional): YYYYMMDD. If unset/invalid/blank, auto-initialized to today (Asia/Seoul).
# - DART_CURATED_DAILY_END_DATE (optional): YYYYMMDD or YYYY-MM-DD. If set, always collect this end date (no auto-advance).
# - DART_CURATED_DAILY_START_DATE (optional): YYYYMMDD or YYYY-MM-DD. If set, use as start date.
# - DART_CURATED_DAILY_WINDOW_DAYS (optional): number of days per collection window (default: 3)
# - DART_CURATED_DAILY_CHUNK_SIZE (optional): companies per chunk (default: 500)
# - DART_CURATED_DAILY_MAX_CHUNKS_PER_RUN (optional): 0=무제한(기본), N=최대 N청크만 수행
"""

from __future__ import annotations

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

from modules.common.airflow_settings import get_required_setting, get_setting, get_setting_json
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

# 수집 대상 Major Report 엔드포인트 (엄선된/선별된 세트)
#
# 참고: 실제 엔드포인트 문자열은 OpenDART major report endpoint 이름입니다.
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


def collect_curated_major_reports(**context):
    """Collect curated(엄선된) major report endpoints for ALL listed companies and store to Postgres(postgres_default)."""
    from datetime import datetime

    from airflow.models import Variable
    import re
    from stockelper_kg.collectors.dart_major_reports import DartMajorReportCollector
    from modules.postgres.postgres_connector import get_postgres_engine

    def _normalize_yyyymmdd(raw: object | None) -> str | None:
        s = str(raw).strip() if raw is not None else ""
        if not s:
            return None
        s = s.replace("-", "").replace("/", "")
        if len(s) != 8 or not s.isdigit():
            return None
        return s

    engine = get_postgres_engine(conn_id="postgres_default")
    api_keys_raw = get_setting("OPEN_DART_API_KEYS")
    api_keys = [k for k in re.split(r"[,\s]+", str(api_keys_raw or "").strip()) if k]
    if not api_keys:
        api_keys = [get_required_setting("OPEN_DART_API_KEY")]

    # Default behavior: collect the most recent N days (inclusive).
    # - end_date defaults to TODAY (Asia/Seoul)
    # - start_date is derived unless explicitly configured
    lookback_default = get_setting("DART_CURATED_LOOKBACK_DAYS", "3") or "3"
    daily_window_days = int(
        get_setting("DART_CURATED_DAILY_WINDOW_DAYS", lookback_default) or lookback_default or "3"
    )
    if daily_window_days <= 0:
        logger.warning("Invalid DART_CURATED_DAILY_WINDOW_DAYS=%r; fallback=3", daily_window_days)
        daily_window_days = 3

    configured_start_raw = get_setting("DART_CURATED_DAILY_START_DATE")
    configured_end_raw = get_setting("DART_CURATED_DAILY_END_DATE")
    configured_start = _normalize_yyyymmdd(configured_start_raw)
    configured_end = _normalize_yyyymmdd(configured_end_raw)
    if configured_start_raw and not configured_start:
        logger.warning(
            "Invalid DART_CURATED_DAILY_START_DATE=%r; ignoring and deriving start_date from lookback days.",
            configured_start_raw,
        )
    if configured_end_raw and not configured_end:
        logger.warning(
            "Invalid DART_CURATED_DAILY_END_DATE=%r; ignoring and using auto end_date.",
            configured_end_raw,
        )

    locked_key = "DART_CURATED_DAILY_LOCKED_END_DATE"

    cap_s = pendulum.now("Asia/Seoul").format("YYYYMMDD")

    if configured_end:
        end_s = str(configured_end)
        should_advance_cursor = False
    else:
        should_advance_cursor = True
        try:
            end_s = _normalize_yyyymmdd(Variable.get(locked_key))
        except Exception:  # noqa: BLE001
            end_s = None

        if not end_s:
            end_s = cap_s
            Variable.set(locked_key, end_s)

    # Do not process future dates; clamp to today (Asia/Seoul).
    if end_s and end_s > cap_s:
        end_s = cap_s

    end_dt = datetime.strptime(str(end_s), "%Y%m%d")

    if configured_start:
        start_s = str(configured_start)
    else:
        start_dt = pendulum.instance(end_dt, tz="Asia/Seoul").subtract(days=daily_window_days - 1)
        start_s = start_dt.format("YYYYMMDD")

    if start_s > str(end_s):
        logger.warning(
            "Derived start_date=%s is after end_date=%s; clamping start_date=end_date",
            start_s,
            end_s,
        )
        start_s = str(end_s)

    # Chunking (same style as backfill)
    chunk_size = int(get_setting("DART_CURATED_DAILY_CHUNK_SIZE", "500") or "500")
    max_chunks_per_run = int(get_setting("DART_CURATED_DAILY_MAX_CHUNKS_PER_RUN", "0") or "0")

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

    priority_universe_path = get_setting(
        "DART_CURATED_UNIVERSE_JSON",
        "/opt/airflow/modules/dart_disclosure/universe.ai-sector.template.json",
    )

    logger.info(
        "Starting DART curated DAILY collection (types=%s, range=%s..%s, window_days=%s, chunk_size=%s, max_chunks_per_run=%s)",
        len(report_types) if isinstance(report_types, list) else "custom",
        start_s,
        end_s,
        daily_window_days,
        chunk_size,
        max_chunks_per_run,
    )

    total_processed = 0
    total_inserted = 0
    chunks_ran = 0
    stopped_reason: str | None = None
    last_processed_count = 0

    while True:
        chunks_ran += 1
        result = collector.collect_backfill_chunk(
            start_date=start_s,
            end_date=end_s,
            chunk_size=chunk_size,
            priority_universe_path=str(priority_universe_path) if priority_universe_path else None,
        )

        if not isinstance(result, dict):
            stopped_reason = "invalid_result"
            break

        last_processed_count = int(result.get("processed_count") or 0)
        total_processed += last_processed_count
        total_inserted += int(result.get("inserted_total") or 0)
        stopped_reason = result.get("stopped_reason")

        if stopped_reason:
            break
        if last_processed_count < int(chunk_size):
            # No more incomplete companies for this range
            break
        if max_chunks_per_run > 0 and chunks_ran >= max_chunks_per_run:
            stopped_reason = "max_chunks_reached"
            break

    # Cursor advance when fully completed for the date range
    if should_advance_cursor and stopped_reason is None and last_processed_count < int(chunk_size):
        # Advance cursor by 1 day; next run will clamp to today if it is in the future.
        next_dt = pendulum.instance(end_dt, tz="Asia/Seoul").add(days=1)
        Variable.set(locked_key, next_dt.format("YYYYMMDD"))

    result_summary = {
        "start_date": start_s,
        "end_date": end_s,
        "window_days": daily_window_days,
        "chunk_size": int(chunk_size),
        "chunks_ran": int(chunks_ran),
        "processed_count": int(total_processed),
        "stopped_reason": stopped_reason,
        "inserted_total": int(total_inserted),
    }
    # Keep XCom small: store only summary (avoid per_company payload explosion).
    context["ti"].xcom_push(key="collect_result", value=result_summary)
    return True


with DAG(
    dag_id="dart_disclosure_collection_curated_major_reports",
    default_args=default_args,
    description="Collect curated(엄선된) DART major-report endpoints for ALL listed companies (Postgres=postgres_default)",
    schedule="0 8 * * *",  # 08:00 KST
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Seoul"),
    catchup=False,
    tags=["dart", "disclosure", "postgres", "curated-major-reports"],
) as dag:
    t_collect = PythonOperator(
        task_id="collect_curated_major_reports",
        python_callable=collect_curated_major_reports,
        # Daily collection may iterate multiple 500-sized chunks; allow long runs.
        execution_timeout=pendulum.duration(hours=24),
    )

    # NOTE:
    # - LLM 기반 이벤트 추출/감성 분석은 2025-01-06 회의 이후 POSTPONED.
    # - 공시 카테고리(Event)는 Neo4j KG ETL DAG에서 적재한다.
    t_collect


