from __future__ import annotations

import datetime as dt
from typing import Any

import pymongo

from modules.common.logging_config import setup_logger

logger = setup_logger(__name__)


class MongoDartRepository:
    """MongoDB persistence for DART filings + derived events."""

    def __init__(
        self,
        db: pymongo.database.Database,
        *,
        corp_codes_collection: str = "dart_corp_codes",
        filings_collection: str = "dart_filings",
        events_collection: str = "dart_events",
        state_collection: str = "dart_ingestion_state",
    ):
        self.db = db
        self.corp_codes = db[corp_codes_collection]
        self.filings = db[filings_collection]
        self.events = db[events_collection]
        self.state = db[state_collection]

    def ensure_indexes(self) -> None:
        # corp codes
        self.corp_codes.create_index([("stock_code", 1)], unique=True)

        # filings
        self.filings.create_index([("rcept_no", 1)], unique=True)
        self.filings.create_index([("stock_code", 1), ("rcept_dt", 1)])

        # events
        self.events.create_index([("event_key", 1)], unique=True)
        self.events.create_index([("stock_code", 1), ("date", 1), ("event_type", 1)])
        self.events.create_index([("source.rcept_no", 1)])

        # state
        self.state.create_index([("stock_code", 1)], unique=True)

        logger.info("Mongo indexes ensured for DART collections.")

    # --- corp code mapping ---
    def upsert_corp_codes(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        ops: list[pymongo.UpdateOne] = []
        now = dt.datetime.utcnow()
        for row in rows:
            stock_code = str(row.get("stock_code") or "").strip()
            corp_code = str(row.get("corp_code") or "").strip()
            corp_name = str(row.get("corp_name") or "").strip()
            if not stock_code or not corp_code:
                continue
            ops.append(
                pymongo.UpdateOne(
                    {"stock_code": stock_code},
                    {
                        "$set": {
                            "stock_code": stock_code,
                            "corp_code": corp_code,
                            "corp_name": corp_name or None,
                            "modify_date": row.get("modify_date"),
                            "updated_at": now,
                        }
                    },
                    upsert=True,
                )
            )
        if ops:
            self.corp_codes.bulk_write(ops, ordered=False)
            logger.info("Upserted corp_code mappings: %s", len(ops))

    def get_corp_code(self, stock_code: str) -> dict[str, Any] | None:
        return self.corp_codes.find_one({"stock_code": stock_code})

    # --- filings ---
    def filing_exists(self, rcept_no: str) -> bool:
        return self.filings.count_documents({"rcept_no": rcept_no}, limit=1) > 0

    def upsert_filing(self, doc: dict[str, Any]) -> None:
        rcept_no = doc.get("rcept_no")
        if not rcept_no:
            raise ValueError("rcept_no is required for filings")

        payload = {**doc}
        payload.setdefault("ingested_at", dt.datetime.utcnow())
        self.filings.update_one({"rcept_no": rcept_no}, {"$set": payload}, upsert=True)

    # --- events ---
    def event_exists(self, event_key: str) -> bool:
        return self.events.count_documents({"event_key": event_key}, limit=1) > 0

    def upsert_event(self, event_doc: dict[str, Any]) -> bool:
        """Upsert event by event_key.

        Returns:
            True if inserted/updated, False if skipped due to duplicate key.
        """
        event_key = event_doc.get("event_key")
        if not event_key:
            raise ValueError("event_key is required for events")

        payload = {**event_doc}
        payload.setdefault("created_at", dt.datetime.utcnow())
        try:
            self.events.update_one({"event_key": event_key}, {"$setOnInsert": payload}, upsert=True)
            return True
        except pymongo.errors.DuplicateKeyError:
            return False

    # --- state ---
    def get_state(self, stock_code: str) -> dict[str, Any] | None:
        return self.state.find_one({"stock_code": stock_code})

    def update_state(self, stock_code: str, *, last_processed_date: str, last_run_at: dt.datetime | None = None) -> None:
        self.state.update_one(
            {"stock_code": stock_code},
            {
                "$set": {
                    "stock_code": stock_code,
                    "last_processed_date": last_processed_date,
                    "last_run_at": last_run_at or dt.datetime.utcnow(),
                }
            },
            upsert=True,
        )


