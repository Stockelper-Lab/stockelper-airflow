#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Stock Report Crawler DAG
========================

This DAG crawls stock reports daily and stores them in MongoDB.

Execution Steps:
1. Check MongoDB connection
2. Execute report crawling
3. Report results

Schedule: Daily at 00:00 UTC (09:00 KST)
"""

from datetime import datetime, timedelta
import os
import sys
import logging
import pendulum
import time

# UTC-based time usage
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[handler])
from pymongo import MongoClient

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

# Add module paths
sys.path.insert(0, '/opt/airflow')
sys.path.append('/opt/airflow/modules')
sys.path.append('/opt/airflow/config')

# Import configuration modules
from config.mongo_config import MONGO_HOST, MONGO_PORT, MONGO_DATABASE

# Import report crawler module
from modules.report_crawler.crawler import StockReportCrawler

# MongoDB connection information
MONGODB_URI = f"mongodb://{MONGO_HOST}:{MONGO_PORT}/"

# Default arguments
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# DAG definition (must be declared globally)
dag = DAG(
    dag_id='stock_report_crawler',
    default_args=default_args,
    description='Stock Report Crawling Pipeline',
    schedule_interval='0 0 * * *',  # Daily at UTC 0:00 (09:00 KST)
    start_date=days_ago(0),  # Start from today to ensure scheduling
    catchup=True,  # Execute missed tasks on restart
    tags=['report_crawler', 'mongodb', 'selenium'],
)

# Task functions
def check_mongodb_connection(**kwargs):
    """Check MongoDB connection"""
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        logging.info("MongoDB connection successful")
        return True
    except Exception as e:
        logging.error(f"MongoDB connection failed: {e}")
        raise

def crawl_stock_report(**kwargs):
    """Execute report crawling"""
    try:
        # Crawl based on the actual date when DAG is executed
        date_to_crawl = pendulum.now('Asia/Seoul').format('YYYY/MM/DD')

        logging.info(f"Starting report crawling (target date: {date_to_crawl})")
        crawler = StockReportCrawler(mongodb_uri=MONGODB_URI)
        # Set start_date and end_date to the same value to crawl only one day
        result = crawler.crawl_daily_report(daily=False, start_date=date_to_crawl, end_date=date_to_crawl)
        logging.info("Report crawling completed")
        ti = kwargs.get('ti')
        if ti:
            ti.xcom_push(key='crawl_result', value={'status': 'success', 'result': result})
        return True
    except Exception as e:
        logging.error(f"Report crawling failed: {e}")
        ti = kwargs.get('ti')
        if ti:
            ti.xcom_push(key='crawl_result', value={'status': 'error', 'error': str(e)})
        raise

def report_results(**kwargs):
    """Report crawling results"""
    try:
        logging.info("Starting report crawling results reporting")
        ti = kwargs.get('ti')
        if ti:
            crawl_result = ti.xcom_pull(task_ids='crawl_stock_report', key='crawl_result')
            if crawl_result and crawl_result.get('status') == 'success':
                logging.info(f"Report crawling completed successfully. Result: {crawl_result.get('result')}")
            elif crawl_result and crawl_result.get('status') == 'error':
                logging.error(f"Error occurred during report crawling: {crawl_result.get('error')}")
            else:
                logging.info("Cannot verify report crawling results.")
        else:
            # Check results directly from MongoDB
            client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            db = client[MONGO_DATABASE]
            count = db["report"].count_documents({})
            today_count = db["report"].count_documents({
                "date": {"$regex": pendulum.now().strftime("%Y/%m/%d")}
            })
            logging.info(f"Reports stored in MongoDB: Total {count}, Today {today_count}")
        logging.info("Report crawling results reporting completed")
        return True
    except Exception as e:
        logging.error(f"Error occurred during results reporting: {e}")
        return True

# Task definitions
check_mongodb = PythonOperator(
    task_id='check_mongodb_connection',
    python_callable=check_mongodb_connection,
    dag=dag,
)

crawl_report = PythonOperator(
    task_id='crawl_stock_report',
    python_callable=crawl_stock_report,
    dag=dag,
)

report = PythonOperator(
    task_id='report_results',
    python_callable=report_results,
    dag=dag,
)

# Task dependency setup
check_mongodb >> crawl_report >> report

if __name__ == "__main__":
    dag.cli()
