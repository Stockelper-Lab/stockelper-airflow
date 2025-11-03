# dags/neo4j_kg_etl_dag.py
"""
DAG to build and update the Neo4j Knowledge Graph.
"""

from __future__ import annotations

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

# Assuming the `dags` directory is in PYTHONPATH, we can import from operators
from modules.neo4j.neo4j_operators import *

# --- Constants --- #
# The connection ID for the Neo4j connection configured in the Airflow UI.
NEO4J_CONN_ID = "neo4j_default"
INPUT_JSON_PATH = "/Users/chan/Documents/workspace/stockelper/neo4j-test/input.json"


with DAG(
    dag_id="neo4j_kg_etl_dag",
    start_date=pendulum.datetime(2025, 10, 31, tz="Asia/Seoul"),
    catchup=False,
    schedule="@daily",
    tags=["neo4j", "kg", "etl"],
    doc_md="""
    ### Neo4j Knowledge Graph ETL DAG

    This DAG orchestrates the process of building and updating a financial knowledge graph in Neo4j.
    It follows an Extract-Load pattern, where data extraction is separated from loading.

    1.  **create_base_kg_data**: (Idempotent) Populates the database with foundational data.
    2.  **extract_daily_data**: Extracts data from a source (e.g., a file, an API) and passes it to the next task.
    3.  **load_daily_data**: Loads the extracted data into Neo4j.
    """,
) as dag:
    # Task 1: (Idempotent) Create foundational data in Neo4j
    create_base_data_task = PythonOperator(
        task_id="create_base_kg_data",
        python_callable=create_base_kg_data,
        op_kwargs={
            "neo4j_conn_id": NEO4J_CONN_ID,
        },
    )

    # Task 2: Extract data from a source (currently a local file)
    extract_daily_data_task = PythonOperator(
        task_id="extract_daily_data",
        python_callable=extract_data_from_request,
        op_kwargs={
            "url": "https://raw.githubusercontent.com/ssilb4/test-file-storage/refs/heads/main/input.json",
        },
        trigger_rule="all_done",
    )
    # Task 3: Load the extracted data into Neo4j
    load_daily_data_task = PythonOperator(
        task_id="load_daily_data",
        python_callable=load_daily_data,
        op_kwargs={
            "neo4j_conn_id": NEO4J_CONN_ID,
        },
    )

    # Define task dependency chain
    create_base_data_task >> extract_daily_data_task >> load_daily_data_task
