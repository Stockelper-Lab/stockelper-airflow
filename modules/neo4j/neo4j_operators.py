"""
Airflow operators for Neo4j Knowledge Graph ETL.

Current approach (UPDATED - 2025-01-06):
- Treat **DART disclosure category/type (major-report endpoint)** as Event.
- Do NOT run LLM-based event extraction / sentiment scoring in the KG ETL (POSTPONED).
- Build the graph **by date** using DB sources:
  - PostgreSQL: `daily_stock_price`
  - PostgreSQL: `dart_*` major-report tables (structured OpenDART endpoints)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date as date_cls, datetime
from typing import Any

import pendulum
from airflow.exceptions import AirflowNotFoundException, AirflowSkipException
from airflow.providers.neo4j.hooks.neo4j import Neo4jHook
from sqlalchemy import text

from modules.dart_disclosure.opendart_api import build_dart_viewer_url
from modules.postgres.postgres_connector import get_postgres_engine

try:  # stockelper-kg is vendored/installed in the Airflow environment
    from stockelper_kg.graph.cypher import generate_constraints as _kg_generate_constraints
except Exception:  # noqa: BLE001
    _kg_generate_constraints = None


log = logging.getLogger(__name__)


def _neo4j_run_with_retry(
    *,
    hook: Neo4jHook,
    neo4j_conn_id: str,
    query: str,
    parameters: dict[str, Any] | None = None,
    max_attempts: int = 8,
    base_sleep_seconds: float = 1.0,
    max_sleep_seconds: float = 30.0,
) -> tuple[Neo4jHook, list[dict[str, Any]]]:
    """Run a Neo4j query with retry on transient connection failures.

    This protects long-running rebuild jobs from intermittent Bolt disconnects,
    Neo4j restarts, and temporary overload conditions (e.g., during huge wipes).
    """
    from neo4j.exceptions import ServiceUnavailable, SessionExpired  # local import: safe in DAG parsing

    last_err: Exception | None = None
    attempts = max(1, int(max_attempts))

    for attempt in range(1, attempts + 1):
        try:
            res = hook.run(query, parameters=parameters) if parameters else hook.run(query)
            return hook, (res or [])
        except (
            ServiceUnavailable,
            SessionExpired,
            TimeoutError,
            OSError,
            AirflowNotFoundException,
        ) as e:  # noqa: PERF203
            last_err = e
            sleep_s = min(max_sleep_seconds, base_sleep_seconds * (2 ** (attempt - 1)))
            log.warning(
                "Neo4j transient error (attempt %s/%s). Will retry in %.1fs. Error=%s",
                attempt,
                attempts,
                sleep_s,
                e,
            )
            time.sleep(sleep_s)
            # Recreate the hook/driver/session for a clean reconnect attempt
            hook = Neo4jHook(neo4j_conn_id)
            continue

    if last_err:
        raise last_err
    return hook, []


# ---------- DART disclosure category/type mapping ----------
# Meeting reference: docs/references/20250106.md / PRD FR2i-FR2z
DART_MAJOR_REPORT_TYPE_MAP: dict[str, dict[str, Any]] = {
    # Capital changes (증자/감자)
    "piicDecsn": {"disclosure_type_code": 6, "disclosure_name": "유상증자_결정"},
    "fricDecsn": {"disclosure_type_code": 7, "disclosure_name": "무상증자_결정"},
    "pifricDecsn": {"disclosure_type_code": 8, "disclosure_name": "유무상증자_결정"},
    "crDecsn": {"disclosure_type_code": 9, "disclosure_name": "감자_결정"},
    # Bonds (CB/BW)
    "cvbdIsDecsn": {"disclosure_type_code": 16, "disclosure_name": "전환사채권_발행결정"},
    "bdwtIsDecsn": {"disclosure_type_code": 17, "disclosure_name": "신주인수권부사채권_발행결정"},
    # Treasury stock
    "tsstkAqDecsn": {"disclosure_type_code": 21, "disclosure_name": "자기주식_취득_결정"},
    "tsstkDpDecsn": {"disclosure_type_code": 22, "disclosure_name": "자기주식_처분_결정"},
    "tsstkAqTrctrCnsDecsn": {
        "disclosure_type_code": 23,
        "disclosure_name": "자기주식취득_신탁계약_체결_결정",
    },
    "tsstkAqTrctrCcDecsn": {
        "disclosure_type_code": 24,
        "disclosure_name": "자기주식취득_신탁계약_해지_결정",
    },
    # Business transfer
    "bsnInhDecsn": {"disclosure_type_code": 25, "disclosure_name": "영업양수_결정"},
    "bsnTrfDecsn": {"disclosure_type_code": 26, "disclosure_name": "영업양도_결정"},
    # Other company stocks
    "otcprStkInvscrInhDecsn": {"disclosure_type_code": 29, "disclosure_name": "타법인주식_양수결정"},
    "otcprStkInvscrTrfDecsn": {"disclosure_type_code": 30, "disclosure_name": "타법인주식_양도결정"},
    # M&A / restructuring
    "cmpMgDecsn": {"disclosure_type_code": 33, "disclosure_name": "회사합병_결정"},
    "cmpDvDecsn": {"disclosure_type_code": 34, "disclosure_name": "회사분할_결정"},
    "cmpDvmgDecsn": {"disclosure_type_code": 35, "disclosure_name": "회사분할합병_결정"},
    "stkExtrDecsn": {"disclosure_type_code": 36, "disclosure_name": "주식교환이전_결정"},
}


def _to_iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date_cls):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    if not s:
        return None
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s[:10]


def _date_parts(date_iso: str) -> dict[str, Any]:
    try:
        dt = datetime.strptime(date_iso, "%Y-%m-%d")
        return {"date": date_iso, "year": dt.year, "month": dt.month, "day": dt.day}
    except Exception:  # noqa: BLE001
        return {"date": date_iso}


def resolve_daily_target_date(*, postgres_conn_id: str = "postgres_default") -> str:
    """Resolve the target date for the daily KG load.

    Strategy:
    - Use the latest available date across **both** sources:
      - `daily_stock_price.date` (trading calendar)
      - `dart_*.rcept_dt` (disclosure calendar; can exist on non-trading days)

    Rationale:
    - Rebuild loads a union of dates from stock prices and DART disclosures.
    - Daily should align by not ignoring "DART-only" dates (e.g., holidays/weekends).
    """
    engine = get_postgres_engine(conn_id=postgres_conn_id)

    # 1) Stock price max date
    with engine.begin() as conn:
        sp_max = conn.execute(text("SELECT MAX(date) FROM daily_stock_price")).scalar()
    sp_max_iso = _to_iso_date(sp_max)

    # 2) DART max date across dart_* major-report tables (same discovery rule as loaders)
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
    dart_tables = [r[0] for r in tbl_rows]

    dart_max_iso: str | None = None
    for t in dart_tables:
        with engine.begin() as conn:
            dmax = conn.execute(text(f"SELECT MAX(rcept_dt) FROM {t}")).scalar()
        dmax_iso = _to_iso_date(dmax)
        if dmax_iso and (dart_max_iso is None or dmax_iso > dart_max_iso):
            dart_max_iso = dmax_iso

    candidates = [d for d in (sp_max_iso, dart_max_iso) if d]
    if not candidates:
        raise AirflowSkipException(
            "No usable dates found in Postgres (daily_stock_price and dart_*); skipping KG daily load."
        )

    return max(candidates)


def create_base_kg_data(*, neo4j_conn_id: str):
    """Idempotently create constraints/indexes required by the KG."""
    hook = Neo4jHook(neo4j_conn_id)

    statements: list[str] = []
    if _kg_generate_constraints is not None:
        constraints = _kg_generate_constraints().strip()
        if constraints:
            statements.extend([s.strip() for s in constraints.rstrip(";").split(";\n") if s.strip()])
    else:
        # Fallback: minimal uniqueness constraints (safe defaults)
        statements.extend(
            [
                "CREATE CONSTRAINT company_stock_code IF NOT EXISTS FOR (c:Company) REQUIRE c.stock_code IS UNIQUE",
                "CREATE CONSTRAINT event_event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.event_id IS UNIQUE",
                "CREATE CONSTRAINT document_rcept_no IF NOT EXISTS FOR (d:Document) REQUIRE d.rcept_no IS UNIQUE",
                "CREATE CONSTRAINT date_date IF NOT EXISTS FOR (d:Date) REQUIRE d.date IS UNIQUE",
            ]
        )

    for stmt in statements:
        hook, _ = _neo4j_run_with_retry(hook=hook, neo4j_conn_id=neo4j_conn_id, query=stmt, max_attempts=10)

    hook, _ = _neo4j_run_with_retry(
        hook=hook,
        neo4j_conn_id=neo4j_conn_id,
        query="MERGE (m:Meta {name: 'kg_setup_status'}) "
        "SET m.complete = true, m.completed_at = datetime()",
        max_attempts=10,
    )
    return {"constraints_applied": len(statements)}


def load_daily_stock_prices(
    *,
    neo4j_conn_id: str,
    postgres_conn_id: str = "postgres_default",
    target_date: str,
    batch_size: int = 3000,
    limit: int | None = None,
) -> dict[str, Any]:
    """Load `daily_stock_price` rows for one date into Neo4j (idempotent)."""
    engine = get_postgres_engine(conn_id=postgres_conn_id)
    hook = Neo4jHook(neo4j_conn_id)

    date_iso = _to_iso_date(target_date)
    if not date_iso:
        raise ValueError(f"Invalid target_date: {target_date!r}")

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT symbol, date, open, high, low, close, volume, adj_close
                FROM daily_stock_price
                WHERE date = :d
                ORDER BY symbol
                """
            ),
            {"d": date_iso},
        ).fetchall()

    if limit:
        rows = rows[: int(limit)]

    if not rows:
        raise AirflowSkipException(f"No daily_stock_price rows for date={date_iso}; skipping.")

    def _num(val: Any) -> float | None:
        if val is None:
            return None
        try:
            return float(val)
        except Exception:  # noqa: BLE001
            return None

    payload_rows: list[dict[str, Any]] = []
    for r in rows:
        stock_code = str(r[0]).strip().zfill(6)
        traded_iso = _to_iso_date(r[1]) or date_iso
        parts = _date_parts(traded_iso)
        payload_rows.append(
            {
                "stock_code": stock_code,
                "traded_at": traded_iso,
                "stck_oprc": _num(r[2]),
                "stck_hgpr": _num(r[3]),
                "stck_lwpr": _num(r[4]),
                "stck_prpr": _num(r[5]),
                "volume": int(r[6]) if r[6] is not None else None,
                "adj_close": _num(r[7]),
                **parts,
            }
        )

    cypher = """
    UNWIND $rows AS row
    // Company
    MERGE (c:Company {stock_code: row.stock_code})
    SET c.updated_at = datetime()

    // Dates
    MERGE (d:Date {date: row.date})
    SET d.year = row.year, d.month = row.month, d.day = row.day
    MERGE (pd:PriceDate {date: row.date})
    SET pd.year = row.year, pd.month = row.month, pd.day = row.day
    MERGE (pd)-[:IS_DATE]->(d)
    MERGE (c)-[:ON_DATE]->(d)

    // StockPrice snapshot
    MERGE (sp:StockPrice {stock_code: row.stock_code, traded_at: row.traded_at})
    SET sp.stck_oprc = row.stck_oprc,
        sp.stck_hgpr = row.stck_hgpr,
        sp.stck_lwpr = row.stck_lwpr,
        sp.stck_prpr = row.stck_prpr,
        sp.volume = row.volume,
        sp.adj_close = row.adj_close,
        sp.updated_at = datetime()

    MERGE (c)-[:HAS_STOCK_PRICE]->(sp)
    MERGE (sp)-[:RECORDED_ON]->(pd)
    """

    loaded = 0
    for i in range(0, len(payload_rows), int(batch_size)):
        batch = payload_rows[i : i + int(batch_size)]
        hook, _ = _neo4j_run_with_retry(
            hook=hook,
            neo4j_conn_id=neo4j_conn_id,
            query=cypher,
            parameters={"rows": batch},
            max_attempts=10,
        )
        loaded += len(batch)

    return {"date": date_iso, "loaded_stock_prices": loaded}


def load_daily_dart_disclosure_events(
    *,
    neo4j_conn_id: str,
    postgres_conn_id: str = "postgres_default",
    target_date: str,
    batch_size: int = 1000,
    limit: int | None = None,
) -> dict[str, Any]:
    """Load DART disclosure category events (from Postgres dart_* tables) into Neo4j."""
    engine = get_postgres_engine(conn_id=postgres_conn_id)
    hook = Neo4jHook(neo4j_conn_id)

    date_iso = _to_iso_date(target_date)
    if not date_iso:
        raise ValueError(f"Invalid target_date: {target_date!r}")

    # Discover dart_* major-report tables (skip non-report tables by requiring expected columns)
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
        raise AirflowSkipException("No dart_* major-report tables found in Postgres; skipping DART event load.")

    payload_rows: list[dict[str, Any]] = []
    for table in table_names:
        q = text(
            f"""
            SELECT t.rcept_no, t.stock_code, t.corp_code, t.corp_name, t.rcept_dt, t.report_type, t.category, t.payload
            FROM {table} t
            WHERE t.rcept_dt = :d
              AND t.stock_code IS NOT NULL
            ORDER BY t.rcept_no
            """
        )
        with engine.begin() as conn:
            rows = conn.execute(q, {"d": date_iso}).fetchall()

        for r in rows:
            rcept_no = str(r[0]).strip()
            stock_code = str(r[1]).strip().zfill(6)
            corp_code = str(r[2] or "").strip() or None
            corp_name = str(r[3] or "").strip() or None
            rcept_dt_iso = _to_iso_date(r[4]) or date_iso
            report_type = str(r[5] or "").strip() or None
            disclosure_category = str(r[6] or "").strip() or None
            payload = r[7]

            if not (rcept_no and stock_code and report_type and rcept_dt_iso):
                continue

            mapping = DART_MAJOR_REPORT_TYPE_MAP.get(report_type or "")
            disclosure_type_code = mapping.get("disclosure_type_code") if mapping else None
            disclosure_name = mapping.get("disclosure_name") if mapping else None

            payload_json = ""
            if payload is not None:
                try:
                    payload_json = json.dumps(payload, ensure_ascii=False)
                except Exception:  # noqa: BLE001
                    payload_json = str(payload)

            # Avoid bloating Neo4j with extremely large JSON payloads
            payload_json = payload_json[:20000]

            parts = _date_parts(rcept_dt_iso)
            payload_rows.append(
                {
                    "event_id": f"EVT_{rcept_no}",
                    "source": "DART",
                    "rcept_no": rcept_no,
                    "corp_code": corp_code,
                    "corp_name": corp_name,
                    "stock_code": stock_code,
                    "rcept_dt": rcept_dt_iso,
                    "report_type": report_type,
                    "disclosure_category": disclosure_category,
                    "disclosure_type_code": disclosure_type_code,
                    "disclosure_name": disclosure_name,
                    "url": build_dart_viewer_url(rcept_no),
                    "payload_json": payload_json,
                    **parts,
                }
            )

    if limit:
        payload_rows = payload_rows[: int(limit)]

    if not payload_rows:
        raise AirflowSkipException(f"No DART disclosure rows for date={date_iso}; skipping.")

    cypher = """
    UNWIND $rows AS row
    // Company (best-effort enrichment from DART)
    MERGE (c:Company {stock_code: row.stock_code})
    SET c.corp_code = coalesce(c.corp_code, row.corp_code),
        c.corp_name = coalesce(c.corp_name, row.corp_name),
        c.updated_at = datetime()

    // Dates
    MERGE (d:Date {date: row.date})
    SET d.year = row.year, d.month = row.month, d.day = row.day
    MERGE (ed:EventDate {date: row.date})
    SET ed.year = row.year, ed.month = row.month, ed.day = row.day
    MERGE (ed)-[:IS_DATE]->(d)
    MERGE (c)-[:ON_DATE]->(d)

    // Document (payload JSON as body)
    MERGE (doc:Document {rcept_no: row.rcept_no})
    SET doc.report_nm = coalesce(doc.report_nm, row.disclosure_name, row.report_type),
        doc.rcept_dt = row.rcept_dt,
        doc.url = row.url,
        doc.body = row.payload_json,
        doc.updated_at = datetime()

    // Event (category-based)
    MERGE (e:Event {event_id: row.event_id})
    SET e.source = row.source,
        e.report_type = row.report_type,
        e.disclosure_category = row.disclosure_category,
        e.disclosure_type_code = row.disclosure_type_code,
        e.disclosure_name = row.disclosure_name,
        e.payload_json = row.payload_json,
        e.corp_code = row.corp_code,
        e.stock_code = row.stock_code,
        e.updated_at = datetime()

    // Relationships
    MERGE (c)-[:INVOLVED_IN]->(e)
    MERGE (e)-[:REPORTED_BY]->(doc)
    MERGE (e)-[:OCCURRED_ON]->(ed)
    """

    loaded = 0
    for i in range(0, len(payload_rows), int(batch_size)):
        batch = payload_rows[i : i + int(batch_size)]
        hook, _ = _neo4j_run_with_retry(
            hook=hook,
            neo4j_conn_id=neo4j_conn_id,
            query=cypher,
            parameters={"rows": batch},
            max_attempts=10,
        )
        loaded += len(batch)

    return {"date": date_iso, "loaded_dart_events": loaded}


def wipe_neo4j_database(*, neo4j_conn_id: str) -> bool:
    """Delete ALL nodes/relationships from Neo4j (DANGEROUS).

    Notes:
    - This does NOT drop indexes/constraints; use `wipe_neo4j_database_full()` for full rebuild.
    - Intended for rebuild workflows only.
    """
    hook = Neo4jHook(neo4j_conn_id)
    hook.run("MATCH (n) DETACH DELETE n")
    return True


def wipe_neo4j_database_full(*, neo4j_conn_id: str) -> dict[str, int]:
    """Fully wipe Neo4j: drop constraints/indexes (except LOOKUP) and delete all data.

    This is required for clean rebuilds because Neo4j does not allow creating a uniqueness
    constraint if a conflicting index already exists.
    """
    hook = Neo4jHook(neo4j_conn_id)

    dropped_constraints = 0
    dropped_indexes = 0
    deleted_relationships = 0
    deleted_nodes = 0

    # 1) Drop constraints first (some indexes may be owned by constraints)
    try:
        rows = hook.run("SHOW CONSTRAINTS YIELD name RETURN name") or []
        for r in rows:
            name = (r or {}).get("name")
            if not name:
                continue
            hook.run(f"DROP CONSTRAINT `{name}` IF EXISTS")
            dropped_constraints += 1
    except Exception:  # noqa: BLE001
        # Best-effort: continue with data wipe
        pass

    # 2) Drop indexes (skip LOOKUP indexes)
    try:
        rows = hook.run("SHOW INDEXES YIELD name, type RETURN name, type") or []
        for r in rows:
            name = (r or {}).get("name")
            idx_type = (r or {}).get("type")
            if not name:
                continue
            if str(idx_type or "").upper() == "LOOKUP":
                continue
            hook.run(f"DROP INDEX `{name}` IF EXISTS")
            dropped_indexes += 1
    except Exception:  # noqa: BLE001
        pass

    # 3) Delete all data in batches to avoid long-running "DETACH DELETE" timeouts.
    #
    # A single `MATCH (n) DETACH DELETE n` can run for a long time on a large graph and the
    # Neo4j driver may hit socket timeouts / defunct connections. Instead, we delete in
    # smaller transactions and retry on transient connection failures.

    def _run_with_retry(statement: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from neo4j.exceptions import ServiceUnavailable  # local import: avoid import-time surprises

        nonlocal hook
        last_err: Exception | None = None
        for attempt in range(1, 6):  # up to 5 attempts
            try:
                return hook.run(statement, parameters=parameters) or []
            except ServiceUnavailable as e:
                last_err = e
                # Recreate hook/session on transient driver errors
                log.warning("Neo4j ServiceUnavailable during wipe (attempt %s/5): %s", attempt, e)
                hook = Neo4jHook(neo4j_conn_id)
                time.sleep(min(5, attempt))
                continue
            except TimeoutError as e:  # noqa: PERF203
                last_err = e
                log.warning("Neo4j TimeoutError during wipe (attempt %s/5): %s", attempt, e)
                hook = Neo4jHook(neo4j_conn_id)
                time.sleep(min(5, attempt))
                continue
        if last_err:
            raise last_err
        return []

    # Smaller batch => shorter transactions => less chance of Bolt socket timeout.
    # Tune via env var if needed.
    batch_size = int(os.getenv("NEO4J_WIPE_BATCH_SIZE", "5000"))
    if batch_size <= 0:
        batch_size = 5000

    # 3-a) Delete relationships first (faster + no DETACH cost later)
    while True:
        rows = _run_with_retry(
            "MATCH ()-[r]-() WITH r LIMIT $limit DELETE r RETURN count(r) AS deleted",
            {"limit": batch_size},
        )
        n = int((rows[0] or {}).get("deleted") or 0) if rows else 0
        if n <= 0:
            break
        deleted_relationships += n
        if deleted_relationships and deleted_relationships % (batch_size * 10) == 0:
            log.info("wipe_neo4j_database_full: deleted_relationships=%s", deleted_relationships)

    # 3-b) Delete nodes
    while True:
        rows = _run_with_retry(
            "MATCH (n) WITH n LIMIT $limit DELETE n RETURN count(n) AS deleted",
            {"limit": batch_size},
        )
        n = int((rows[0] or {}).get("deleted") or 0) if rows else 0
        if n <= 0:
            break
        deleted_nodes += n
        if deleted_nodes and deleted_nodes % (batch_size * 10) == 0:
            log.info("wipe_neo4j_database_full: deleted_nodes=%s", deleted_nodes)

    return {
        "dropped_constraints": dropped_constraints,
        "dropped_indexes": dropped_indexes,
        "deleted_relationships": deleted_relationships,
        "deleted_nodes": deleted_nodes,
    }


def rebuild_kg_from_postgres_range(
    *,
    neo4j_conn_id: str,
    postgres_conn_id: str = "postgres_default",
    start_date: str,
    end_date: str,
    wipe: bool = True,
) -> dict[str, Any]:
    """Rebuild the KG from PostgreSQL for a date range (best-effort).

    Notes:
    - Uses `daily_stock_price.date` as the driving calendar (trading days).
    - For each date:
      - load stock prices
      - load DART disclosure-category events
    """
    start_iso = _to_iso_date(start_date)
    end_iso = _to_iso_date(end_date)
    if not start_iso or not end_iso:
        raise ValueError(f"Invalid date range: start_date={start_date!r}, end_date={end_date!r}")

    if wipe:
        wipe_neo4j_database_full(neo4j_conn_id=neo4j_conn_id)

    # Re-create constraints/meta marker after wipe
    try:
        create_base_kg_data(neo4j_conn_id=neo4j_conn_id)
    except AirflowSkipException:
        # already set up
        pass

    engine = get_postgres_engine(conn_id=postgres_conn_id)
    with engine.begin() as conn:
        date_rows = conn.execute(
            text(
                """
                SELECT DISTINCT date
                FROM daily_stock_price
                WHERE date >= :start_dt AND date <= :end_dt
                ORDER BY date
                """
            ),
            {"start_dt": start_iso, "end_dt": end_iso},
        ).fetchall()

    dates = [_to_iso_date(r[0]) for r in date_rows]
    dates = [d for d in dates if d]
    if not dates:
        raise AirflowSkipException(f"No daily_stock_price dates in range {start_iso}..{end_iso}")

    total_prices = 0
    total_events = 0
    for d in dates:
        res_prices = load_daily_stock_prices(
            neo4j_conn_id=neo4j_conn_id,
            postgres_conn_id=postgres_conn_id,
            target_date=d,
        )
        total_prices += int(res_prices.get("loaded_stock_prices") or 0)

        res_events = load_daily_dart_disclosure_events(
            neo4j_conn_id=neo4j_conn_id,
            postgres_conn_id=postgres_conn_id,
            target_date=d,
        )
        total_events += int(res_events.get("loaded_dart_events") or 0)

    return {
        "start_date": start_iso,
        "end_date": end_iso,
        "days": len(dates),
        "loaded_stock_prices": total_prices,
        "loaded_dart_events": total_events,
    }


def rebuild_kg_from_postgres_all(
    *,
    neo4j_conn_id: str,
    postgres_conn_id: str = "postgres_default",
    wipe: bool = True,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Rebuild the KG using **ALL data present in PostgreSQL** (optionally within a range).

    If `start_date`/`end_date` are omitted, this will derive the range from DB contents.

    Notes:
    - 날짜 단위 KG이므로, `daily_stock_price.date` + `dart_*.rcept_dt`의 **합집합** 날짜를 대상으로 적재합니다.
    - 특정 날짜에 주가/공시가 없으면 해당 부분만 스킵하고 계속 진행합니다.
    """
    engine = get_postgres_engine(conn_id=postgres_conn_id)

    # Discover dart_* tables (same rule as daily loader)
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
    dart_tables = [r[0] for r in tbl_rows]

    # Resolve date range from DB if not provided
    start_iso = _to_iso_date(start_date) if start_date else None
    end_iso = _to_iso_date(end_date) if end_date else None

    if start_iso is None or end_iso is None:
        with engine.begin() as conn:
            sp_min = conn.execute(text("SELECT MIN(date) FROM daily_stock_price")).scalar()
            sp_max = conn.execute(text("SELECT MAX(date) FROM daily_stock_price")).scalar()
        sp_min_iso = _to_iso_date(sp_min)
        sp_max_iso = _to_iso_date(sp_max)

        dart_min_iso: str | None = None
        dart_max_iso: str | None = None
        if dart_tables:
            for t in dart_tables:
                with engine.begin() as conn:
                    dmin = conn.execute(text(f"SELECT MIN(rcept_dt) FROM {t}")).scalar()
                    dmax = conn.execute(text(f"SELECT MAX(rcept_dt) FROM {t}")).scalar()
                dmin_iso = _to_iso_date(dmin)
                dmax_iso = _to_iso_date(dmax)
                if dmin_iso and (dart_min_iso is None or dmin_iso < dart_min_iso):
                    dart_min_iso = dmin_iso
                if dmax_iso and (dart_max_iso is None or dmax_iso > dart_max_iso):
                    dart_max_iso = dmax_iso

        candidates_min = [d for d in (start_iso, sp_min_iso, dart_min_iso) if d]
        candidates_max = [d for d in (end_iso, sp_max_iso, dart_max_iso) if d]

        if start_iso is None:
            start_iso = min(candidates_min) if candidates_min else None
        if end_iso is None:
            end_iso = max(candidates_max) if candidates_max else None

    if not start_iso or not end_iso:
        raise AirflowSkipException("No usable dates found in Postgres (daily_stock_price and dart_*).")

    # Wipe (optional)
    if wipe:
        wipe_neo4j_database_full(neo4j_conn_id=neo4j_conn_id)

    # Setup constraints/meta marker after wipe
    try:
        create_base_kg_data(neo4j_conn_id=neo4j_conn_id)
    except AirflowSkipException:
        pass

    # Collect distinct dates from BOTH sources within the range (union)
    date_set: set[str] = set()
    with engine.begin() as conn:
        sp_dates = conn.execute(
            text(
                """
                SELECT DISTINCT date
                FROM daily_stock_price
                WHERE date >= :start_dt AND date <= :end_dt
                """
            ),
            {"start_dt": start_iso, "end_dt": end_iso},
        ).fetchall()
    for r in sp_dates:
        d = _to_iso_date(r[0])
        if d:
            date_set.add(d)

    for t in dart_tables:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT DISTINCT rcept_dt
                    FROM {t}
                    WHERE rcept_dt >= :start_dt AND rcept_dt <= :end_dt
                    """
                ),
                {"start_dt": start_iso, "end_dt": end_iso},
            ).fetchall()
        for r in rows:
            d = _to_iso_date(r[0])
            if d:
                date_set.add(d)

    all_dates = sorted(date_set)
    if not all_dates:
        raise AirflowSkipException(f"No dates found in range {start_iso}..{end_iso}")

    total_prices = 0
    total_events = 0
    skipped_prices_days = 0
    skipped_event_days = 0

    for d in all_dates:
        try:
            res_prices = load_daily_stock_prices(
                neo4j_conn_id=neo4j_conn_id,
                postgres_conn_id=postgres_conn_id,
                target_date=d,
            )
            total_prices += int(res_prices.get("loaded_stock_prices") or 0)
        except AirflowSkipException:
            skipped_prices_days += 1

        try:
            res_events = load_daily_dart_disclosure_events(
                neo4j_conn_id=neo4j_conn_id,
                postgres_conn_id=postgres_conn_id,
                target_date=d,
            )
            total_events += int(res_events.get("loaded_dart_events") or 0)
        except AirflowSkipException:
            skipped_event_days += 1

    return {
        "start_date": start_iso,
        "end_date": end_iso,
        "days": len(all_dates),
        "skipped_price_days": skipped_prices_days,
        "skipped_event_days": skipped_event_days,
        "loaded_stock_prices": total_prices,
        "loaded_dart_events": total_events,
    }
