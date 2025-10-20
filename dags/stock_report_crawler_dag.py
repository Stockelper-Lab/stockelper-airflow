"""
Stock Report Crawler DAG
========================

This DAG crawls stock reports daily and stores them in MongoDB.

Execution Steps:
1. Execute report crawling
2. Report results

Schedule: Daily at 00:00 UTC (09:00 KST)
"""

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

# Import report crawler module
from modules.report_crawler.stock_report_crawler import StockReportCrawler
from modules.common.logging_config import setup_logger

# Setup logger
logger = setup_logger(__name__)

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': pendulum.duration(minutes=5),
}

def crawl_stock_report(**kwargs):
    """Execute report crawling"""
    date_to_crawl = pendulum.now("Asia/Seoul").format("YYYY/MM/DD")
    logger.info(f"Starting report crawling (target date: {date_to_crawl})")

    crawler = StockReportCrawler()
    result = crawler.crawl_daily_report(
        daily=False, start_date=date_to_crawl, end_date=date_to_crawl
    )

    if not result["success"]:
        raise Exception(f"Crawling failed: {result['error']}")

    kwargs['ti'].xcom_push(key="crawl_result", value=result)

def report_results(**kwargs):
    """Report crawling results"""
    crawl_result = kwargs['ti'].xcom_pull(
        task_ids="crawl_stock_report", key="crawl_result"
    )
    if crawl_result:
        logger.info(f"Crawling completed successfully: {crawl_result}")
    else:
        logger.warning("Could not retrieve crawling result from XCom.")

with DAG(
    dag_id="stock_report_crawler",
    default_args=default_args,
    description="Stock Report Crawling Pipeline",
    schedule="0 0 * * *",  # Daily at UTC 0:00 (09:00 KST)
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    catchup=False,
    tags=["report_crawler", "mongodb", "selenium"],
) as dag:
    crawl_report = PythonOperator(
        task_id="crawl_stock_report",
        python_callable=crawl_stock_report,
    )

    report = PythonOperator(
        task_id="report_results",
        python_callable=report_results,
    )

    crawl_report >> report
