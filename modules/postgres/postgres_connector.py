import os
from sqlalchemy import create_engine
from airflow.hooks.base import BaseHook
import logging

log = logging.getLogger(__name__)

def get_postgres_engine(conn_id="postgres_default"):
    """
    Airflow Connection에서 PostgreSQL 접속 정보를 가져와 SQLAlchemy 엔진을 생성합니다.

    :param conn_id: Airflow에 설정된 Connection ID
    :return: SQLAlchemy Engine
    """
    try:
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

        engine = create_engine(f'postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}')
        log.info(f"Successfully created SQLAlchemy engine for Airflow connection '{conn_id}'.")
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