"""
Airflow Log Cleanup DAG

This DAG automatically cleans up old Airflow logs to prevent disk space issues.
It runs daily and removes logs older than the specified retention period.

Author: Stockelper Team
License: MIT
"""

import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator

from modules.common.logging_config import setup_logger

# Setup logger
logger = setup_logger(__name__)

# Configuration
LOG_BASE_FOLDER = "/opt/airflow/logs"
LOG_RETENTION_DAYS = 7  # Keep logs for 7 days
DRY_RUN = False  # Set to True to see what would be deleted without actually deleting

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': pendulum.duration(minutes=5),
}

def cleanup_old_logs(**context):
    """
    Clean up old Airflow logs based on retention policy.
    
    Args:
        **context: Airflow context dictionary
    """
    log_folder = Path(LOG_BASE_FOLDER)
    cutoff_date = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
    
    deleted_files = 0
    deleted_size = 0
    errors = []
    
    logger.info(f"Starting log cleanup. Retention period: {LOG_RETENTION_DAYS} days")
    logger.info(f"Cutoff date: {cutoff_date}")
    logger.info(f"Dry run mode: {DRY_RUN}")
    
    try:
        # Walk through all subdirectories in the log folder
        for root, dirs, files in os.walk(log_folder):
            for file in files:
                file_path = Path(root) / file
                
                try:
                    # Get file modification time
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    
                    # Check if file is older than cutoff date
                    if file_mtime < cutoff_date:
                        file_size = file_path.stat().st_size
                        
                        if DRY_RUN:
                            logger.info(f"[DRY RUN] Would delete: {file_path} (size: {file_size} bytes)")
                        else:
                            file_path.unlink()
                            logger.debug(f"Deleted: {file_path} (size: {file_size} bytes)")
                        
                        deleted_files += 1
                        deleted_size += file_size
                        
                except Exception as e:
                    error_msg = f"Error processing file {file_path}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
        
        # Clean up empty directories
        if not DRY_RUN:
            for root, dirs, files in os.walk(log_folder, topdown=False):
                for dir_name in dirs:
                    dir_path = Path(root) / dir_name
                    try:
                        if not any(dir_path.iterdir()):
                            dir_path.rmdir()
                            logger.debug(f"Removed empty directory: {dir_path}")
                    except Exception as e:
                        logger.warning(f"Could not remove directory {dir_path}: {e}")
        
        # Log summary
        deleted_size_mb = deleted_size / (1024 * 1024)
        logger.info(f"Log cleanup completed!")
        logger.info(f"Files deleted: {deleted_files}")
        logger.info(f"Space freed: {deleted_size_mb:.2f} MB")
        
        if errors:
            logger.warning(f"Encountered {len(errors)} errors during cleanup")
        
        # Push metrics to XCom for monitoring
        context['ti'].xcom_push(key='deleted_files', value=deleted_files)
        context['ti'].xcom_push(key='deleted_size_mb', value=deleted_size_mb)
        context['ti'].xcom_push(key='error_count', value=len(errors))
        
        return {
            "deleted_files": deleted_files,
            "deleted_size_mb": deleted_size_mb,
            "errors": len(errors)
        }
        
    except Exception as e:
        logger.error(f"Fatal error during log cleanup: {e}")
        raise

def get_log_statistics(**context):
    """
    Get current log folder statistics.
    
    Args:
        **context: Airflow context dictionary
    """
    log_folder = Path(LOG_BASE_FOLDER)
    
    total_files = 0
    total_size = 0
    
    try:
        for root, dirs, files in os.walk(log_folder):
            for file in files:
                file_path = Path(root) / file
                try:
                    total_files += 1
                    total_size += file_path.stat().st_size
                except Exception as e:
                    logger.warning(f"Could not stat file {file_path}: {e}")
        
        total_size_mb = total_size / (1024 * 1024)
        total_size_gb = total_size / (1024 * 1024 * 1024)
        
        logger.info(f"Current log statistics:")
        logger.info(f"Total files: {total_files}")
        logger.info(f"Total size: {total_size_gb:.2f} GB ({total_size_mb:.2f} MB)")
        
        # Push to XCom
        context['ti'].xcom_push(key='total_files', value=total_files)
        context['ti'].xcom_push(key='total_size_mb', value=total_size_mb)
        
        return {
            "total_files": total_files,
            "total_size_mb": total_size_mb,
            "total_size_gb": total_size_gb
        }
        
    except Exception as e:
        logger.error(f"Error getting log statistics: {e}")
        raise

with DAG(
    dag_id='log_cleanup',
    default_args=default_args,
    description='Clean up old Airflow logs to manage disk space',
    schedule='0 2 * * *',  # Run daily at 2 AM UTC
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    catchup=False,
    doc_md="""
    ### Log Cleanup DAG

    This DAG automatically cleans up old Airflow logs to prevent disk space issues.
    It runs daily and removes logs older than the specified retention period.
    """,
    tags=['maintenance', 'logs'],
) as dag:
    
    # Task 1: Get current log statistics
    get_stats_task = PythonOperator(
        task_id='get_log_statistics',
        python_callable=get_log_statistics,
    )
    
    # Task 2: Clean up old logs
    cleanup_task = PythonOperator(
        task_id='cleanup_old_logs',
        python_callable=cleanup_old_logs,
    )
    
    # Task 3: Get statistics after cleanup
    get_stats_after_task = PythonOperator(
        task_id='get_log_statistics_after_cleanup',
        python_callable=get_log_statistics,
    )
    
    # Define task dependencies
    get_stats_task >> cleanup_task >> get_stats_after_task
