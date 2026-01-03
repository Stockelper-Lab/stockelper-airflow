from __future__ import annotations

import os
import sys
import re
from dataclasses import asdict
from datetime import datetime
from typing import Any

import FinanceDataReader as fdr
from dateutil.relativedelta import relativedelta

from modules.common.logging_config import setup_logger
from modules.common.airflow_settings import get_required_setting

from .llm_extractor import OpenAIEventExtractor, compute_event_key, guess_event_type
from .mongo_repo import MongoDartRepository
from .opendart_api import (
    OpenDartApiClient,
    build_dart_viewer_url,
    document_xml_to_text,
    normalize_iso_date,
    yyyymmdd,
)
from .universe import UniverseItem, load_universe

logger = setup_logger(__name__)


DEFAULT_FALLBACK_START_DATE = os.getenv("DART_FALLBACK_START_DATE", "20050101")


def _normalize_name_for_lookup(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\s+", "", name)
    return name.lower()


def resolve_universe_items(
    universe: list[UniverseItem],
    corp_rows: list[Any],
) -> list[dict[str, Any]]:
    """Resolve universe items to (stock_code, corp_code, corp_name).

    Supports cases where the universe item only contains `corp_name` (meeting docs),
    and stock_code must be resolved using corpCode.xml (`corp_rows`).
    """

    by_stock_code = {r.stock_code: r for r in corp_rows if getattr(r, "stock_code", None)}
    by_corp_name: dict[str, list[Any]] = {}
    for r in corp_rows:
        corp_name = getattr(r, "corp_name", None)
        if not corp_name:
            continue
        by_corp_name.setdefault(_normalize_name_for_lookup(str(corp_name)), []).append(r)

    resolved: list[dict[str, Any]] = []
    for item in universe:
        if getattr(item, "enabled", True) is False:
            continue

        row = None
        stock_code = getattr(item, "stock_code", None)
        if stock_code:
            row = by_stock_code.get(stock_code)

        if row is None:
            candidates: list[str] = []
            for name in (
                getattr(item, "dart_corp_name", None),
                getattr(item, "corp_name", None),
            ):
                if name:
                    candidates.append(str(name))
            aliases = getattr(item, "aliases", None) or []
            if isinstance(aliases, list):
                candidates.extend([str(a) for a in aliases if str(a).strip()])

            for name in candidates:
                matches = by_corp_name.get(_normalize_name_for_lookup(name)) or []
                if matches:
                    row = matches[0]
                    stock_code = getattr(row, "stock_code", None)
                    break

        if row is None or not stock_code:
            logger.warning("Unable to resolve universe item: %s", item)
            continue

        dart_corp_name = getattr(row, "corp_name", None)
        corp_name = getattr(item, "corp_name", None) or dart_corp_name or stock_code
        resolved.append(
            {
                "stock_code": stock_code,
                "corp_code": getattr(row, "corp_code", None),
                "corp_name": corp_name,
                "dart_corp_name": dart_corp_name,
            }
        )

    return resolved


def _get_mongo_db():
    # NOTE: this import raises if env vars are missing. In Airflow runtime they must exist.
    from modules.common.db_connections import get_db_connection

    return get_db_connection()


def get_listing_date(stock_code: str) -> str:
    """Return listing date as YYYYMMDD if available, else fallback date."""
    try:
        krx = fdr.StockListing("KRX")
        row = krx.loc[krx["Code"] == stock_code]
        if not row.empty and "ListingDate" in row.columns:
            value = row.iloc[0]["ListingDate"]
            if value:
                # FDR returns YYYY-MM-DD
                return yyyymmdd(str(value))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to get listing date from FDR for %s: %s", stock_code, exc)
    return DEFAULT_FALLBACK_START_DATE


def iter_date_chunks(start_yyyymmdd: str, end_yyyymmdd: str, *, months: int = 6):
    start = datetime.strptime(yyyymmdd(start_yyyymmdd), "%Y%m%d")
    end = datetime.strptime(yyyymmdd(end_yyyymmdd), "%Y%m%d")

    cur = start
    while cur <= end:
        nxt = min(cur + relativedelta(months=months) - relativedelta(days=1), end)
        yield cur.strftime("%Y%m%d"), nxt.strftime("%Y%m%d")
        cur = nxt + relativedelta(days=1)


def compute_event_id_from_rcept(*, rcept_no: str, event_type: str) -> str:
    # Same idea as `stockelper-kg` payload.py: use doc_id + event_type.
    import hashlib

    digest = hashlib.sha1(f"{rcept_no}::{event_type}".encode("utf-8")).hexdigest()
    return f"EVT_{digest[:12].upper()}"


def _parse_pblntf_types() -> list[str]:
    raw = os.getenv("DART_PBLNTF_TYPES", "A,B,C,E")
    values = [v.strip().upper() for v in raw.split(",") if v.strip()]
    return values or ["A", "B", "C", "E"]


def bulk_backfill(
    *,
    universe: list[UniverseItem] | None = None,
    end_date: str | None = None,
    chunk_months: int = 6,
) -> dict[str, Any]:
    """Initial backfill from listing date to today (chunked)."""
    universe = universe or load_universe()
    end_date = yyyymmdd(end_date or datetime.utcnow().strftime("%Y%m%d"))

    api_key = get_required_setting("OPEN_DART_API_KEY")

    db = _get_mongo_db()
    repo = MongoDartRepository(db)
    repo.ensure_indexes()

    dart = OpenDartApiClient(api_key, sleep_seconds=float(os.getenv("DART_SLEEP_SECONDS", "0.2")))
    llm = OpenAIEventExtractor()
    pblntf_types = _parse_pblntf_types()

    # Ensure corp_code mapping for universe stocks
    corp_rows = dart.fetch_corp_codes()
    resolved_universe = resolve_universe_items(universe, corp_rows)
    wanted = {item["stock_code"] for item in resolved_universe if item.get("stock_code")}
    repo.upsert_corp_codes([asdict(r) for r in corp_rows if r.stock_code in wanted])

    stats = {
        "stocks": len(resolved_universe),
        "filings_saved": 0,
        "events_saved": 0,
        "events_skipped": 0,
        "stocks_skipped": len(universe) - len(resolved_universe),
    }

    for item in resolved_universe:
        stock_code = item["stock_code"]
        corp_code = item["corp_code"]
        corp_name = item["corp_name"]
        if not corp_code:
            logger.warning("Missing corp_code mapping for stock_code=%s; skipping", stock_code)
            continue

        start_date = get_listing_date(stock_code)
        logger.info("Backfill start: %s (%s) from %s to %s", corp_name, stock_code, start_date, end_date)

        for chunk_start, chunk_end in iter_date_chunks(start_date, end_date, months=chunk_months):
            # gather filings across types
            filings_by_rcept: dict[str, dict[str, Any]] = {}
            for ty in pblntf_types:
                for row in dart.iter_filings(
                    corp_code=corp_code,
                    start_date=chunk_start,
                    end_date=chunk_end,
                    pblntf_ty=ty,
                ):
                    rcept_no = row.get("rcept_no")
                    if rcept_no:
                        filings_by_rcept[str(rcept_no)] = row

            if not filings_by_rcept:
                continue

            # process in chronological order
            rows = list(filings_by_rcept.values())
            rows.sort(key=lambda r: (r.get("rcept_dt") or "", r.get("rcept_no") or ""))

            for row in rows:
                rcept_no = str(row.get("rcept_no") or "").strip()
                rcept_dt = str(row.get("rcept_dt") or "").strip()
                report_nm = str(row.get("report_nm") or "").strip()
                if not rcept_no or not rcept_dt or not report_nm:
                    continue

                event_type_hint = guess_event_type(report_nm)
                if not event_type_hint:
                    # Not a target filing per our current major-event rules
                    continue

                if repo.filing_exists(rcept_no):
                    continue

                url = build_dart_viewer_url(rcept_no)
                doc_xml = dart.fetch_document_xml(rcept_no=rcept_no)
                body_text = document_xml_to_text(doc_xml)

                repo.upsert_filing(
                    {
                        "rcept_no": rcept_no,
                        "corp_code": corp_code,
                        "stock_code": stock_code,
                        "corp_name": corp_name,
                        "rcept_dt": rcept_dt,
                        "report_nm": report_nm,
                        "pblntf_ty": row.get("pblntf_ty"),
                        "pblntf_detail_ty": row.get("pblntf_detail_ty"),
                        "url": url,
                        "body_text": body_text,
                        "raw": row,
                    }
                )
                stats["filings_saved"] += 1

                reported_iso = normalize_iso_date(rcept_dt)
                extracted = llm.extract(
                    corp_name=corp_name,
                    stock_code=stock_code,
                    report_nm=report_nm,
                    rcept_dt=rcept_dt,
                    url=url,
                    body_text=body_text,
                    event_type_hint=event_type_hint,
                    reported_date_iso=reported_iso,
                )

                date_iso = str(extracted.required_slots.get("date") or reported_iso)
                event_key = compute_event_key(
                    stock_code=stock_code,
                    date=date_iso,
                    event_type=event_type_hint,
                    summary=extracted.summary,
                )
                event_id = compute_event_id_from_rcept(rcept_no=rcept_no, event_type=event_type_hint)

                saved = repo.upsert_event(
                    {
                        "event_key": event_key,
                        "event_id": event_id,
                        "event_type": event_type_hint,
                        "date": date_iso,
                        "corp_code": corp_code,
                        "stock_code": stock_code,
                        "corp_name": corp_name,
                        "summary": extracted.summary,
                        "required_slots": extracted.required_slots,
                        "optional_slots": extracted.optional_slots,
                        "sentiment_score": extracted.sentiment_score,
                        "source": {
                            "rcept_no": rcept_no,
                            "report_nm": report_nm,
                            "rcept_dt": rcept_dt,
                            "url": url,
                        },
                    }
                )
                if saved:
                    stats["events_saved"] += 1
                else:
                    stats["events_skipped"] += 1

                repo.update_state(stock_code, last_processed_date=reported_iso)

    logger.info("Bulk backfill done: %s", stats)
    return stats


def daily_update(
    *,
    universe: list[UniverseItem] | None = None,
    run_date: str | None = None,
    lookback_days: int = 3,
) -> dict[str, Any]:
    """Daily incremental update. Intended to be scheduled by Airflow later."""
    universe = universe or load_universe()
    run_date = yyyymmdd(run_date or datetime.utcnow().strftime("%Y%m%d"))

    api_key = get_required_setting("OPEN_DART_API_KEY")

    db = _get_mongo_db()
    repo = MongoDartRepository(db)
    repo.ensure_indexes()

    dart = OpenDartApiClient(api_key, sleep_seconds=float(os.getenv("DART_SLEEP_SECONDS", "0.2")))
    llm = OpenAIEventExtractor()
    pblntf_types = _parse_pblntf_types()

    # Ensure corp_code mapping for universe stocks (refresh from corpCode.xml)
    corp_rows = dart.fetch_corp_codes()
    resolved_universe = resolve_universe_items(universe, corp_rows)
    wanted = {item["stock_code"] for item in resolved_universe if item.get("stock_code")}
    repo.upsert_corp_codes([asdict(r) for r in corp_rows if r.stock_code in wanted])

    stats = {
        "stocks": len(resolved_universe),
        "filings_saved": 0,
        "events_saved": 0,
        "events_skipped": 0,
        "stocks_skipped": len(universe) - len(resolved_universe),
    }

    for item in resolved_universe:
        stock_code = item["stock_code"]
        corp_code = item["corp_code"]
        corp_name = item["corp_name"]
        if not corp_code:
            logger.warning("Missing corp_code mapping for stock_code=%s; skipping", stock_code)
            continue

        state = repo.get_state(stock_code) or {}
        last_processed_iso = str(state.get("last_processed_date") or "")
        if last_processed_iso:
            start_dt = datetime.strptime(last_processed_iso, "%Y-%m-%d") - relativedelta(days=lookback_days)
            start_date = start_dt.strftime("%Y%m%d")
        else:
            start_date = get_listing_date(stock_code)

        # Fetch only recent range
        filings_by_rcept: dict[str, dict[str, Any]] = {}
        for ty in pblntf_types:
            for row in dart.iter_filings(
                corp_code=corp_code,
                start_date=start_date,
                end_date=run_date,
                pblntf_ty=ty,
            ):
                rcept_no = row.get("rcept_no")
                if rcept_no:
                    filings_by_rcept[str(rcept_no)] = row

        rows = list(filings_by_rcept.values())
        rows.sort(key=lambda r: (r.get("rcept_dt") or "", r.get("rcept_no") or ""))

        for row in rows:
            rcept_no = str(row.get("rcept_no") or "").strip()
            rcept_dt = str(row.get("rcept_dt") or "").strip()
            report_nm = str(row.get("report_nm") or "").strip()
            if not rcept_no or not rcept_dt or not report_nm:
                continue

            event_type_hint = guess_event_type(report_nm)
            if not event_type_hint:
                continue

            if repo.filing_exists(rcept_no):
                continue

            url = build_dart_viewer_url(rcept_no)
            doc_xml = dart.fetch_document_xml(rcept_no=rcept_no)
            body_text = document_xml_to_text(doc_xml)

            repo.upsert_filing(
                {
                    "rcept_no": rcept_no,
                    "corp_code": corp_code,
                    "stock_code": stock_code,
                    "corp_name": corp_name,
                    "rcept_dt": rcept_dt,
                    "report_nm": report_nm,
                    "pblntf_ty": row.get("pblntf_ty"),
                    "pblntf_detail_ty": row.get("pblntf_detail_ty"),
                    "url": url,
                    "body_text": body_text,
                    "raw": row,
                }
            )
            stats["filings_saved"] += 1

            reported_iso = normalize_iso_date(rcept_dt)
            extracted = llm.extract(
                corp_name=corp_name,
                stock_code=stock_code,
                report_nm=report_nm,
                rcept_dt=rcept_dt,
                url=url,
                body_text=body_text,
                event_type_hint=event_type_hint,
                reported_date_iso=reported_iso,
            )

            date_iso = str(extracted.required_slots.get("date") or reported_iso)
            event_key = compute_event_key(
                stock_code=stock_code,
                date=date_iso,
                event_type=event_type_hint,
                summary=extracted.summary,
            )
            event_id = compute_event_id_from_rcept(rcept_no=rcept_no, event_type=event_type_hint)

            saved = repo.upsert_event(
                {
                    "event_key": event_key,
                    "event_id": event_id,
                    "event_type": event_type_hint,
                    "date": date_iso,
                    "corp_code": corp_code,
                    "stock_code": stock_code,
                    "corp_name": corp_name,
                    "summary": extracted.summary,
                    "required_slots": extracted.required_slots,
                    "optional_slots": extracted.optional_slots,
                    "sentiment_score": extracted.sentiment_score,
                    "source": {
                        "rcept_no": rcept_no,
                        "report_nm": report_nm,
                        "rcept_dt": rcept_dt,
                        "url": url,
                    },
                }
            )
            if saved:
                stats["events_saved"] += 1
            else:
                stats["events_skipped"] += 1

            repo.update_state(stock_code, last_processed_date=reported_iso)

    logger.info("Daily update done: %s", stats)
    return stats


def _main(argv: list[str]) -> int:
    cmd = (argv[1] if len(argv) > 1 else "").strip().lower()
    if cmd in ("backfill", "bulk"):
        bulk_backfill()
        return 0
    if cmd in ("daily", "update"):
        daily_update()
        return 0
    print("Usage: python -m modules.dart_disclosure.runner [backfill|daily]")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))


