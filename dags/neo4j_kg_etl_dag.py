"""
Neo4j Knowledge Graph ETL DAG

UPDATED - 2025-01-06:
- KG는 **날짜 단위(Date 허브)**로 구성
- **Event = 공시 카테고리/유형(major-report endpoint)** (뉴스/LLM 이벤트 추출/감성은 POSTPONED)
- 일일 배치로 PostgreSQL에서 데이터를 읽어 Neo4j에 적재
  - `daily_stock_price` (주가)
  - `dart_*` major-report tables (공시 카테고리 이벤트)
"""

from __future__ import annotations

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule

from modules.neo4j.neo4j_operators import (
    create_base_kg_data,
    load_competitor_relationships_from_mongodb,
    load_daily_dart_disclosure_events,
    load_reports_from_mongodb,
    load_daily_stock_prices,
    resolve_daily_target_date,
)

# Airflow Connection IDs
NEO4J_CONN_ID = "neo4j_default"
POSTGRES_CONN_ID = "postgres_default"


with DAG(
    dag_id="neo4j_kg_etl_dag",
    start_date=pendulum.datetime(2026, 1, 6, tz="Asia/Seoul"),
    catchup=False,
    # After 20:00 KST (price collection 완료 이후 KG 적재)
    schedule="10 20 * * *",
    tags=["neo4j", "kg", "etl", "daily"],
) as dag:
    t_setup = PythonOperator(
        task_id="create_base_kg_data",
        python_callable=create_base_kg_data,
        op_kwargs={"neo4j_conn_id": NEO4J_CONN_ID},
    )

    t_resolve_date = PythonOperator(
        task_id="resolve_target_date",
        python_callable=resolve_daily_target_date,
        op_kwargs={"postgres_conn_id": POSTGRES_CONN_ID},
    )

    t_load_prices = PythonOperator(
        task_id="load_daily_stock_prices",
        python_callable=load_daily_stock_prices,
        op_kwargs={
            "neo4j_conn_id": NEO4J_CONN_ID,
            "postgres_conn_id": POSTGRES_CONN_ID,
            "target_date": "{{ ti.xcom_pull(task_ids='resolve_target_date') }}",
        },
    )

    t_load_dart_events = PythonOperator(
        task_id="load_daily_dart_disclosure_events",
        python_callable=load_daily_dart_disclosure_events,
        # Align with rebuild behavior:
        # - If the day has no stock prices (holiday/weekend), stock price task may SKIP,
        #   but DART disclosures for that day should still be loaded.
        # - If stock price task FAILS, we don't proceed (consistent with rebuild loop behavior).
        trigger_rule=TriggerRule.NONE_FAILED,
        op_kwargs={
            "neo4j_conn_id": NEO4J_CONN_ID,
            "postgres_conn_id": POSTGRES_CONN_ID,
            "target_date": "{{ ti.xcom_pull(task_ids='resolve_target_date') }}",
        },
    )

    t_load_reports = PythonOperator(
        task_id="load_daily_reports_from_mongodb",
        python_callable=load_reports_from_mongodb,
        trigger_rule=TriggerRule.NONE_FAILED,
        op_kwargs={
            "neo4j_conn_id": NEO4J_CONN_ID,
            "start_date": "{{ ti.xcom_pull(task_ids='resolve_target_date') }}",
            "end_date": "{{ ti.xcom_pull(task_ids='resolve_target_date') }}",
        },
    )

    t_load_competitors = PythonOperator(
        task_id="load_competitor_relationships_from_mongodb",
        python_callable=load_competitor_relationships_from_mongodb,
        trigger_rule=TriggerRule.NONE_FAILED,
        op_kwargs={"neo4j_conn_id": NEO4J_CONN_ID},
    )

    t_setup >> t_resolve_date >> t_load_prices >> t_load_dart_events >> t_load_reports >> t_load_competitors
