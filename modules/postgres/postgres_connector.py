from __future__ import annotations

import logging
import os
from typing import Optional

from airflow.hooks.base import BaseHook
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# NOTE:
# - This module is imported by long-running Airflow tasks (e.g. KG rebuild).
# - Creating a brand-new SQLAlchemy Engine per call will create a brand-new connection pool.
#   In date-range loops, that can quickly exhaust Postgres `max_connections` ("too many clients already").
# - Therefore we cache engines per conn_id within the worker process.
_ENGINE_CACHE: dict[str, Engine] = {}


def dispose_postgres_engine(conn_id: Optional[str] = None) -> None:
    """Dispose cached SQLAlchemy engines (close pooled connections).

    If conn_id is None, dispose ALL cached engines.
    """
    global _ENGINE_CACHE
    if conn_id is None:
        for _cid, _eng in list(_ENGINE_CACHE.items()):
            try:
                _eng.dispose()
            except Exception:  # noqa: BLE001
                pass
        _ENGINE_CACHE = {}
        return

    eng = _ENGINE_CACHE.pop(conn_id, None)
    if eng is None:
        return
    try:
        eng.dispose()
    except Exception:  # noqa: BLE001
        pass


def get_postgres_engine(conn_id: str = "postgres_default") -> Engine:
    """
    Airflow Connection에서 PostgreSQL 접속 정보를 가져와 SQLAlchemy 엔진을 생성합니다.

    :param conn_id: Airflow에 설정된 Connection ID
    :return: SQLAlchemy Engine
    """
    try:
        cached = _ENGINE_CACHE.get(conn_id)
        if cached is not None:
            return cached

        # Airflow UI에서 설정된 Connection 정보 가져오기
        conn = BaseHook.get_connection(conn_id)
        
        db_user = conn.login
        db_password = conn.password
        db_host = conn.host
        db_port = conn.port
        db_name = conn.schema

        if not all([db_user, db_password, db_host, db_port, db_name]):
            raise ValueError(f"Connection '{conn_id}' is not configured properly. "
                             "Please ensure host, port, login, password, and schema are set.")

        # Keep connection usage conservative by default.
        # You can override via env vars if needed.
        pool_size = int(os.getenv("POSTGRES_POOL_SIZE", "1"))
        max_overflow = int(os.getenv("POSTGRES_MAX_OVERFLOW", "0"))
        pool_recycle = int(os.getenv("POSTGRES_POOL_RECYCLE_SECONDS", "1800"))

        dsn = f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        engine = create_engine(
            dsn,
            pool_pre_ping=True,
            pool_recycle=pool_recycle,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        _ENGINE_CACHE[conn_id] = engine
        log.info(
            "Successfully created (cached) SQLAlchemy engine for Airflow connection '%s' "
            "(pool_size=%s, max_overflow=%s, pool_recycle=%ss).",
            conn_id,
            pool_size,
            max_overflow,
            pool_recycle,
        )
        return engine

    except Exception as e:
        log.error(f"Failed to create SQLAlchemy engine from Airflow connection '{conn_id}'. "
                  f"Please check your connection settings in the Airflow UI. Error: {e}")
        raise

if __name__ == '__main__':
    # 이 모듈은 Airflow 환경 외부에서 직접 실행하면 Airflow Connection을
    # 가져올 수 없으므로 에러가 발생합니다.
    # 테스트를 위해서는 Airflow 환경 내에서 실행해야 합니다.
    print("This module is designed to be used within an Airflow environment.")
    print("To test, ensure you have a connection named 'postgres_default' configured in Airflow.")