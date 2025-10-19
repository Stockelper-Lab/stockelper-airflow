"""
Stock Report Crawler Module

This module crawls stock research reports from financial websites using Selenium WebDriver.
It processes the data and stores it in MongoDB with duplicate prevention.

Author: Stockelper Team
License: MIT
"""

import os
import sys
import pandas as pd
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from pymongo import MongoClient
import time

# Add module path for imports
sys.path.insert(0, '/opt/airflow')

# Import common logging configuration
from modules.common.logging_config import setup_logger

# Setup logger
logger = setup_logger(__name__)

MONGODB_URI = os.environ.get("MONGODB_URI")

class StockReportCrawler:
    """
    Stock Report Crawler class for scraping financial research reports.
    """
    
    def __init__(self, mongodb_uri=None, mongo_database=None, headless=True):
        """
        Initialize the Stock Report Crawler.
        
        Args:
            mongodb_uri (str): MongoDB connection URI
            mongo_database (str): MongoDB database name
            headless (bool): Whether to run Chrome in headless mode
        """
        self.mongodb_uri = mongodb_uri or MONGODB_URI
        self.mongo_database = mongo_database or os.environ.get("MONGO_DATABASE", "stockelper")
        self.headless = headless
        self.driver = None
        self.collection = None
        
        # Initialize MongoDB connection
        self._init_mongodb()
        
    def _init_mongodb(self):
        """Initialize MongoDB connection and collection."""
        try:
            client = MongoClient(self.mongodb_uri, serverSelectionTimeoutMS=5000)
            client.server_info()  # Test connection
            self.db = client[self.mongo_database]
            self.collection = self.db["report"]
            
            # Create indexes for duplicate prevention
            self.collection.create_index([
                ('date', 1), 
                ('company', 1), 
                ('code', 1)
            ], unique=True)
            
            logger.info("Successfully connected to MongoDB and created indexes.")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            self.collection = None
    
    def setup_driver(self):
        """Setup Chrome WebDriver with appropriate options."""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless=new")
        
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("Chrome WebDriver initialized successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Chrome WebDriver: {e}")
            return False
    
    def crawl_daily_report(self, daily=True, start_date=None, end_date=None):
        """
        Crawl stock reports for the specified date range.
        
        Args:
            daily (bool): If True, crawl today's reports only
            start_date (str): Start date in YYYY-MM-DD format
            end_date (str): End date in YYYY-MM-DD format
            
        Returns:
            dict: Crawling results with statistics
        """
        if not self.setup_driver():
            return {"success": False, "error": "Failed to setup WebDriver"}
        
        if self.collection is None:
            return {"success": False, "error": "MongoDB connection not available"}
        
        try:
            # Determine date range
            if daily:
                target_date = datetime.now().strftime("%Y-%m-%d")
                date_range = [target_date]
            else:
                # Parse date range if provided
                if start_date and end_date:
                    # Support both YYYY-MM-DD and YYYY/MM/DD formats
                    try:
                        start = datetime.strptime(start_date, "%Y-%m-%d")
                        end = datetime.strptime(end_date, "%Y-%m-%d")
                    except ValueError:
                        start = datetime.strptime(start_date, "%Y/%m/%d")
                        end = datetime.strptime(end_date, "%Y/%m/%d")
                    date_range = [(start + timedelta(days=x)).strftime("%Y-%m-%d") 
                                 for x in range((end - start).days + 1)]
                else:
                    # Default to last 7 days
                    date_range = [(datetime.now() - timedelta(days=x)).strftime("%Y-%m-%d") 
                                 for x in range(7)]
            
            total_reports = 0
            successful_saves = 0
            errors = []
            
            for date_str in date_range:
                logger.info(f"Crawling reports for date: {date_str}")
                
                try:
                    reports = self._crawl_reports_for_date(date_str)
                    total_reports += len(reports)
                    
                    # Save reports to MongoDB
                    for report in reports:
                        try:
                            self.collection.update_one(
                                {
                                    'date': report['date'],
                                    'company': report['company'],
                                    'code': report['code']
                                },
                                {'$set': report},
                                upsert=True
                            )
                            successful_saves += 1
                            logger.debug(f"Saved report: {report['company']} - {report.get('summary', 'N/A')}")
                        except Exception as e:
                            error_msg = f"Failed to save report for {report.get('company', 'Unknown')}: {e}"
                            logger.error(error_msg)
                            errors.append(error_msg)
                
                except Exception as e:
                    error_msg = f"Failed to crawl reports for {date_str}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                
                # Add delay between dates to be respectful to the server
                time.sleep(1)
            
            return {
                "success": True,
                "total_reports": total_reports,
                "successful_saves": successful_saves,
                "errors": errors,
                "date_range": date_range
            }
            
        except Exception as e:
            logger.error(f"Unexpected error during crawling: {e}")
            return {"success": False, "error": str(e)}
        
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("WebDriver closed.")
    
    def _crawl_reports_for_date(self, date_str):
        """
        Crawl reports for a specific date.
        
        Args:
            date_str (str): Date in YYYY-MM-DD format
            
        Returns:
            list: List of report dictionaries
        """
        reports = []
        
        try:
            # Convert YYYY-MM-DD to YYYY/MM/DD for the website
            date_formatted = date_str.replace('-', '/')
            
            # Navigate to fnguide report page
            url = "https://comp.fnguide.com/SVO2/ASP/SVD_Report_Summary.asp"
            self.driver.get(url)
            time.sleep(3)
            
            # Set date range
            start_date_key = self.driver.find_element(By.CSS_SELECTOR, '#inFromDate')
            end_date_key = self.driver.find_element(By.CSS_SELECTOR, '#inToDate')
            
            # Clear and set dates
            for _ in range(10):
                start_date_key.send_keys(Keys.BACK_SPACE)
            start_date_key.send_keys(date_formatted)
            
            for _ in range(10):
                end_date_key.send_keys(Keys.BACK_SPACE)
            end_date_key.send_keys(date_formatted)
            
            # Click search
            search_button = self.driver.find_element(By.CSS_SELECTOR, '#btnSearch')
            search_button.click()
            time.sleep(5)
            
            # Extract table data
            table = self.driver.find_element(By.XPATH, '//*[@id="ReportGrid"]/table')
            headers = [header.text for header in table.find_elements(By.XPATH, './/thead//th')]
            
            rows = []
            for row in table.find_elements(By.XPATH, './/tbody//tr'):
                rows.append([cell.text for cell in row.find_elements(By.XPATH, './/td')])
            
            # Create DataFrame
            df = pd.DataFrame(rows, columns=headers)
            
            # Process DataFrame
            df['company'] = df['종목명 - 리포트 요약'].apply(lambda x: x.split(' ')[0])
            df['code'] = df['종목명 - 리포트 요약'].apply(lambda x: x.split(' ')[1])
            df['summary'] = df['종목명 - 리포트 요약'].apply(lambda x: ' '.join(x.split(' ')[2:]).strip('-'))
            
            # Convert date format
            def convert_date_format(date_str):
                if not date_str or not isinstance(date_str, str):
                    return date_str
                parts = date_str.split('/')
                if len(parts) == 3 and len(parts[0]) == 2:
                    year = '20' + parts[0]
                    return f"{year}-{parts[1]}-{parts[2]}"
                return date_str
            
            df['일자'] = df['일자'].apply(convert_date_format)
            
            df = df[['일자', 'company', 'code', 'summary', '투자의견', '제공처/작성자', '목표주가']]
            df.columns = ['date', 'company', 'code', 'summary', 'opinion', 'provider', 'goal_price']
            
            # Convert to list of dicts
            reports = df.to_dict(orient='records')
            logger.info(f"Found {len(reports)} reports for {date_str}")
            
        except Exception as e:
            logger.error(f"Error crawling reports for {date_str}: {e}")
        
        return reports
    
    
    def get_crawl_statistics(self, date_str=None):
        """
        Get crawling statistics from MongoDB.
        
        Args:
            date_str (str): Optional date to filter statistics
            
        Returns:
            dict: Statistics dictionary
        """
        if self.collection is None:
            return {"error": "MongoDB connection not available"}
        
        try:
            query = {}
            if date_str:
                query["date"] = date_str
            
            total_reports = self.collection.count_documents(query)
            
            # Get unique companies
            companies = self.collection.distinct("company", query)
            
            # Get latest crawl time
            latest_doc = self.collection.find_one(
                query, 
                sort=[("crawled_at", -1)]
            )
            latest_crawl = latest_doc["crawled_at"] if latest_doc else None
            
            return {
                "total_reports": total_reports,
                "unique_companies": len(companies),
                "latest_crawl": latest_crawl,
                "companies": companies[:10]  # First 10 companies
            }
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {"error": str(e)}

def main():
    """Main function for testing the crawler."""
    crawler = StockReportCrawler()
    
    # Test crawling
    result = crawler.crawl_daily_report(daily=True)
    print(f"Crawling result: {result}")
    
    # Get statistics
    stats = crawler.get_crawl_statistics()
    print(f"Statistics: {stats}")

if __name__ == "__main__":
    main()
