from __future__ import annotations

import pendulum

from airflow.models.dag import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="competitor_crawler",
    schedule="0 0 * * *",  # Daily at midnight (UTC)
    start_date=pendulum.now('UTC').subtract(days=1),
    catchup=False,
    doc_md="""
    ### Competitor Crawler DAG

    - Crawls competitor information for all listed companies from Wisereport
    - Runs daily at midnight to keep MongoDB data up-to-date
    """,
    tags=["crawler", "mongodb", "competitor"],
) as dag:
    crawl_task = BashOperator(
        task_id="crawl_competitor_companies",
        bash_command="python /opt/airflow/modules/company_crawler/compete_company_crawler.py",
        env={
            "MONGODB_URI": "mongodb://<MONGODB_HOST>:<MONGODB_PORT>/",
            "PYTHONPATH": "/opt/airflow"
        },
    )
