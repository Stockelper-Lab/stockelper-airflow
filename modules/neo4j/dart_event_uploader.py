"""
DART events -> Neo4j loader (idempotent).

Reads `dart_events` + `dart_filings` (MongoDB) and upserts:
- (:Company {corp_code})
- (:Event {event_id})
- (:Document {rcept_no})
- (:Date {date}) and (:EventDate {date})

Relationships:
- (Company)-[:INVOLVED_IN]->(Event)
- (Event)-[:REPORTED_BY]->(Document)
- (Event)-[:OCCURRED_ON]->(EventDate)-[:IS_DATE]->(Date)
- (Company)-[:ON_DATE]->(Date)

NOTE:
- Designed to align with `stockelper-kg` ontology/payload patterns.
- This module is intentionally lightweight; batch/UNWIND optimizations can be added later.
"""

from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Any

from airflow.providers.neo4j.hooks.neo4j import Neo4jHook

from modules.common.db_connections import get_db_connection
from modules.common.logging_config import setup_logger
from modules.postgres.postgres_connector import get_postgres_engine

logger = setup_logger(__name__)


def _date_parts(date_iso: str) -> dict[str, Any]:
    try:
        dt = datetime.strptime(date_iso, "%Y-%m-%d")
        return {"date": date_iso, "year": dt.year, "month": dt.month, "day": dt.day}
    except Exception:  # noqa: BLE001
        return {"date": date_iso}


def _safe_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [v if isinstance(v, (str, int, float, bool)) else str(v) for v in value]
    return str(value)


def load_dart_events_to_neo4j(
    *,
    neo4j_conn_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Load DART-derived events from MongoDB to Neo4j."""
    db = get_db_connection()
    events = db["dart_events"]
    filings = db["dart_filings"]

    query: dict[str, Any] = {}
    if start_date or end_date:
        date_cond: dict[str, Any] = {}
        if start_date:
            date_cond["$gte"] = start_date
        if end_date:
            date_cond["$lte"] = end_date
        query["date"] = date_cond

    cursor = events.find(query).sort([("date", 1)])
    if limit:
        cursor = cursor.limit(int(limit))

    hook = Neo4jHook(neo4j_conn_id)

    cy_company = """
    MERGE (c:Company {corp_code: $corp_code})
    SET c.corp_name = $corp_name,
        c.stock_code = $stock_code,
        c.updated_at = datetime()
    """

    cy_document = """
    MERGE (d:Document {rcept_no: $rcept_no})
    SET d.report_nm = $report_nm,
        d.rcept_dt = $rcept_dt,
        d.url = $url,
        d.body = $body,
        d.updated_at = datetime()
    """

    cy_event = """
    MERGE (e:Event {event_id: $event_id})
    SET e.type = $event_type,
        e.summary = $summary,
        e.sentiment_score = $sentiment_score,
        e.corp_code = $corp_code,
        e.stock_code = $stock_code,
        e += $slots,
        e.updated_at = datetime()
    """

    cy_date = """
    MERGE (d:Date {date: $date})
    SET d.year = $year, d.month = $month, d.day = $day
    """

    cy_event_date = """
    MERGE (ed:EventDate {date: $date})
    SET ed.year = $year, ed.month = $month, ed.day = $day
    """

    cy_edges = """
    MATCH (c:Company {corp_code: $corp_code})
    MATCH (e:Event {event_id: $event_id})
    MATCH (doc:Document {rcept_no: $rcept_no})
    MATCH (d:Date {date: $date})
    MATCH (ed:EventDate {date: $date})
    MERGE (c)-[:INVOLVED_IN]->(e)
    MERGE (e)-[:REPORTED_BY]->(doc)
    MERGE (e)-[:OCCURRED_ON]->(ed)
    MERGE (ed)-[:IS_DATE]->(d)
    MERGE (c)-[:ON_DATE]->(d)
    """

    loaded = 0
    skipped = 0

    for ev in cursor:
        try:
            corp_code = ev.get("corp_code")
            stock_code = ev.get("stock_code")
            corp_name = ev.get("corp_name") or ev.get("corp_name") or ""
            event_id = ev.get("event_id")
            event_type = ev.get("event_type")
            date_iso = ev.get("date")
            source = ev.get("source") or {}
            rcept_no = source.get("rcept_no")
            report_nm = source.get("report_nm")
            rcept_dt = source.get("rcept_dt")
            url = source.get("url")

            if not (corp_code and event_id and event_type and date_iso and rcept_no):
                skipped += 1
                continue

            slots: dict[str, Any] = {}
            for k in ("required_slots", "optional_slots"):
                data = ev.get(k)
                if isinstance(data, dict):
                    for kk, vv in data.items():
                        if kk == "date":
                            continue
                        slots[kk] = _safe_scalar(vv)

            # Keep original JSON for debugging
            slots["required_slots_json"] = json.dumps(ev.get("required_slots") or {}, ensure_ascii=False)
            slots["optional_slots_json"] = json.dumps(ev.get("optional_slots") or {}, ensure_ascii=False)

            filing = filings.find_one({"rcept_no": rcept_no}, projection={"body_text": 1})
            body = (filing or {}).get("body_text") or ""
            # Avoid bloating Neo4j with extremely large text; keep first N chars.
            try:
                max_chars = int(os.getenv("NEO4J_DOCUMENT_BODY_MAX_CHARS", "20000"))
            except Exception:  # noqa: BLE001
                max_chars = 20000
            body = body[:max_chars] if isinstance(body, str) else ""

            params_common = {
                "corp_code": corp_code,
                "corp_name": corp_name,
                "stock_code": stock_code,
                "event_id": event_id,
                "event_type": event_type,
                "summary": ev.get("summary") or "",
                "sentiment_score": float(ev.get("sentiment_score") or 0.0),
                "slots": slots,
                "rcept_no": rcept_no,
                "report_nm": report_nm or "",
                "rcept_dt": rcept_dt or "",
                "url": url or "",
                "body": body,
                **_date_parts(date_iso),
            }

            hook.run(cy_company, parameters=params_common)
            hook.run(cy_document, parameters=params_common)
            hook.run(cy_event, parameters=params_common)
            hook.run(cy_date, parameters=params_common)
            hook.run(cy_event_date, parameters=params_common)
            hook.run(cy_edges, parameters=params_common)

            loaded += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load event to Neo4j: %s", exc)
            skipped += 1

    return {"loaded": loaded, "skipped": skipped}


def load_dart_event_extractions_to_neo4j(
    *,
    neo4j_conn_id: str,
    postgres_conn_id: str = "postgres_default",
    start_date: str | None = None,  # YYYY-MM-DD or YYYYMMDD (best-effort)
    end_date: str | None = None,  # YYYY-MM-DD or YYYYMMDD (best-effort)
    limit: int | None = None,
) -> dict[str, Any]:
    """Load DART event extractions from Postgres(`dart_event_extractions`) to Neo4j (idempotent).

    Expected source table (public):
    - dart_event_extractions (rcept_no PK)

    This aligns with `stockelper-kg` ontology:
    - (:Company {corp_code})
    - (:Event {event_id})
    - (:Document {rcept_no})
    - (:Date {date}) and (:EventDate {date})
    Relationships:
    - (Company)-[:INVOLVED_IN]->(Event)
    - (Event)-[:REPORTED_BY]->(Document)
    - (Event)-[:OCCURRED_ON]->(EventDate)-[:IS_DATE]->(Date)
    - (Company)-[:ON_DATE]->(Date)
    """
    from sqlalchemy import text

    def _to_iso_date(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        # psycopg2 DATE -> datetime.date
        try:
            return value.strftime("%Y-%m-%d")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        s = str(value).strip()
        if not s:
            return None
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:]}"
        return s[:10]

    def _safe_json(val: Any) -> dict[str, Any]:
        if val is None:
            return {}
        if isinstance(val, dict):
            return val
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:  # noqa: BLE001
                return {}
        return {}

    engine = get_postgres_engine(conn_id=postgres_conn_id)

    where: list[str] = []
    params: dict[str, Any] = {}
    if start_date:
        params["start_dt"] = _to_iso_date(start_date)
        where.append("rcept_dt >= CAST(:start_dt AS date)")
    if end_date:
        params["end_dt"] = _to_iso_date(end_date)
        where.append("rcept_dt <= CAST(:end_dt AS date)")

    sql = """
    SELECT
      rcept_no, stock_code, corp_code, corp_name, rcept_dt,
      report_type, category, event_type, sentiment_score, summary,
      required_slots, optional_slots, source_url
    FROM dart_event_extractions
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY rcept_dt ASC"
    if limit:
        sql += " LIMIT :limit"
        params["limit"] = int(limit)

    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    hook = Neo4jHook(neo4j_conn_id)

    # Best-effort schema (idempotent)
    constraints = [
        "CREATE CONSTRAINT company_code IF NOT EXISTS FOR (c:Company) REQUIRE c.corp_code IS UNIQUE",
        "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.event_id IS UNIQUE",
        "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.rcept_no IS UNIQUE",
        "CREATE CONSTRAINT date_id IF NOT EXISTS FOR (d:Date) REQUIRE d.date IS UNIQUE",
        "CREATE CONSTRAINT event_date_id IF NOT EXISTS FOR (d:EventDate) REQUIRE d.date IS UNIQUE",
    ]
    for q in constraints:
        try:
            hook.run(q)
        except Exception:  # noqa: BLE001
            # Non-fatal: constraints may already exist or user may not have privilege
            pass

    cy_company = """
    MERGE (c:Company {corp_code: $corp_code})
    SET c.corp_name = $corp_name,
        c.stock_code = $stock_code,
        c.updated_at = datetime()
    """

    cy_document = """
    MERGE (d:Document {rcept_no: $rcept_no})
    SET d.report_nm = $report_nm,
        d.rcept_dt = $rcept_dt,
        d.url = $url,
        d.updated_at = datetime()
    """

    cy_event = """
    MERGE (e:Event {event_id: $event_id})
    SET e.type = $event_type,
        e.summary = $summary,
        e.sentiment_score = $sentiment_score,
        e.corp_code = $corp_code,
        e.stock_code = $stock_code,
        e += $slots,
        e.updated_at = datetime()
    """

    cy_date = """
    MERGE (d:Date {date: $date})
    SET d.year = $year, d.month = $month, d.day = $day
    """

    cy_event_date = """
    MERGE (ed:EventDate {date: $date})
    SET ed.year = $year, ed.month = $month, ed.day = $day
    """

    cy_edges = """
    MATCH (c:Company {corp_code: $corp_code})
    MATCH (e:Event {event_id: $event_id})
    MATCH (doc:Document {rcept_no: $rcept_no})
    MATCH (d:Date {date: $date})
    MATCH (ed:EventDate {date: $date})
    MERGE (c)-[:INVOLVED_IN]->(e)
    MERGE (e)-[:REPORTED_BY]->(doc)
    MERGE (e)-[:OCCURRED_ON]->(ed)
    MERGE (ed)-[:IS_DATE]->(d)
    MERGE (c)-[:ON_DATE]->(d)
    """

    loaded = 0
    skipped = 0

    for r in rows:
        try:
            rcept_no = str(r[0] or "").strip()
            stock_code = str(r[1] or "").strip().zfill(6) or None
            corp_code = str(r[2] or "").strip() or None
            corp_name = str(r[3] or "").strip() or ""
            rcept_dt = _to_iso_date(r[4]) or ""
            report_type = str(r[5] or "").strip()
            category = str(r[6] or "").strip()
            event_type = str(r[7] or "").strip()
            sentiment_raw = r[8]
            summary = str(r[9] or "").strip()
            required_slots = _safe_json(r[10])
            optional_slots = _safe_json(r[11])
            url = str(r[12] or "").strip()

            if not (rcept_no and corp_code and event_type and rcept_dt):
                skipped += 1
                continue

            event_id = f"EVT_{rcept_no}"
            date_iso = required_slots.get("date") or rcept_dt
            date_iso = _to_iso_date(date_iso) or rcept_dt

            # slots (flatten), keep JSON for debugging
            slots: dict[str, Any] = {}
            for src in (required_slots, optional_slots):
                for k, v in src.items():
                    if k == "date":
                        continue
                    slots[k] = _safe_scalar(v)
            slots["required_slots_json"] = json.dumps(required_slots or {}, ensure_ascii=False)
            slots["optional_slots_json"] = json.dumps(optional_slots or {}, ensure_ascii=False)
            # Store provenance (optional but useful)
            if report_type:
                slots["report_type"] = report_type
            if category:
                slots["category"] = category

            # sentiment clamp (safety)
            try:
                sentiment_score = float(sentiment_raw)
            except Exception:  # noqa: BLE001
                sentiment_score = 0.0
            sentiment_score = max(-1.0, min(1.0, sentiment_score))

            dt_parts = _date_parts(date_iso)

            params_common = {
                "corp_code": corp_code,
                "corp_name": corp_name,
                "stock_code": stock_code,
                "rcept_no": rcept_no,
                "report_nm": report_type or category or "DART_DISCLOSURE",
                "rcept_dt": rcept_dt,
                "url": url,
                "event_id": event_id,
                "event_type": event_type,
                "summary": summary or (report_type or category or ""),
                "sentiment_score": sentiment_score,
                "slots": slots,
                **dt_parts,
            }

            hook.run(cy_company, parameters=params_common)
            hook.run(cy_document, parameters=params_common)
            hook.run(cy_event, parameters=params_common)
            hook.run(cy_date, parameters=params_common)
            hook.run(cy_event_date, parameters=params_common)
            hook.run(cy_edges, parameters=params_common)

            loaded += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load Postgres dart_event_extractions row to Neo4j: %s", exc)
            skipped += 1

    return {"loaded": loaded, "skipped": skipped, "source_rows": len(rows)}


