from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from modules.common.airflow_settings import get_setting
from modules.common.logging_config import setup_logger

logger = setup_logger(__name__)


@dataclass(frozen=True)
class UniverseItem:
    """Stock universe item (supports gradual enrichment).

    Notes:
    - For DART ingestion, we ultimately need `corp_code` and `stock_code`.
    - If `stock_code` is missing, we can resolve it using corpCode.xml by name.
    """

    stock_code: str | None = None
    corp_name: str | None = None
    dart_corp_name: str | None = None
    aliases: list[str] = field(default_factory=list)
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


DEFAULT_UNIVERSE: list[UniverseItem] = [
    # Source: docs/references/20251208.md, 20251215.md (AI sector initial focus)
    UniverseItem(stock_code="035420", corp_name="네이버", dart_corp_name="NAVER", tags=["ai", "bigtech"]),
    UniverseItem(stock_code="035720", corp_name="카카오", tags=["ai", "bigtech"]),
    UniverseItem(stock_code="047560", corp_name="이스트소프트", tags=["ai", "software"]),
    UniverseItem(corp_name="와이즈넛", tags=["ai", "software"]),
    UniverseItem(corp_name="코난테크놀로지", tags=["ai", "software"]),
    UniverseItem(corp_name="마음AI", tags=["ai", "software"]),
    UniverseItem(corp_name="엑셈", tags=["ai", "software"]),
    UniverseItem(corp_name="플리토", tags=["ai", "data"]),
    UniverseItem(corp_name="알체라", tags=["ai", "vision"]),
    UniverseItem(corp_name="한국전자인증", tags=["ai", "security"]),
    UniverseItem(corp_name="레인보우로보틱스", tags=["ai", "robotics"]),
    UniverseItem(corp_name="유진로봇", tags=["ai", "robotics"]),
    UniverseItem(corp_name="로보로보", tags=["ai", "robotics"]),
    UniverseItem(corp_name="큐렉소", tags=["ai", "robotics"]),
]


def _normalize_stock_code(code: str | None) -> str | None:
    code = (code or "").strip()
    if not code:
        return None
    if not code.isdigit():
        raise ValueError(f"stock_code must be digits only: {code}")
    return code.zfill(6)


def load_universe(
    universe_json_path: str | None = None,
    fallback: Iterable[UniverseItem] = DEFAULT_UNIVERSE,
) -> list[UniverseItem]:
    """Load stock universe.

    Priority:
    1) `universe_json_path` argument
    2) Airflow Variable / env var `DART_UNIVERSE_JSON`
    3) Airflow Variable / env var `DART_STOCK_CODES` (comma-separated codes)
    4) fallback list (DEFAULT_UNIVERSE)
    """

    if not universe_json_path:
        universe_json_path = get_setting("DART_UNIVERSE_JSON")

    if universe_json_path:
        path = Path(universe_json_path).expanduser()
        data = json.loads(path.read_text(encoding="utf-8"))
        items: list[UniverseItem] = []
        for row in data:
            if isinstance(row, str):
                code = _normalize_stock_code(row)
                if not code:
                    continue
                items.append(UniverseItem(stock_code=code))
                continue
            if not isinstance(row, dict):
                raise ValueError(f"Invalid universe row: {row!r}")

            enabled = row.get("enabled", True)
            if enabled is False:
                continue

            stock_code = _normalize_stock_code(row.get("stock_code"))
            corp_name = row.get("corp_name") or row.get("name") or None
            dart_corp_name = row.get("dart_corp_name") or row.get("corp_name_dart") or None

            aliases_raw = row.get("aliases") or []
            aliases = [str(x).strip() for x in aliases_raw if str(x).strip()] if isinstance(aliases_raw, list) else []

            tags_raw = row.get("tags") or []
            tags = [str(x).strip() for x in tags_raw if str(x).strip()] if isinstance(tags_raw, list) else []

            items.append(
                UniverseItem(
                    stock_code=stock_code,
                    corp_name=corp_name,
                    dart_corp_name=dart_corp_name,
                    aliases=aliases,
                    enabled=True,
                    tags=tags,
                )
            )
        logger.info("Loaded universe from JSON: %s items", len(items))
        return items

    if env_codes := get_setting("DART_STOCK_CODES"):
        items = [
            UniverseItem(stock_code=_normalize_stock_code(code))
            for code in env_codes.split(",")
            if code.strip()
        ]
        items = [item for item in items if item.stock_code]
        logger.info("Loaded universe from DART_STOCK_CODES: %s items", len(items))
        return items

    items = list(fallback)
    logger.info("Loaded universe from fallback: %s items", len(items))
    return items


