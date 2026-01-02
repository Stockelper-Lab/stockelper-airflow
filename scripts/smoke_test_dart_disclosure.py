from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on sys.path so `modules.*` imports work when running this file directly.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from modules.common.airflow_settings import get_required_setting, get_setting
from modules.common.logging_config import setup_logger
from modules.dart_disclosure.llm_extractor import (
    EVENT_SLOT_SCHEMA,
    OpenAIEventExtractor,
    compute_event_key,
    guess_event_type,
)
from modules.dart_disclosure.opendart_api import (
    OpenDartApiClient,
    build_dart_viewer_url,
    document_xml_to_text,
    normalize_iso_date,
)

logger = setup_logger(__name__)


def _is_iso_date(value: object) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", str(value or "")))


def main() -> int:
    # Load local .env for dev runs (Airflow runtime will use Variables or env).
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Smoke test: OpenDART(list/document) -> LLM extraction(event+sentiment)"
    )
    parser.add_argument(
        "--stock-code",
        default=get_setting("DART_SMOKE_STOCK_CODE", "035420"),
        help="6-digit KRX stock code (default: 035420)",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=int(get_setting("DART_SMOKE_LOOKBACK_DAYS", "365")),
        help="How many days to look back for filings (default: 365)",
    )
    parser.add_argument(
        "--max-filings",
        type=int,
        default=int(get_setting("DART_SMOKE_MAX_FILINGS", "8")),
        help="Max filings to try until a non-empty document is found (default: 8)",
    )
    parser.add_argument(
        "--min-text-chars",
        type=int,
        default=int(get_setting("DART_SMOKE_MIN_TEXT_CHARS", "200")),
        help="Minimum extracted text length to accept a document (default: 200)",
    )
    parser.add_argument(
        "--prefer-non-other",
        action="store_true",
        default=True,
        help="Prefer a filing whose guessed event_type is not OTHER (default: true)",
    )
    parser.add_argument(
        "--no-prefer-non-other",
        action="store_true",
        help="Disable prefer-non-other behavior (always pick first usable document).",
    )
    parser.add_argument(
        "--prefer-event-types",
        default=get_setting("DART_SMOKE_PREFER_EVENT_TYPES"),
        help='Comma-separated event_type list to prefer (e.g. "CAPITAL_RAISE,CAPITAL_RETURN"). Optional.',
    )
    parser.add_argument(
        "--show-candidates",
        action="store_true",
        help="Log scanned candidates with guessed event_type.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip OpenAI extraction (only validate OpenDART calls)",
    )
    args = parser.parse_args()

    open_dart_api_key = get_required_setting("OPEN_DART_API_KEY")
    if not args.no_llm:
        _ = get_required_setting("OPENAI_API_KEY")

    if args.no_prefer_non_other:
        args.prefer_non_other = False

    prefer_types: list[str] = []
    if args.prefer_event_types:
        prefer_types = [x.strip() for x in str(args.prefer_event_types).split(",") if x.strip()]

    client = OpenDartApiClient(api_key=open_dart_api_key, sleep_seconds=0.2, timeout_seconds=30.0)

    logger.info("Fetching corpCode.xml ... (this may take a bit)")
    corp_rows = client.fetch_corp_codes()
    row = next((r for r in corp_rows if r.stock_code == args.stock_code), None)
    if row is None:
        raise RuntimeError(f"corp_code not found for stock_code={args.stock_code}")

    corp_code = row.corp_code
    corp_name = row.corp_name
    logger.info("Resolved stock_code=%s -> corp_code=%s (corp_name=%s)", args.stock_code, corp_code, corp_name)

    today = datetime.now()
    start = today - timedelta(days=args.lookback_days)
    start_date = start.strftime("%Y%m%d")
    end_date = today.strftime("%Y%m%d")

    logger.info("Listing filings: %s..%s (max_filings=%s)", start_date, end_date, args.max_filings)
    filings: list[dict] = []
    for filing in client.iter_filings(corp_code=corp_code, start_date=start_date, end_date=end_date):
        filings.append(filing)
        if len(filings) >= args.max_filings:
            break

    if not filings:
        logger.warning("No filings found for %s in %s..%s", args.stock_code, start_date, end_date)
        return 2

    # Prefer more "meaningful" filings by title before fetching document.xml (cheaper).
    candidates: list[dict] = []
    for filing in filings:
        report_nm = str(filing.get("report_nm") or "").strip()
        et = guess_event_type(report_nm) or "OTHER"
        candidate = dict(filing)
        candidate["_guessed_event_type"] = et
        candidates.append(candidate)

    if args.show_candidates:
        for i, c in enumerate(candidates, start=1):
            logger.info(
                "candidate[%s] rcept_dt=%s type=%s report_nm=%s",
                i,
                c.get("rcept_dt"),
                c.get("_guessed_event_type"),
                c.get("report_nm"),
            )

    def _is_preferred(c: dict) -> bool:
        et = str(c.get("_guessed_event_type") or "OTHER")
        if prefer_types:
            return et in prefer_types
        if args.prefer_non_other:
            return et != "OTHER"
        return True

    ordered = [c for c in candidates if _is_preferred(c)] + [c for c in candidates if not _is_preferred(c)]

    chosen_row: dict | None = None
    chosen_text: str | None = None
    chosen_xml_len: int | None = None

    for filing in ordered:
        rcept_no = (filing.get("rcept_no") or "").strip()
        if not rcept_no:
            continue
        report_nm = str(filing.get("report_nm") or "").strip()
        rcept_dt = str(filing.get("rcept_dt") or "").strip()

        logger.info("Fetching document.xml: rcept_no=%s report_nm=%s rcept_dt=%s", rcept_no, report_nm, rcept_dt)
        doc_xml = client.fetch_document_xml(rcept_no=rcept_no)
        text = document_xml_to_text(doc_xml)
        if len(text) < int(args.min_text_chars):
            logger.info("Document too short/empty (%s chars), trying next filing...", len(text))
            continue

        chosen_row = filing
        chosen_text = text
        chosen_xml_len = len(doc_xml or "")
        break

    if chosen_row is None or chosen_text is None:
        logger.warning("Could not find a non-empty document among %s filings", len(filings))
        return 3

    rcept_no = str(chosen_row.get("rcept_no") or "").strip()
    report_nm = str(chosen_row.get("report_nm") or "").strip()
    rcept_dt = str(chosen_row.get("rcept_dt") or "").strip()
    url = build_dart_viewer_url(rcept_no)

    event_type_hint = str(chosen_row.get("_guessed_event_type") or guess_event_type(report_nm) or "OTHER")
    if event_type_hint not in EVENT_SLOT_SCHEMA:
        event_type_hint = "OTHER"

    reported_date_iso = normalize_iso_date(rcept_dt) if rcept_dt else today.strftime("%Y-%m-%d")

    logger.info("Chosen filing: rcept_no=%s report_nm=%s", rcept_no, report_nm)
    logger.info("DART viewer url: %s", url)
    logger.info("Document XML length: %s, text length: %s", chosen_xml_len, len(chosen_text))
    logger.info("Text preview (first 300 chars): %s", chosen_text[:300].replace("\n", " "))
    logger.info("Event type hint: %s", event_type_hint)

    if args.no_llm:
        logger.info("--no-llm set; skipping OpenAI extraction.")
        return 0

    extractor = OpenAIEventExtractor()
    extracted = extractor.extract(
        corp_name=corp_name,
        stock_code=args.stock_code,
        report_nm=report_nm,
        rcept_dt=rcept_dt,
        url=url,
        body_text=chosen_text,
        event_type_hint=event_type_hint,
        reported_date_iso=reported_date_iso,
    )

    errors: list[str] = []
    if extracted.event_type != event_type_hint:
        errors.append(f"event_type mismatch: got={extracted.event_type}, expected={event_type_hint}")
    if extracted.event_type not in EVENT_SLOT_SCHEMA:
        errors.append(f"unknown event_type: {extracted.event_type}")
    if not (-1.0 <= float(extracted.sentiment_score) <= 1.0):
        errors.append(f"sentiment_score out of range: {extracted.sentiment_score}")

    required_keys = (EVENT_SLOT_SCHEMA.get(event_type_hint) or EVENT_SLOT_SCHEMA["OTHER"])["required"]
    for k in required_keys:
        if k not in (extracted.required_slots or {}):
            errors.append(f"missing required_slots key: {k}")

    if "date" in (extracted.required_slots or {}) and not _is_iso_date(extracted.required_slots.get("date")):
        errors.append(f"required_slots.date is not ISO YYYY-MM-DD: {extracted.required_slots.get('date')}")

    date_for_key = str((extracted.required_slots or {}).get("date") or reported_date_iso)
    event_key = compute_event_key(
        stock_code=args.stock_code,
        date=date_for_key,
        event_type=extracted.event_type,
        summary=extracted.summary,
    )

    print("\n=== SMOKE TEST RESULT ===")
    print(json.dumps(
        {
            "input": {
                "stock_code": args.stock_code,
                "corp_code": corp_code,
                "corp_name": corp_name,
                "lookback_days": args.lookback_days,
                "chosen": {
                    "rcept_no": rcept_no,
                    "report_nm": report_nm,
                    "rcept_dt": rcept_dt,
                    "url": url,
                    "event_type_hint": event_type_hint,
                    "reported_date_iso": reported_date_iso,
                    "text_length": len(chosen_text),
                },
            },
            "extracted": asdict(extracted),
            "derived": {"event_key": event_key},
            "validation": {"ok": not errors, "errors": errors},
        },
        ensure_ascii=False,
        indent=2,
    ))

    return 0 if not errors else 10


if __name__ == "__main__":
    raise SystemExit(main())


