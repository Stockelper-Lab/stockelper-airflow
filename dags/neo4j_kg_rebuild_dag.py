"""
Neo4j Knowledge Graph REBUILD DAG (MANUAL)

목적:
- PostgreSQL에 이미 적재된 데이터(주가/공시)로부터 Neo4j KG를 **처음부터 재구축**합니다.

주의:
- 기본값은 Neo4j 전체 데이터를 `DETACH DELETE`로 삭제(wipe)한 뒤 재구축합니다.
- 대용량 기간(예: 2005~현재)을 지정하면 시간이 오래 걸릴 수 있습니다.

Airflow Variables (선택):
- KG_REBUILD_START_DATE: "YYYY-MM-DD" (미설정 시 DB에서 MIN(date) 자동 계산)
- KG_REBUILD_END_DATE: "YYYY-MM-DD" (미설정 시 DB에서 MAX(date) 자동 계산)
- KG_REBUILD_WIPE: "true"/"false" (기본 true)
- NEO4J_CONN_ID: (선택) 기본 "neo4j_default"
"""

from __future__ import annotations

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

from modules.common.airflow_settings import get_setting
from modules.neo4j.neo4j_operators import rebuild_kg_from_postgres_all


def _rebuild(**_context):
    neo4j_conn_id = get_setting("NEO4J_CONN_ID", "neo4j_default") or "neo4j_default"
    postgres_conn_id = get_setting("POSTGRES_CONN_ID", "postgres_default") or "postgres_default"

    start_date = get_setting("KG_REBUILD_START_DATE")
    end_date = get_setting("KG_REBUILD_END_DATE")
    wipe_raw = str(get_setting("KG_REBUILD_WIPE", "true") or "true").strip().lower()
    wipe = wipe_raw not in ("0", "false", "no", "n")

    # If start/end are missing, the operator will derive the range from DB contents.
    return rebuild_kg_from_postgres_all(
        neo4j_conn_id=neo4j_conn_id,
        postgres_conn_id=postgres_conn_id,
        start_date=str(start_date) if start_date else None,
        end_date=str(end_date) if end_date else None,
        wipe=wipe,
    )


with DAG(
    dag_id="neo4j_kg_rebuild_dag",
    start_date=pendulum.datetime(2026, 1, 6, tz="Asia/Seoul"),
    schedule=None,
    catchup=False,
    tags=["neo4j", "kg", "rebuild", "manual"],
) as dag:
    PythonOperator(
        task_id="rebuild_kg_from_postgres",
        python_callable=_rebuild,
        execution_timeout=pendulum.duration(hours=24),
    )


