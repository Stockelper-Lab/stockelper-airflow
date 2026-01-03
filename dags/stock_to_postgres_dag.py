from __future__ import annotations

from datetime import datetime

from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

# 분리된 모듈과 오퍼레이터 임포트
from modules.stock_price.fetch_stock_operators import FetchStockBatchOperator
from modules.stock_price.stock_to_db import (
    get_symbols_to_update,
    load_data_to_postgres,
    setup_database_table,
)


with DAG(
    dag_id="stock_price_to_db",
    start_date=datetime(2023, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    doc_md="""
    ### KRX 주식 가격 ETL DAG (Refactored)

    - KRX 상장된 모든 종목의 일별 시세를 가져와 PostgreSQL 데이터베이스에 저장합니다.
    - **DB 연결 정보**: Airflow UI의 'Admin -> Connections'에서 PostgreSQL Connection을 설정해야 합니다.
      - **Conn ID**: `postgres_default` (기본값)
      - **Conn Type**: `Postgres`
      - **Host**: PostgreSQL 서버 호스트
      - **Schema**: 데이터베이스 이름 (e.g., `postgres`)
      - **Login**: 사용자 이름
      - **Password**: 비밀번호
      - **Port**: 포트 번호
    - 이 DAG는 로직을 커스텀 오퍼레이터와 모듈로 분리하여 DAG 파일의 가독성을 높였습니다.
    """,
    tags=["stock", "postgres", "etl"],
    default_args={"owner": "airflow"},
) as dag:
    # Task 1: DB 테이블 설정
    setup_task = PythonOperator(
        task_id="setup_database_table",
        python_callable=setup_database_table,
    )

    # Task 2: (신규 종목 + 기존 종목 최신) 업데이트 대상 리스트 가져오기
    get_symbols_task = PythonOperator(
        task_id="get_symbols_to_update",
        python_callable=get_symbols_to_update,
        do_xcom_push=True,
    )

    # Task 3: 배치 단위로 데이터 가져오기 (동적 생성)
    # get_symbols_task는 [{"batch": [{"symbol": "...", "data_start_date": "...", "data_end_date": "..."}, ...]}, ...] 형태를 반환하고,
    # expand_kwargs로 각 batch를 오퍼레이터 인자로 매핑합니다. (Airflow core.max_map_length 기본 1024 제한 회피)
    fetch_data_task = FetchStockBatchOperator.partial(
        task_id="fetch_and_process_stock_data"
    ).expand_kwargs(get_symbols_task.output)

    # Task 4: 처리된 모든 데이터를 DB에 로드
    load_data_task = PythonOperator(
        task_id="load_data_to_postgres",
        python_callable=load_data_to_postgres,
        provide_context=True,
    )

    # 의존성 설정
    setup_task >> get_symbols_task >> fetch_data_task >> load_data_task
