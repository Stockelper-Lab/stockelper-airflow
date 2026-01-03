from __future__ import annotations

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

from modules.company_crawler.compete_company_crawler import CompetitorCrawler

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': pendulum.duration(minutes=5),
}

def run_crawler():
    """Instantiate and run the CompetitorCrawler."""
    crawler = CompetitorCrawler()
    crawler.run()

with DAG(
    dag_id="competitor_crawler",
    default_args=default_args,
    schedule="0 0 * * *",  # Daily at midnight (UTC)
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    catchup=False,
    doc_md="""
    ### Competitor Crawler DAG

    - Crawls competitor information for all listed companies from Wisereport
    - Runs daily at midnight to keep MongoDB data up-to-date
    """,
    tags=["crawler", "mongodb", "competitor"],
) as dag:
    crawl_task = PythonOperator(
        task_id="crawl_competitor_companies",
        python_callable=run_crawler,
    )
