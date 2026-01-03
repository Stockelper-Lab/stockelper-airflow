import logging
import os
import pandas as pd
from sqlalchemy import text
import FinanceDataReader as fdr
import requests
from io import StringIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from modules.postgres.postgres_connector import get_postgres_engine
from modules.common.airflow_settings import get_setting

log = logging.getLogger(__name__)

TABLE_NAME = "daily_stock_price"
DEFAULT_START_DATE = "2005-01-01"


def get_confirmed_eod_end_date() -> str:
    """Return last confirmed trading date (YYYY-MM-DD) for KRX daily close (EOD).

    Strategy:
    - Use KST time to decide the *latest possible* EOD date:
      - before cutoff hour (default 18:00 KST): use yesterday
      - after cutoff hour: allow today
    - Then query KRX's `max_work_dt` endpoint (no-login) to get the latest trading date.

    This avoids mixing "intraday" / "partial today" rows when the DAG runs at 09:00 KST.
    """

    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    cutoff_hour = int(get_setting("STOCK_PRICE_EOD_CUTOFF_HOUR", os.getenv("STOCK_PRICE_EOD_CUTOFF_HOUR", "18")))
    cutoff = now_kst.replace(hour=cutoff_hour, minute=0, second=0, microsecond=0)
    asof_date = now_kst.date() if now_kst >= cutoff else (now_kst.date() - timedelta(days=1))

    try:
        headers = {
            "User-Agent": "Chrome/78.0.3904.87 Safari/537.36",
            "Referer": "http://data.krx.co.kr/",
        }
        url = (
            "http://data.krx.co.kr/comm/bldAttendant/executeForResourceBundle.cmd"
            "?baseName=krx.mdc.i18n.component&key=B128.bld"
        )
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        j = r.json()
        max_work_dt = j["result"]["output"][0]["max_work_dt"]  # YYYYMMDD

        # cutoff 이전에는 today 데이터가 완전히 확정되지 않을 수 있으므로 asof_date로 상한을 둔다.
        asof_yyyymmdd = asof_date.strftime("%Y%m%d")
        if isinstance(max_work_dt, str) and max_work_dt.isdigit():
            max_work_dt = min(max_work_dt, asof_yyyymmdd)
            return f"{max_work_dt[:4]}-{max_work_dt[4:6]}-{max_work_dt[6:8]}"

        log.warning("EOD max_work_dt probe returned unexpected payload; fallback=%s", asof_yyyymmdd)
        return asof_date.strftime("%Y-%m-%d")
    except Exception as exc:
        log.warning("EOD end_date probe failed; fallback=%s err=%s", asof_date, exc)
        return asof_date.strftime("%Y-%m-%d")


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


def get_symbols_to_update() -> list[dict[str, list[dict[str, str]]]]:
    """
    매일 실행 기준으로, "신규 상장 종목" + "기존 종목의 최신 주가"를 모두 수집하기 위한
    (symbol, data_start_date, data_end_date) 작업 리스트를 반환합니다.

    - 신규 종목(테이블에 심볼 없음): (listing date 또는 DEFAULT_START_DATE)부터 적재
    - 기존 종목: 해당 종목의 마지막 date 이후부터(today까지) 증분 적재

    반환 형식(동적 매핑용, batch 단위):
    - Airflow `core.max_map_length` 기본값(1024)을 초과하지 않도록, 심볼 작업을 N개씩 묶어서 반환합니다.
    [
      {"batch": [
        {"symbol": "035420", "data_start_date": "2025-12-31", "data_end_date": "2026-01-02"},
        ...
      ]},
      ...
    ]
    """
    engine = get_postgres_engine()

    # NOTE:
    # - Airflow 동적 매핑(expand_kwargs)은 upstream이 빈 리스트를 반환하면,
    #   mapped task(여기서는 fetch_and_process_stock_data)가 0개로 생성되며 SKIPPED 처리됩니다.
    # - 따라서 심볼 목록 조회 실패 시 "[] 반환"은 전체 파이프라인을 조용히 SKIP 시키는 부작용이 큽니다.
    #
    # KRX 사이트(data.krx.co.kr)가 세션/쿠키 요구로 `LOGOUT`(400)을 응답하는 경우가 있어,
    # FinanceDataReader의 `StockListing("KRX")`가 JSONDecodeError로 실패할 수 있습니다.
    # 기본값을 더 안정적인 `KRX-DESC`로 두고, 그래도 실패하면 DB에 이미 존재하는 심볼로 fallback 합니다.
    listing_market = (
        get_setting(
            "STOCK_PRICE_LISTING_MARKET",
            os.getenv("STOCK_PRICE_LISTING_MARKET", "KRX-DESC"),
        )
        or "KRX-DESC"
    ).strip() or "KRX-DESC"

    try:
        krx_stocks = fdr.StockListing(listing_market)
        krx_stocks["Code"] = krx_stocks["Code"].astype(str).str.zfill(6)
        all_symbols = krx_stocks["Code"].tolist()
        log.info(
            "Fetched %s symbols from listing_market=%s.",
            len(all_symbols),
            listing_market,
        )
    except Exception as e:
        log.error("Failed to fetch stock listings from %s: %s", listing_market, e)

        # Fallback: DB에 이미 적재된 심볼 목록으로 계속 진행(신규 상장 종목은 누락될 수 있음)
        db_symbols: list[str] = []
        try:
            with engine.connect() as conn:
                rows = conn.execute(text(f"SELECT DISTINCT symbol FROM {TABLE_NAME}"))
                db_symbols = [str(r[0]).zfill(6) for r in rows if r and r[0] is not None]
        except Exception as db_e:
            log.error("Also failed to fetch symbol list from DB for fallback: %s", db_e)

        if not db_symbols:
            # 여기까지 오면 심볼을 만들 방법이 없으므로 실패로 처리(=리트라이/알람 가능)
            raise RuntimeError(
                f"Unable to fetch symbol listing from {listing_market} and DB fallback returned empty."
            ) from e

        log.warning(
            "Falling back to %s symbols from DB (new listings may be missed).",
            len(db_symbols),
        )
        all_symbols = db_symbols
        krx_stocks = pd.DataFrame({"Code": all_symbols})

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

    # listing_market 결과에 없는(예: 과거 적재된 심볼/특수 종목 등) 심볼도 DB에 존재한다면 유지
    if last_date_by_symbol:
        db_symbols = {str(s).zfill(6) for s in last_date_by_symbol.keys()}
        merged_symbols = sorted(set(all_symbols) | db_symbols)
        if len(merged_symbols) != len(all_symbols):
            log.warning(
                "listing_market=%s returned %s symbols, DB has %s; using union=%s symbols.",
                listing_market,
                len(all_symbols),
                len(last_date_by_symbol),
                len(merged_symbols),
            )
        all_symbols = merged_symbols

    # 운영 안정성을 위해 최근 N일을 다시 당겨와 upsert(누락/휴장/지연 대비)
    lookback_days = int(get_setting("STOCK_PRICE_LOOKBACK_DAYS", os.getenv("STOCK_PRICE_LOOKBACK_DAYS", "2")))

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
        # 이미 최신 거래일(end_date)까지 적재된 심볼은 스킵 (증분 적재)
        if max_date is not None and max_date >= end_date_dt:
            continue
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

        tasks.append({"symbol": sym, "data_start_date": start, "data_end_date": end_date})

    batch_size = int(get_setting("STOCK_PRICE_TASK_BATCH_SIZE", os.getenv("STOCK_PRICE_TASK_BATCH_SIZE", "200")))
    if batch_size <= 0:
        batch_size = 200

    batches: list[dict[str, list[dict[str, str]]]] = [
        {"batch": tasks[i : i + batch_size]} for i in range(0, len(tasks), batch_size)
    ]
    log.info(
        "Prepared %s update tasks into %s batches (batch_size=%s, lookback_days=%s).",
        len(tasks),
        len(batches),
        batch_size,
        lookback_days,
    )

    # For testing, you can uncomment the lines below to process a small subset.
    # tasks = tasks[:50]
    # return [{"batch": tasks}]
    return batches


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
