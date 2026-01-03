from __future__ import annotations

import io
import time
import zipfile
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from modules.common.logging_config import setup_logger

logger = setup_logger(__name__)


OPENDART_BASE_URL = "https://opendart.fss.or.kr/api"


def build_dart_viewer_url(rcept_no: str) -> str:
    """Human-friendly DART viewer URL."""
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


def yyyymmdd(date_value: str | datetime) -> str:
    if isinstance(date_value, datetime):
        return date_value.strftime("%Y%m%d")
    s = (date_value or "").strip()
    if len(s) == 10 and "-" in s:
        return s.replace("-", "")
    if len(s) == 8 and s.isdigit():
        return s
    raise ValueError(f"Invalid date format: {date_value!r}")


def normalize_iso_date(date_yyyymmdd: str) -> str:
    s = yyyymmdd(date_yyyymmdd)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


@dataclass(frozen=True)
class CorpCodeRow:
    corp_code: str
    corp_name: str
    stock_code: str
    modify_date: str | None = None


class OpenDartApiClient:
    """Minimal OpenDART(Open API) client with rate limiting & retries."""

    def __init__(
        self,
        api_key: str,
        *,
        sleep_seconds: float = 0.2,
        timeout_seconds: float = 30.0,
        max_retries: int = 4,
    ):
        self.api_key = api_key
        self.sleep_seconds = sleep_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.session = requests.Session()

    def _sleep(self):
        if self.sleep_seconds > 0:
            time.sleep(self.sleep_seconds)

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> requests.Response:
        url = f"{OPENDART_BASE_URL}/{path.lstrip('/')}"
        base_params = {"crtfc_key": self.api_key}
        merged = {**base_params, **(params or {})}

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self._sleep()
                res = self.session.get(
                    url,
                    params=merged,
                    timeout=self.timeout_seconds,
                    stream=stream,
                )
                res.raise_for_status()
                return res
            except Exception as exc:  # noqa: BLE001 - controlled retry
                last_exc = exc
                wait = min(2 ** (attempt - 1), 8)
                logger.warning("OpenDART GET retry %s/%s: %s (wait=%ss)", attempt, self.max_retries, exc, wait)
                time.sleep(wait)
        raise RuntimeError(f"OpenDART request failed: {url}") from last_exc

    # --- corpCode.xml ---
    def fetch_corp_codes(self) -> list[CorpCodeRow]:
        """Download and parse corpCode.xml (zip) and return rows with stock_code."""
        res = self._get("corpCode.xml", stream=True)
        content = res.content

        zf = zipfile.ZipFile(io.BytesIO(content))
        # Usually a single xml file inside the zip
        xml_name = zf.namelist()[0]
        xml_bytes = zf.read(xml_name)

        root = ET.fromstring(xml_bytes)
        rows: list[CorpCodeRow] = []
        for item in root.findall("list"):
            corp_code = (item.findtext("corp_code") or "").strip()
            corp_name = (item.findtext("corp_name") or "").strip()
            stock_code = (item.findtext("stock_code") or "").strip()
            modify_date = (item.findtext("modify_date") or "").strip() or None
            if not stock_code:
                continue
            rows.append(
                CorpCodeRow(
                    corp_code=corp_code,
                    corp_name=corp_name,
                    stock_code=stock_code.zfill(6),
                    modify_date=modify_date,
                )
            )
        logger.info("Parsed corpCode.xml: %s listed companies (with stock_code)", len(rows))
        return rows

    # --- list.json ---
    def list_filings(
        self,
        *,
        corp_code: str,
        start_date: str,
        end_date: str,
        pblntf_ty: str | None = None,
        page_no: int = 1,
        page_count: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "corp_code": corp_code,
            "bgn_de": yyyymmdd(start_date),
            "end_de": yyyymmdd(end_date),
            "page_no": page_no,
            "page_count": page_count,
        }
        if pblntf_ty:
            params["pblntf_ty"] = pblntf_ty

        res = self._get("list.json", params=params)
        data = res.json()
        return data

    def iter_filings(
        self,
        *,
        corp_code: str,
        start_date: str,
        end_date: str,
        pblntf_ty: str | None = None,
        page_count: int = 100,
    ) -> Iterable[dict[str, Any]]:
        page_no = 1
        while True:
            data = self.list_filings(
                corp_code=corp_code,
                start_date=start_date,
                end_date=end_date,
                pblntf_ty=pblntf_ty,
                page_no=page_no,
                page_count=page_count,
            )
            status = str(data.get("status") or "")
            if status == "013":  # no data
                return
            if status != "000":
                msg = data.get("message")
                raise RuntimeError(f"OpenDART list.json failed: status={status}, message={msg}")

            items = data.get("list") or []
            if not items:
                return

            for row in items:
                if isinstance(row, dict):
                    yield row

            total_count = int(data.get("total_count") or 0)
            if page_no * page_count >= total_count:
                return
            page_no += 1

    # --- document.xml ---
    def fetch_document_xml(self, *, rcept_no: str) -> str:
        """
        Fetch a filing original document from OpenDART.

        Note:
        - OpenDART `document.xml` frequently returns a ZIP (PK...) containing one XML/HTML file.
        - This method transparently unzips and returns the inner file content as text.
        """
        res = self._get("document.xml", params={"rcept_no": rcept_no}, stream=True)
        data = res.content or b""

        # ZIP magic header: PK\x03\x04
        if data.startswith(b"PK"):
            try:
                zf = zipfile.ZipFile(io.BytesIO(data))
                name = zf.namelist()[0]
                raw = zf.read(name)
                for enc in ("utf-8", "cp949", "euc-kr"):
                    try:
                        return raw.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return raw.decode("utf-8", errors="replace")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to unzip OpenDART document.xml (rcept_no=%s): %s", rcept_no, exc)
                return data.decode("utf-8", errors="replace")

        # Non-zip response: rely on requests decoding
        return res.text


def document_xml_to_text(document_xml: str) -> str:
    """Extract readable text from OpenDART document.xml response."""
    if not document_xml:
        return ""

    # 1) Try XML parsing to get CDATA/HTML payload
    html_or_text: str | None = None
    try:
        root = ET.fromstring(document_xml)
        # Typical: <result><status>000</status>...<body>...</body></result>
        status = (root.findtext("status") or "").strip()
        if status and status != "000":
            return ""

        # body/content is not consistent; try multiple tags
        for tag in ("body", "content", "document"):
            candidate = root.findtext(tag)
            if candidate and candidate.strip():
                html_or_text = candidate
                break
    except Exception:  # noqa: BLE001
        html_or_text = None

    if html_or_text is None:
        html_or_text = document_xml

    # 2) Strip markup into plain text
    # Some filings are XML; BeautifulSoup emits XMLParsedAsHTMLWarning when using html.parser.
    # We intentionally parse as HTML here for robustness, so silence the warning.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(html_or_text, "html.parser")
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


