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


