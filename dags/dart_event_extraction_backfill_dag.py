"""
DART Disclosures -> Event/Sentiment Extraction -> Neo4j Backfill DAG
===================================================================

Purpose:
- After curated(엄선된) DART disclosure tables(dart_*) have been collected into Postgres,
  this DAG:
  1) extracts event_type + sentiment_score (LLM) from Postgres disclosure tables
  2) stores results into Postgres table: `dart_event_extractions`
  3) upserts the extracted events into Neo4j (ontology-aligned)

Notes:
- This DAG is MANUAL (schedule=None). Intended for backfill/repair runs.
- Ontology reference: `stockelper-kg/src/stockelper_kg/graph/ontology.py`
"""

from __future__ import annotations

import json as _json
from datetime import datetime

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import text

from modules.common.airflow_settings import get_required_setting, get_setting
from modules.common.logging_config import setup_logger
from modules.postgres.postgres_connector import get_postgres_engine
from modules.neo4j.dart_event_uploader import load_dart_event_extractions_to_neo4j

logger = setup_logger(__name__)


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": pendulum.duration(minutes=10),
    # Backfill can be long-running (OpenAI + OpenDART calls)
    "execution_timeout": pendulum.duration(hours=24),
}


def load_universe_template(**context):
    """(Deprecated) kept for backward compatibility. No-op."""
    logger.info("load_universe_template is no longer used for Postgres-based backfill; skipping.")
    return True
    import json
    from pathlib import Path

    default_path = "/opt/airflow/stockelper-kg/modules/dart_disclosure/universe.ai-sector.template.json"
    universe_path = get_setting("DART_CURATED_UNIVERSE_JSON", default_path)

    path = Path(str(universe_path)).expanduser()
    data = json.loads(path.read_text(encoding="utf-8"))
    stocks = data.get("stocks") or []
    stock_codes = [
        str(s.get("stock_code") or "").strip().zfill(6)
        for s in stocks
        if isinstance(s, dict) and s.get("stock_code")
    ]
    stock_codes = [c for c in stock_codes if c.isdigit() and len(c) == 6]

    ti = context["ti"]
    ti.xcom_push(key="universe_path", value=str(path))
    ti.xcom_push(key="stock_codes", value=stock_codes)
    ti.xcom_push(key="universe_size", value=len(stock_codes))
    logger.info("Loaded universe: %s stocks (path=%s)", len(stock_codes), path)
    return len(stock_codes)


def extract_events_backfill(**context):
    """Backfill extraction for ALL disclosure rows in Postgres into `dart_event_extractions`."""
    from modules.dart_disclosure.llm_extractor import OpenAIEventExtractor
    from modules.dart_disclosure.opendart_api import build_dart_viewer_url, normalize_iso_date

    ti = context["ti"]

    years = int(get_setting("DART_EVENT_BACKFILL_YEARS", "20"))
    end_s = str(get_setting("DART_EVENT_BACKFILL_END_DATE", pendulum.now("Asia/Seoul").format("YYYYMMDD")) or "")
    end_s = end_s.replace("-", "")
    if len(end_s) != 8 or not end_s.isdigit():
        raise ValueError(f"Invalid DART_EVENT_BACKFILL_END_DATE: {end_s!r}")

    end_dt = datetime.strptime(end_s, "%Y%m%d")
    start_dt = pendulum.instance(end_dt, tz="Asia/Seoul").subtract(years=years)

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

    def _event_type_hint(report_type: str | None, category: str | None) -> str:
        rt = (report_type or "").strip()
        cat = (category or "").strip()
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
            return "CRISIS_EVENT"
        return "OTHER"

    # Find major-report tables (dart_*) but skip non-report tables (e.g., progress tables) by requiring expected columns.
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
        logger.warning("No dart_* tables found; did you run the major-report backfill first?")
        return True

    extractor = OpenAIEventExtractor(timeout_seconds=float(get_setting("DART_EVENT_TIMEOUT_SECONDS", "60")))

    inserted = 0
    skipped = 0
    hard_limit = int(get_setting("DART_EVENT_BACKFILL_LIMIT", "0") or "0")

    for table_name in table_names:
        q = text(
            f"""
            SELECT t.rcept_no, t.stock_code, t.corp_code, t.corp_name, t.rcept_dt, t.report_type, t.category, t.payload
            FROM {table_name} t
            WHERE t.rcept_dt >= :start_dt
              AND t.rcept_dt <= :end_dt
              AND NOT EXISTS (SELECT 1 FROM dart_event_extractions e WHERE e.rcept_no = t.rcept_no)
            ORDER BY t.rcept_dt ASC
            """
        )

        with engine.begin() as conn:
            rows = conn.execute(
                q,
                {"start_dt": start_dt.date(), "end_dt": end_dt.date()},
            ).fetchall()

        for r in rows:
            rcept_no = str(r[0])
            stock_code = str(r[1]).zfill(6)
            corp_code = str(r[2] or "").strip() or None
            corp_name = str(r[3] or "").strip() or None
            rcept_dt = r[4]
            report_type = str(r[5] or "").strip() or None
            category = str(r[6] or "").strip() or None
            payload = r[7]

            hint = _event_type_hint(report_type, category)
            url = build_dart_viewer_url(rcept_no)
            rcept_dt_str = rcept_dt.strftime("%Y%m%d") if rcept_dt else ""
            reported_iso = normalize_iso_date(rcept_dt_str) if rcept_dt_str else pendulum.now("Asia/Seoul").format("YYYY-MM-DD")

            try:
                # IMPORTANT: Use payload from Postgres disclosure tables as the primary input (no extra OpenDART calls).
                # This avoids 020 rate limits and keeps extraction reproducible from DB state.
                body_text = _json.dumps(payload or {}, ensure_ascii=False, indent=2)
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

            if hard_limit > 0 and inserted >= hard_limit:
                logger.warning("Reached DART_EVENT_BACKFILL_LIMIT=%s; stopping early.", hard_limit)
                break

        if hard_limit > 0 and inserted >= hard_limit:
            break

    logger.info(
        "extract_events_backfill done: inserted=%s skipped=%s range=%s..%s",
        inserted,
        skipped,
        start_dt.format("YYYY-MM-DD"),
        end_dt.strftime("%Y-%m-%d"),
    )

    ti.xcom_push(
        key="backfill_summary",
        value={
            "start_date": start_dt.format("YYYYMMDD"),
            "end_date": end_s,
            "years": years,
            "inserted": inserted,
            "skipped": skipped,
            "limit": hard_limit,
        },
    )
    return True


def report(**context):
    summary = context["ti"].xcom_pull(task_ids="extract_events_backfill", key="backfill_summary")
    logger.info("Backfill summary: %s", summary)


def load_to_neo4j_backfill(**context):
    """Upsert extracted events from Postgres into Neo4j (ontology-aligned)."""
    years = int(get_setting("DART_EVENT_BACKFILL_YEARS", "20"))
    end_s = str(get_setting("DART_EVENT_BACKFILL_END_DATE", pendulum.now("Asia/Seoul").format("YYYYMMDD")) or "")
    end_s = end_s.replace("-", "")
    if len(end_s) != 8 or not end_s.isdigit():
        raise ValueError(f"Invalid DART_EVENT_BACKFILL_END_DATE: {end_s!r}")

    end_dt = datetime.strptime(end_s, "%Y%m%d")
    start_dt = pendulum.instance(end_dt, tz="Asia/Seoul").subtract(years=years)

    limit = int(get_setting("DART_EVENT_NEO4J_LIMIT", "0") or "0")
    res = load_dart_event_extractions_to_neo4j(
        neo4j_conn_id=get_setting("NEO4J_CONN_ID", "neo4j_default") or "neo4j_default",
        postgres_conn_id="postgres_default",
        start_date=start_dt.format("YYYY-MM-DD"),
        end_date=end_dt.strftime("%Y-%m-%d"),
        limit=limit if limit > 0 else None,
    )
    context["ti"].xcom_push(key="neo4j_load_summary", value=res)
    logger.info("Neo4j load summary: %s", res)
    return True


with DAG(
    dag_id="dart_event_sentiment_neo4j_backfill",
    default_args=default_args,
    description="(BACKFILL) Extract event_type/sentiment from Postgres disclosures and upsert into Neo4j",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Seoul"),
    catchup=False,
    tags=["dart", "event", "sentiment", "postgres", "neo4j", "backfill"],
) as dag:
    t_extract = PythonOperator(
        task_id="extract_events_backfill",
        python_callable=extract_events_backfill,
        execution_timeout=pendulum.duration(hours=24),
    )
    t_load_neo4j = PythonOperator(
        task_id="load_to_neo4j_backfill",
        python_callable=load_to_neo4j_backfill,
        execution_timeout=pendulum.duration(hours=24),
    )
    t_report = PythonOperator(task_id="report", python_callable=report)

    t_extract >> t_load_neo4j >> t_report


