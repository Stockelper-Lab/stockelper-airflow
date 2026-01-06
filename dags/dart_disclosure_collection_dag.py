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
- DART_CURATED_LOOKBACK_DAYS (optional): lookback days for daily run
- DART_CURATED_SLEEP_SECONDS (optional): sleep seconds between OpenDART calls (default: 0.2)
- DART_CURATED_TIMEOUT_SECONDS (optional): OpenDART request timeout seconds (default: 30)
- DART_CURATED_MAX_RETRIES (optional): max retries per endpoint (default: 3)

# Daily (curated) collection cursor:
# - DART_CURATED_DAILY_LOCKED_END_DATE (optional): YYYYMMDD. If unset, auto-initialized to yesterday (Asia/Seoul).
# - DART_CURATED_DAILY_END_DATE (optional): YYYYMMDD. If set, always collect this date range (no auto-advance).
# - DART_CURATED_DAILY_WINDOW_DAYS (optional): number of days per collection window (default: 1)
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


def load_universe_template(**context):
    """Load AI-sector universe template JSON (used for event/sentiment extraction only)."""
    import json
    from pathlib import Path

    default_path = "/opt/airflow/stockelper-kg/modules/dart_disclosure/universe.ai-sector.template.json"
    universe_path = get_setting("DART_CURATED_UNIVERSE_JSON", default_path)

    path = Path(str(universe_path)).expanduser()
    data = json.loads(path.read_text(encoding="utf-8"))
    stocks = data.get("stocks") or []
    corp_codes = [s["corp_code"] for s in stocks if isinstance(s, dict) and s.get("corp_code")]
    stock_codes = [
        str(s.get("stock_code") or "").strip().zfill(6)
        for s in stocks
        if isinstance(s, dict) and s.get("stock_code")
    ]
    stock_codes = [c for c in stock_codes if c.isdigit() and len(c) == 6]

    ti = context["task_instance"]
    ti.xcom_push(key="universe_path", value=str(path))
    ti.xcom_push(key="corp_codes", value=corp_codes)
    ti.xcom_push(key="stock_codes", value=stock_codes)
    ti.xcom_push(key="universe_size", value=len(corp_codes))

    logger.info("Loaded universe: %s stocks (path=%s)", len(corp_codes), path)
    return len(corp_codes)


def collect_curated_major_reports(**context):
    """Collect curated(엄선된) major report endpoints for ALL listed companies and store to Postgres(postgres_default)."""
    from datetime import datetime

    from airflow.models import Variable
    import re
    from stockelper_kg.collectors.dart_major_reports import DartMajorReportCollector
    from modules.postgres.postgres_connector import get_postgres_engine

    engine = get_postgres_engine(conn_id="postgres_default")
    api_keys_raw = get_setting("OPEN_DART_API_KEYS")
    api_keys = [k for k in re.split(r"[,\s]+", str(api_keys_raw or "").strip()) if k]
    if not api_keys:
        api_keys = [get_required_setting("OPEN_DART_API_KEY")]

    # Daily cursor window (default: yesterday only)
    daily_window_days = int(get_setting("DART_CURATED_DAILY_WINDOW_DAYS", "1") or "1")
    if daily_window_days <= 0:
        raise ValueError(f"Invalid DART_CURATED_DAILY_WINDOW_DAYS: {daily_window_days!r}")

    configured_end = get_setting("DART_CURATED_DAILY_END_DATE")
    locked_key = "DART_CURATED_DAILY_LOCKED_END_DATE"

    cap_s = pendulum.now("Asia/Seoul").subtract(days=1).format("YYYYMMDD")

    if configured_end:
        end_s = str(configured_end)
        should_advance_cursor = False
    else:
        should_advance_cursor = True
        try:
            end_s = str(Variable.get(locked_key))
        except Exception:  # noqa: BLE001
            end_s = cap_s
            Variable.set(locked_key, end_s)

    end_s = end_s.replace("-", "")
    if len(end_s) != 8 or not end_s.isdigit():
        raise ValueError(f"Invalid daily end date: {end_s!r} (expected YYYYMMDD)")

    # Do not process future dates; clamp to yesterday (Asia/Seoul).
    if end_s > cap_s:
        end_s = cap_s

    end_dt = datetime.strptime(end_s, "%Y%m%d")
    start_dt = pendulum.instance(end_dt, tz="Asia/Seoul").subtract(days=daily_window_days - 1)
    start_s = start_dt.format("YYYYMMDD")

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
        # Advance cursor by 1 day; next run will clamp to yesterday if it is in the future.
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


def extract_events(**context):
    """Extract events/sentiment for UNIVERSE stocks only and store to Postgres(postgres_default)."""
    import json as _json
    from datetime import datetime, timedelta

    from sqlalchemy import text

    from modules.postgres.postgres_connector import get_postgres_engine
    from modules.dart_disclosure.llm_extractor import OpenAIEventExtractor
    from modules.dart_disclosure.opendart_api import (
        OpenDartApiClient,
        build_dart_viewer_url,
        document_xml_to_text,
        normalize_iso_date,
    )

    ti = context["ti"]
    stock_codes: list[str] = ti.xcom_pull(key="stock_codes", task_ids="load_universe_template") or []
    stock_codes = [str(c).strip().zfill(6) for c in stock_codes if str(c).strip()]
    stock_codes = [c for c in stock_codes if c.isdigit() and len(c) == 6]

    if not stock_codes:
        logger.warning("No universe stock_codes loaded; skipping extract_events.")
        return True

    # Extract window: default last 3 days (overridable)
    lookback_days = int(get_setting("DART_EVENT_LOOKBACK_DAYS", "3"))
    end_dt = pendulum.now("Asia/Seoul").date()
    start_dt = end_dt - timedelta(days=lookback_days)

    engine = get_postgres_engine(conn_id="postgres_default")

    # Output table (same DB as daily_stock_price)
    ddl = """
    CREATE TABLE IF NOT EXISTS dart_event_extractions (
      rcept_no TEXT PRIMARY KEY,
      stock_code VARCHAR(6) NOT NULL,
      corp_code VARCHAR(8),
      corp_name TEXT,
      rcept_dt DATE,
      report_type TEXT,
      category TEXT,
      event_type TEXT NOT NULL,
      sentiment_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
      summary TEXT,
      required_slots JSONB,
      optional_slots JSONB,
      source_url TEXT,
      extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_dart_event_extractions_stock_date ON dart_event_extractions(stock_code, rcept_dt);
    CREATE INDEX IF NOT EXISTS idx_dart_event_extractions_event_type ON dart_event_extractions(event_type);
    """

    with engine.begin() as conn:
        for stmt in ddl.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s))

    # Map report_type/category -> ontology event_type hint (kept consistent with llm_extractor)
    def _event_type_hint(report_type: str | None, category: str | None) -> str:
        rt = (report_type or "").strip()
        cat = (category or "").strip()

        # Special cases
        if rt == "crDecsn":
            return "CAPITAL_STRUCTURE_CHANGE"
        if rt in {"cmpDvDecsn", "cmpDvmgDecsn"}:
            return "STRATEGY_SPINOFF"

        if cat in {"증자감자", "사채발행"}:
            return "CAPITAL_RAISE"
        if cat == "자기주식":
            return "CAPITAL_RETURN"
        if cat in {"영업양수도", "자산양수도", "타법인주식", "사채권양수도", "합병분할"}:
            return "STRATEGY_MNA"
        if cat in {"해외상장"}:
            return "LISTING_STATUS_CHANGE"
        if cat in {"소송"}:
            return "LEGAL_LITIGATION"
        if cat in {"기업상태", "채권은행"}:
            # includes default/rehabilitation/bankruptcy etc.
            return "CRISIS_EVENT"
        return "OTHER"

    # Find major-report tables (dart_*) and pick universe rows in window, excluding already extracted.
    # NOTE: Skip non-report tables (e.g., progress tables) by requiring expected columns.
    with engine.begin() as conn:
        tbl_rows = conn.execute(
            text(
                """
                SELECT t.table_name
                FROM information_schema.tables t
                WHERE t.table_schema='public'
                  AND t.table_name LIKE 'dart_%'
                  AND t.table_name <> 'dart_event_extractions'
                  AND EXISTS (
                    SELECT 1 FROM information_schema.columns c
                    WHERE c.table_schema='public' AND c.table_name=t.table_name AND c.column_name='rcept_no'
                  )
                  AND EXISTS (
                    SELECT 1 FROM information_schema.columns c
                    WHERE c.table_schema='public' AND c.table_name=t.table_name AND c.column_name='rcept_dt'
                  )
                  AND EXISTS (
                    SELECT 1 FROM information_schema.columns c
                    WHERE c.table_schema='public' AND c.table_name=t.table_name AND c.column_name='report_type'
                  )
                  AND EXISTS (
                    SELECT 1 FROM information_schema.columns c
                    WHERE c.table_schema='public' AND c.table_name=t.table_name AND c.column_name='category'
                  )
                  AND EXISTS (
                    SELECT 1 FROM information_schema.columns c
                    WHERE c.table_schema='public' AND c.table_name=t.table_name AND c.column_name='stock_code'
                  )
                ORDER BY t.table_name
                """
            )
        ).fetchall()

    table_names = [r[0] for r in tbl_rows]
    if not table_names:
        logger.warning("No dart_* tables found in Postgres; skipping extract_events.")
        return True

    api_key = get_required_setting("OPEN_DART_API_KEY")
    dart = OpenDartApiClient(
        api_key=api_key,
        sleep_seconds=float(get_setting("DART_CURATED_SLEEP_SECONDS", "0.2") or "0.2"),
    )
    extractor = OpenAIEventExtractor(timeout_seconds=float(get_setting("DART_EVENT_TIMEOUT_SECONDS", "60")))

    inserted = 0
    skipped = 0

    for table_name in table_names:
        q = text(
            f"""
            SELECT t.rcept_no, t.stock_code, t.corp_code, t.corp_name, t.rcept_dt, t.report_type, t.category
            FROM {table_name} t
            WHERE t.stock_code = ANY(:stock_codes)
              AND t.rcept_dt >= :start_dt
              AND t.rcept_dt <= :end_dt
              AND NOT EXISTS (
                SELECT 1 FROM dart_event_extractions e WHERE e.rcept_no = t.rcept_no
              )
            ORDER BY t.rcept_dt ASC
            """
        )

        with engine.begin() as conn:
            rows = conn.execute(
                q,
                {"stock_codes": stock_codes, "start_dt": start_dt, "end_dt": end_dt},
            ).fetchall()

        for r in rows:
            rcept_no = str(r[0])
            stock_code = str(r[1]).zfill(6)
            corp_code = str(r[2] or "").strip() or None
            corp_name = str(r[3] or "").strip() or None
            rcept_dt = r[4]
            report_type = str(r[5] or "").strip() or None
            category = str(r[6] or "").strip() or None

            hint = _event_type_hint(report_type, category)
            url = build_dart_viewer_url(rcept_no)
            # OpenDART uses YYYYMMDD for rcept_dt; our table is DATE already.
            rcept_dt_str = rcept_dt.strftime("%Y%m%d") if rcept_dt else ""
            reported_iso = normalize_iso_date(rcept_dt_str) if rcept_dt_str else pendulum.now("Asia/Seoul").format("YYYY-MM-DD")

            try:
                doc_xml = dart.fetch_document_xml(rcept_no=rcept_no)
                body_text = document_xml_to_text(doc_xml)
                extracted = extractor.extract(
                    corp_name=corp_name or stock_code,
                    stock_code=stock_code,
                    report_nm=report_type or (category or "DART_MAJOR_REPORT"),
                    rcept_dt=rcept_dt_str,
                    url=url,
                    body_text=body_text,
                    event_type_hint=hint,
                    reported_date_iso=reported_iso,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Event extraction failed for rcept_no=%s: %s", rcept_no, exc)
                skipped += 1
                continue

            params = {
                "rcept_no": rcept_no,
                "stock_code": stock_code,
                "corp_code": corp_code,
                "corp_name": corp_name,
                "rcept_dt": rcept_dt,
                "report_type": report_type,
                "category": category,
                "event_type": extracted.event_type,
                "sentiment_score": float(extracted.sentiment_score or 0.0),
                "summary": extracted.summary,
                "required_slots": _json.dumps(extracted.required_slots or {}, ensure_ascii=False),
                "optional_slots": _json.dumps(extracted.optional_slots or {}, ensure_ascii=False),
                "source_url": url,
            }

            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO dart_event_extractions (
                          rcept_no, stock_code, corp_code, corp_name, rcept_dt, report_type, category,
                          event_type, sentiment_score, summary, required_slots, optional_slots, source_url
                        )
                        VALUES (
                          :rcept_no, :stock_code, :corp_code, :corp_name, :rcept_dt, :report_type, :category,
                          :event_type, :sentiment_score, :summary,
                          CAST(:required_slots AS jsonb), CAST(:optional_slots AS jsonb), :source_url
                        )
                        ON CONFLICT (rcept_no) DO NOTHING
                        """
                    ),
                    params,
                )
            inserted += 1

    logger.info("extract_events done: inserted=%s skipped=%s window=%s..%s universe=%s", inserted, skipped, start_dt, end_dt, len(stock_codes))
    return True


def pattern_matching(**context):
    """Placeholder (future): Neo4j pattern matching and user notification."""
    logger.info("pattern_matching placeholder - to be implemented")
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


