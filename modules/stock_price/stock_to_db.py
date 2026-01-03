import logging
import os
import pandas as pd
from sqlalchemy import text
import FinanceDataReader as fdr
from io import StringIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from modules.postgres.postgres_connector import get_postgres_engine

log = logging.getLogger(__name__)

TABLE_NAME = "daily_stock_price"
DEFAULT_START_DATE = "2005-01-01"


def get_confirmed_eod_end_date() -> str:
    """Return last confirmed trading date (YYYY-MM-DD) for KRX daily close (EOD).

    Strategy:
    - Use KST time to decide the *latest possible* EOD date:
      - before cutoff hour (default 18:00 KST): use yesterday
      - after cutoff hour: allow today
    - Then query FinanceDataReader(KRX) for a stable ticker and pick the last available date.

    This avoids mixing "intraday" / "partial today" rows when the DAG runs at 09:00 KST.
    """

    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    cutoff_hour = int(os.getenv("STOCK_PRICE_EOD_CUTOFF_HOUR", "18"))
    cutoff = now_kst.replace(hour=cutoff_hour, minute=0, second=0, microsecond=0)
    asof_date = now_kst.date() if now_kst >= cutoff else (now_kst.date() - timedelta(days=1))

    cal_ticker = os.getenv("STOCK_PRICE_CAL_TICKER", "005930").strip() or "005930"
    cal_lookback_days = int(os.getenv("STOCK_PRICE_CAL_LOOKBACK_DAYS", "30"))

    start = (asof_date - timedelta(days=cal_lookback_days)).strftime("%Y-%m-%d")
    end = asof_date.strftime("%Y-%m-%d")

    try:
        df = fdr.DataReader(f"KRX:{cal_ticker}", start=start, end=end)
        if df is None or df.empty:
            log.warning("EOD calendar probe returned empty; fallback end=%s", end)
            return end
        last_dt = pd.Timestamp(df.index.max()).date()
        return last_dt.strftime("%Y-%m-%d")
    except Exception as exc:
        log.warning("EOD end_date probe failed; fallback end=%s err=%s", end, exc)
        return end


def setup_database_table():
    """
    주식 가격을 저장할 테이블을 생성합니다.
    """
    engine = get_postgres_engine()
    with engine.begin() as conn:
        conn.execute(
            text(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(10) NOT NULL,
                date DATE NOT NULL,
                open NUMERIC(12, 2),
                high NUMERIC(12, 2),
                low NUMERIC(12, 2),
                close NUMERIC(12, 2),
                volume BIGINT,
                adj_close NUMERIC(12, 6),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, date)
            );
            
            CREATE INDEX IF NOT EXISTS idx_symbol_date ON {TABLE_NAME}(symbol, date);
            CREATE INDEX IF NOT EXISTS idx_date ON {TABLE_NAME}(date);
        """)
        )
    log.info(f"Table '{TABLE_NAME}' is ready.")


def get_symbols_to_update() -> list[dict[str, str]]:
    """
    매일 실행 기준으로, "신규 상장 종목" + "기존 종목의 최신 주가"를 모두 수집하기 위한
    (symbol, start_date) 작업 리스트를 반환합니다.

    - 신규 종목(테이블에 심볼 없음): (listing date 또는 DEFAULT_START_DATE)부터 적재
    - 기존 종목: 해당 종목의 마지막 date 이후부터(today까지) 증분 적재

    반환 형식(동적 매핑용):
    [
      {"symbol": "035420", "start_date": "2025-12-31"},
      ...
    ]
    """
    engine = get_postgres_engine()

    try:
        krx_stocks = fdr.StockListing("KRX")
        krx_stocks["Code"] = krx_stocks["Code"].astype(str).str.zfill(6)
        all_symbols = krx_stocks["Code"].tolist()
        log.info("Fetched %s symbols from KRX.", len(all_symbols))
    except Exception as e:
        log.error(f"Failed to fetch stock listings from KRX: {e}")
        return []

    # Global end_date: last confirmed EOD close date for KRX (YYYY-MM-DD)
    end_date = get_confirmed_eod_end_date()
    end_date_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    log.info("Confirmed EOD end_date=%s (KST cutoff controlled).", end_date)

    try:
        with engine.connect() as conn:
            # 종목별 마지막 저장일 조회
            rows = conn.execute(
                text(f"SELECT symbol, MAX(date) AS max_date FROM {TABLE_NAME} GROUP BY symbol")
            )
            last_date_by_symbol = {str(r[0]): r[1] for r in rows}
        log.info("Found %s symbols in the database.", len(last_date_by_symbol))
    except Exception as e:
        log.warning("Could not fetch existing symbol max(date); assuming empty. err=%s", e)
        last_date_by_symbol = {}

    # 운영 안정성을 위해 최근 N일을 다시 당겨와 upsert(누락/휴장/지연 대비)
    lookback_days = int(os.getenv("STOCK_PRICE_LOOKBACK_DAYS", "2"))

    tasks: list[dict[str, str]] = []

    # listing date가 있으면 신규 종목의 start를 더 정확히 잡아준다.
    listing_date_by_symbol: dict[str, str] = {}
    if "ListingDate" in krx_stocks.columns:
        try:
            tmp = krx_stocks[["Code", "ListingDate"]].dropna()
            for _, row in tmp.iterrows():
                code = str(row["Code"]).zfill(6)
                # FDR: YYYY-MM-DD 또는 datetime
                ld = str(row["ListingDate"])
                listing_date_by_symbol[code] = ld[:10]
        except Exception:
            listing_date_by_symbol = {}

    for sym in all_symbols:
        max_date = last_date_by_symbol.get(sym)
        if max_date is None:
            start = listing_date_by_symbol.get(sym) or DEFAULT_START_DATE
        else:
            # date 컬럼은 DATE 타입이므로 Python date로 들어옴
            start_dt = max_date - timedelta(days=lookback_days) if lookback_days > 0 else max_date + timedelta(days=1)
            # lookback_days 사용 시: max_date 포함해서 재수집(upsert)
            start = start_dt.strftime("%Y-%m-%d")

        # start가 end_date보다 미래면 스킵(할 일 없음)
        try:
            if datetime.strptime(start, "%Y-%m-%d").date() > end_date_dt:
                continue
        except Exception:
            # 형식이 이상하면 기본값으로
            start = DEFAULT_START_DATE

        tasks.append({"symbol": sym, "start_date": start, "end_date": end_date})

    log.info("Prepared %s update tasks (lookback_days=%s).", len(tasks), lookback_days)

    # For testing, you can uncomment the line below to process a small subset.
    # return tasks[:50]
    return tasks


def bulk_upsert(df: pd.DataFrame):
    """
    DataFrame을 DB에 배치 UPSERT 수행
    """
    if df.empty:
        log.info("No data to upsert.")
        return

    engine = get_postgres_engine()
    temp_table = f"{TABLE_NAME}_temp_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S%f')}"

    # Get the DDL for the temp table from pandas, ensuring correct dialect from connection
    with engine.connect() as conn:
        schema_sql = pd.io.sql.get_schema(df, temp_table, con=conn)

    try:
        df.to_sql(temp_table, engine, if_exists="replace", index=False, method="multi")
        with engine.begin() as conn:
            conn.execute(
                text(f"""
                INSERT INTO {TABLE_NAME} (symbol, date, open, high, low, close, volume, adj_close)
                SELECT symbol, date, open, high, low, close, volume, adj_close
                FROM {temp_table}
                ON CONFLICT (symbol, date) 
                DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    adj_close = EXCLUDED.adj_close;
            """)
            )

        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {temp_table};"))

        log.info(f"Successfully upserted {len(df)} rows.")

    except Exception as e:
        log.error(f"Bulk upsert failed: {e}")
        try:
            with engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {temp_table};"))
        except Exception as cleanup_e:
            log.error(f"Failed to drop temporary table {temp_table}: {cleanup_e}")
        raise e


def load_data_to_postgres(**kwargs):
    """
    XCom에서 DataFrame 리스트를 받아 하나로 합쳐 DB에 적재합니다.
    """
    ti = kwargs["ti"]

    processed_data = ti.xcom_pull(task_ids="fetch_and_process_stock_data")
    if processed_data is not None:
        valid_dfs = [df for df in processed_data if df is not None and not df.empty]
    else:
        valid_dfs = []

    if not valid_dfs:
        log.info("No dataframes to load.")
        return

    combined_df = pd.concat(valid_dfs, ignore_index=True)
    log.info(
        f"Combined {len(valid_dfs)} dataframes into one with {len(combined_df)} total rows."
    )

    bulk_upsert(combined_df)
