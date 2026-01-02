from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests

from modules.common.logging_config import setup_logger
from modules.common.airflow_settings import get_required_setting, get_setting

logger = setup_logger(__name__)


# NOTE: This mapping must be kept consistent with `stockelper-kg` ontology event types.
REPORT_NM_EVENT_TYPE_RULES: list[tuple[re.Pattern[str], str]] = [
    # Capital / dilution
    (re.compile(r"(유상증자|전환사채|신주인수권부사채|교환사채|전환청구권|증권신고서)", re.IGNORECASE), "CAPITAL_RAISE"),
    # Capital return (shareholder return)
    (re.compile(r"(자기주식).*?(취득|처분|소각)", re.IGNORECASE), "CAPITAL_RETURN"),
    (re.compile(r"(현금|현물)?배당|분기배당|중간배당", re.IGNORECASE), "CAPITAL_RETURN"),
    # Capital structure
    (re.compile(r"감자", re.IGNORECASE), "CAPITAL_STRUCTURE_CHANGE"),
    # Listing status
    (re.compile(r"(상장폐지|거래정지)", re.IGNORECASE), "LISTING_STATUS_CHANGE"),
    # M&A / governance
    (re.compile(r"(주식양수도|영업양수도|합병|타법인).*?(취득|처분)|인수", re.IGNORECASE), "STRATEGY_MNA"),
    (re.compile(r"분할합병|분할", re.IGNORECASE), "STRATEGY_SPINOFF"),
    (re.compile(r"(최대주주).*?변경|주요주주.*변동", re.IGNORECASE), "OWNERSHIP_CHANGE"),
    # Business
    (re.compile(r"(단일판매|공급계약|중요계약).*?(체결|해지)", re.IGNORECASE), "DEMAND_SALES_CONTRACT"),
    (re.compile(r"(영업\(잠정\)실적|손익구조).*?(변경)?", re.IGNORECASE), "REVENUE_EARNINGS"),
    (re.compile(r"(공장|사업장).*?(가동중단|재가동)", re.IGNORECASE), "SUPPLY_HALT"),
    # Legal / crisis
    (re.compile(r"(소송|판결)", re.IGNORECASE), "LEGAL_LITIGATION"),
    (re.compile(r"(횡령|배임|회생절차|미상환|부도)", re.IGNORECASE), "CRISIS_EVENT"),
]


# Minimal slot schema for LLM instruction (do not overfit; missing fields are allowed).
EVENT_SLOT_SCHEMA: dict[str, dict[str, list[str]]] = {
    "CAPITAL_RAISE": {
        "required": ["date"],
        "optional": [
            "raise_type",
            "amount",
            "counterparty",
            "issue_price",
            "dilution_ratio",
            "purpose",
        ],
    },
    "CAPITAL_RETURN": {
        "required": ["date"],
        "optional": ["action_type", "amount", "share_count", "method", "purpose"],
    },
    "CAPITAL_STRUCTURE_CHANGE": {
        "required": ["date"],
        "optional": ["change_ratio", "reason", "method", "impact"],
    },
    "LISTING_STATUS_CHANGE": {
        "required": ["date"],
        "optional": ["action_type", "reason", "status", "authority"],
    },
    "STRATEGY_MNA": {
        "required": ["counterparty", "deal_value", "date"],
        "optional": ["region", "mna_type", "stake_percentage"],
    },
    "STRATEGY_SPINOFF": {
        "required": ["counterparty", "date"],
        "optional": ["deal_value", "region", "spinoff_type"],
    },
    "OWNERSHIP_CHANGE": {
        "required": ["actor", "stake_change", "date"],
        "optional": ["purpose", "value"],
    },
    "DEMAND_SALES_CONTRACT": {
        "required": ["counterparty", "contract_value", "date"],
        "optional": ["duration", "product_id"],
    },
    "REVENUE_EARNINGS": {
        "required": ["period", "metric", "value", "date"],
        "optional": ["consensus_comparison", "previous_comparison"],
    },
    "SUPPLY_HALT": {
        "required": ["date"],
        "optional": ["facility_id", "duration", "reason", "impact"],
    },
    "LEGAL_LITIGATION": {
        "required": ["counterparty", "date"],
        "optional": ["claim_value", "court", "litigation_type"],
    },
    "CRISIS_EVENT": {
        "required": ["incident_type", "location", "date"],
        "optional": ["impact", "cause", "damage_estimate"],
    },
    "OTHER": {"required": ["description", "date"], "optional": []},
}


def guess_event_type(report_nm: str) -> str | None:
    report_nm = (report_nm or "").strip()
    if not report_nm:
        return None
    for pattern, etype in REPORT_NM_EVENT_TYPE_RULES:
        if pattern.search(report_nm):
            return etype
    return None


def normalize_summary_for_key(text: str) -> str:
    s = (text or "").strip().lower()
    s = re.sub(r"\\s+", " ", s)
    s = re.sub(r"[^0-9a-z가-힣 %\\.\\-_/]+", "", s)
    return s[:240]


def compute_event_key(*, stock_code: str, date: str, event_type: str, summary: str) -> str:
    material = f"{stock_code}|{date}|{event_type}|{normalize_summary_for_key(summary)}"
    return hashlib.sha1(material.encode("utf-8")).hexdigest()


def truncate_text(text: str, *, max_chars: int = 6000) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    head = text[: int(max_chars * 0.7)]
    tail = text[-int(max_chars * 0.3) :]
    return head + "\n...\n" + tail


def _parse_json_object(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty LLM response")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: find first JSON object substring
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


@dataclass
class ExtractedEvent:
    event_type: str
    corp_name: str
    summary: str
    required_slots: dict[str, Any]
    optional_slots: dict[str, Any]
    sentiment_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "corp_name": self.corp_name,
            "summary": self.summary,
            "required_slots": self.required_slots,
            "optional_slots": self.optional_slots,
            "sentiment_score": self.sentiment_score,
        }


class OpenAIEventExtractor:
    """LLM-based event + sentiment extractor using OpenAI Chat Completions via HTTP."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 60.0,
    ):
        # Prefer Airflow Variables, fallback to env
        self.api_key = api_key or get_required_setting("OPENAI_API_KEY")
        self.model = model or get_setting("OPENAI_MODEL", "gpt-5.1")
        self.timeout_seconds = timeout_seconds

    def extract(
        self,
        *,
        corp_name: str,
        stock_code: str,
        report_nm: str,
        rcept_dt: str,
        url: str,
        body_text: str,
        event_type_hint: str,
        reported_date_iso: str,
    ) -> ExtractedEvent:
        schema = EVENT_SLOT_SCHEMA.get(event_type_hint) or EVENT_SLOT_SCHEMA["OTHER"]

        body_text = truncate_text(body_text, max_chars=int(os.getenv("DART_DOC_MAX_CHARS", "6000")))

        system = (
            "You are a financial disclosure analyst. "
            "Extract a single most important event from a DART filing and a sentiment score.\n"
            "Return ONLY valid JSON. Do not include markdown."
        )

        user = f"""
[CONTEXT]
- corp_name: {corp_name}
- stock_code: {stock_code}
- report_nm: {report_nm}
- rcept_dt: {rcept_dt}
- url: {url}
- event_type_hint: {event_type_hint}

[BODY_TEXT]
{body_text}

[OUTPUT JSON SCHEMA]
{{
  "event_type": "{event_type_hint}", 
  "corp_name": "{corp_name}",
  "summary": "핵심 요약 1문장 (한국어)",
  "required_slots": {json.dumps({k: "..." for k in schema["required"]}, ensure_ascii=False)},
  "optional_slots": {json.dumps({k: "..." for k in schema["optional"]}, ensure_ascii=False)},
  "sentiment_score": -1.0
}}

[STRICT RULES]
1) event_type MUST be exactly "{event_type_hint}".
2) required_slots MUST include keys: {schema["required"]}. If value is unknown, use:
   - string field: "UNKNOWN"
   - numeric field: 0
3) required_slots.date MUST be "YYYY-MM-DD". If unclear, use reported date: {reported_date_iso}.
4) sentiment_score MUST be a float in [-1.0, 1.0].
"""

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            # Newer OpenAI models use `max_completion_tokens` (and may reject `max_tokens`).
            "max_completion_tokens": 700,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        def _post(p: dict[str, Any]) -> requests.Response:
            return requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=p,
                timeout=self.timeout_seconds,
            )

        res = _post(payload)
        if res.status_code >= 400:
            # Compatibility fallback: some older models/endpoints may not support `max_completion_tokens`.
            try:
                err = res.json()
            except Exception:  # noqa: BLE001
                err = {"raw": res.text}

            unsupported_param = (
                isinstance(err, dict)
                and isinstance(err.get("error"), dict)
                and err["error"].get("code") == "unsupported_parameter"
                and err["error"].get("param") == "max_completion_tokens"
            )
            if unsupported_param:
                fallback_payload = dict(payload)
                fallback_payload.pop("max_completion_tokens", None)
                fallback_payload["max_tokens"] = 700
                res = _post(fallback_payload)
            if res.status_code >= 400:
                # Do not leak secrets; response should not include API keys.
                try:
                    err2 = res.json()
                except Exception:  # noqa: BLE001
                    err2 = res.text
                raise RuntimeError(
                    f"OpenAI chat/completions failed: status={res.status_code}, body={err2}"
                )
        data = res.json()
        content = data["choices"][0]["message"]["content"]
        parsed = _parse_json_object(content)

        required_slots = parsed.get("required_slots") or {}
        optional_slots = parsed.get("optional_slots") or {}
        summary = str(parsed.get("summary") or "").strip() or report_nm

        # Ensure required keys exist
        for k in schema["required"]:
            required_slots.setdefault(k, "UNKNOWN")
        required_slots.setdefault("date", reported_date_iso)

        sentiment = parsed.get("sentiment_score")
        try:
            sentiment_score = float(sentiment)
        except Exception:  # noqa: BLE001
            sentiment_score = 0.0
        sentiment_score = max(-1.0, min(1.0, sentiment_score))

        return ExtractedEvent(
            event_type=event_type_hint,
            corp_name=corp_name,
            summary=summary,
            required_slots=required_slots,
            optional_slots=optional_slots,
            sentiment_score=sentiment_score,
        )


