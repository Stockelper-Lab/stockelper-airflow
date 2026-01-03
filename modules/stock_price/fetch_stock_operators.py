from __future__ import annotations

import logging
from datetime import datetime

import FinanceDataReader as fdr
import pandas as pd
from airflow.models.baseoperator import BaseOperator
from airflow.utils.context import Context

log = logging.getLogger(__name__)

DEFAULT_START_DATE = "2005-01-01"

def _fetch_symbol_dataframe(symbol: str, start_date: str, to_date: str) -> pd.DataFrame | None:
    """
    Fetch daily OHLCV for a single symbol and return standardized DataFrame:
    [symbol, date, open, high, low, close, volume, adj_close]
    """
    yahoo_df: pd.DataFrame | None = None
    yahoo_err: Exception | None = None
    for suffix in ("KS", "KQ"):  # KOSPI=.KS, KOSDAQ=.KQ
        try:
            yahoo_df = fdr.DataReader(f"YAHOO:{symbol}.{suffix}", start=start_date, end=to_date)
            if yahoo_df is not None and not yahoo_df.empty:
                break
        except Exception as e:
            yahoo_df = None
            yahoo_err = e

    naver_df: pd.DataFrame | None = None
    naver_err: Exception | None = None
    try:
        naver_df = fdr.DataReader(f"NAVER:{symbol}", start=start_date, end=to_date)
    except Exception as e:
        naver_df = None
        naver_err = e

    required_cols = ["Open", "High", "Low", "Close", "Volume", "Adj Close"]

    def _normalize(df: pd.DataFrame | None) -> pd.DataFrame | None:
        if df is None or df.empty:
            return None
        d = df.copy()
        # NAVER는 Adj Close 컬럼이 없으므로 Close로 대체
        if "Adj Close" not in d.columns and "Close" in d.columns:
            d["Adj Close"] = d["Close"]
        for c in required_cols:
            if c not in d.columns:
                d[c] = pd.NA
        return d[required_cols]

    y = _normalize(yahoo_df)
    n = _normalize(naver_df)

    if y is None and n is None:
        log.warning(
            "No price data for symbol=%s (yahoo_err=%s, naver_err=%s).",
            symbol,
            yahoo_err,
            naver_err,
        )
        return None

    # If both sources exist, prefer Yahoo values but fill gaps with Naver (covers Yahoo-stale/NaN cases)
    if y is not None and n is not None:
        df = y.combine_first(n)
        source = "YAHOO+NAVER"
    elif y is not None:
        df = y
        source = "YAHOO"
    else:
        df = n
        source = "NAVER"

    # Ensure adj close exists where close exists
    df["Adj Close"] = df["Adj Close"].fillna(df["Close"])
    # Only close is required to keep the row; other columns can be NULL in DB
    df.dropna(subset=["Close"], inplace=True)

    if df.empty:
        log.warning("No data found for symbol %s after processing (source=%s).", symbol, source)
        return df

    df.index.name = "Date"
    df.reset_index(inplace=True)
    df["symbol"] = symbol

    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Adj Close": "adj_close",
            "Date": "date",
        }
    )

    df = df[["symbol", "date", "open", "high", "low", "close", "volume", "adj_close"]]
    return df


class FetchStockDataOperator(BaseOperator):
    """
    단일 주식 종목의 데이터를 가져와서 전처리하고 XCom으로 DataFrame을 반환하는 오퍼레이터
    """

    # NOTE: Do NOT use `start_date`/`end_date` as template fields here.
    # Airflow BaseOperator already has reserved fields with those names, and
    # dynamic task mapping serialization will fail ("Cannot template BaseOperator field").
    template_fields: tuple[str, ...] = ("symbol", "data_start_date", "data_end_date")

    def __init__(
        self,
        symbol: str,
        data_start_date: str | None = None,
        data_end_date: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.symbol = symbol
        self.data_start_date = data_start_date
        self.data_end_date = data_end_date

    def execute(self, context: Context) -> pd.DataFrame | None:
        """
        symbol에 해당하는 주식 데이터를 가져와 전처리 후 DataFrame을 반환합니다.
        """
        to_date = (self.data_end_date or datetime.now().strftime("%Y-%m-%d")).strip()
        start_date = (self.data_start_date or DEFAULT_START_DATE).strip()
        log.info("Fetching and processing data for symbol=%s start=%s end=%s", self.symbol, start_date, to_date)

        df = _fetch_symbol_dataframe(self.symbol, start_date, to_date)
        if df is None:
            return None
        log.info("Processed %s rows for symbol %s.", len(df), self.symbol)
        return df


class FetchStockBatchOperator(BaseOperator):
    """
    여러 종목을 한 태스크에서 처리하기 위한 배치 오퍼레이터.
    Airflow의 동적 매핑 제한(core.max_map_length=1024) 회피용으로 사용합니다.
    """

    template_fields: tuple[str, ...] = ("batch",)

    def __init__(self, batch: list[dict[str, str]], **kwargs):
        super().__init__(**kwargs)
        self.batch = batch

    def execute(self, context: Context) -> pd.DataFrame | None:
        dfs: list[pd.DataFrame] = []
        for item in self.batch:
            sym = str(item.get("symbol", "")).strip()
            if not sym:
                continue
            start = str(item.get("data_start_date") or DEFAULT_START_DATE).strip()
            end = str(item.get("data_end_date") or datetime.now().strftime("%Y-%m-%d")).strip()

            df = _fetch_symbol_dataframe(sym, start, end)
            if df is not None and not df.empty:
                dfs.append(df)

        if not dfs:
            log.info("Batch produced no data (items=%s).", len(self.batch))
            return None

        combined = pd.concat(dfs, ignore_index=True)
        log.info("Processed batch items=%s rows=%s.", len(self.batch), len(combined))
        return combined
