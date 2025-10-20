"""
Competitor Company Crawler Module

This module crawls competitor information for all listed companies from Wisereport.
It collects target company information along with their competitors and stores the data in MongoDB.

Author: Stockelper Team
License: MIT
"""

import os
import sys
import requests
import FinanceDataReader as fdr
from time import sleep
from datetime import datetime
import json
from tqdm import tqdm

# Add module path for imports
sys.path.insert(0, '/opt/airflow')

# Import common logging and database connection
from modules.common.logging_config import setup_logger
from modules.common.db_connections import get_db_connection

# Setup logger
logger = setup_logger(__name__)

class CompetitorCrawler:
    """
    A class to crawl competitor information for listed companies.
    """
    COLLECTION_NAME = "competitors"

    def __init__(self, test_mode=False):
        """
        Initialize the CompetitorCrawler.

        Args:
            test_mode (bool): If True, run in test mode without DB connection.
        """
        self.test_mode = test_mode
        self.collection = None
        if not self.test_mode:
            self._init_db()

    def _init_db(self):
        """Initialize the MongoDB connection."""
        try:
            db = get_db_connection()
            self.collection = db[self.COLLECTION_NAME]
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def get_all_stock_codes(self):
        """
        Get all listed company stock codes using FinanceDataReader.
        
        Returns:
            list: List of stock codes from KOSPI, KOSDAQ, and KONEX
        """
        logger.info("Loading KOSPI, KOSDAQ, KONEX stock codes...")
        try:
            kospi = fdr.StockListing("KOSPI")
            kosdaq = fdr.StockListing("KOSDAQ")
            konex = fdr.StockListing("KONEX")
            all_stocks = [kospi, kosdaq, konex]
            
            codes = [code for df in all_stocks for code in df['Code'].dropna().astype(str).tolist()]
            logger.info(f"Found {len(codes)} stock codes in total.")
            return codes
        except Exception as e:
            logger.error(f"Failed to load stock codes: {e}")
            return []

    def fetch_html(self, url, retries=3, delay=1):
        """
        Fetch HTML content from the given URL with retry mechanism.
        
        Args:
            url (str): URL to fetch
            retries (int): Number of retry attempts
            delay (int): Delay between retries in seconds
            
        Returns:
            bytes: HTML content or None if failed
        """
        for i in range(retries):
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()  # Raise exception if not 200 OK
                return response.content
            except requests.exceptions.RequestException as e:
                logger.warning(f"URL fetch error: {url} (attempt {i+1}/{retries}): {e}")
                sleep(delay)
        return None

    def parse_company_data(self, html_content):
        """
        Parse HTML content (JSON) to extract target company and competitor information.
        
        Args:
            html_content (bytes): HTML content containing JSON data
            
        Returns:
            tuple: (target_company, competitors) where target_company is dict and competitors is list
        """
        try:
            data = json.loads(html_content)
            if not data.get("oDt_header"):
                return None, []

            target_company = None
            competitors = []
            
            for company in data["oDt_header"]:
                company_info = {
                    "code": company.get("CMP_CD"),
                    "name": company.get("CMP_KOR"),
                    "market_value": company.get("MKT_VAL")
                }
                
                if company.get("SEQ") == 1:
                    target_company = company_info
                else:
                    competitors.append(company_info)
                    
            return target_company, competitors
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"JSON parsing error: {e}")
            return None, []

    def run(self):
        """
        Main execution function: collect stock codes, crawl data, and save to DB or output JSON.
        """
        codes = self.get_all_stock_codes()
        if not codes:
            logger.error("No stock codes found. Exiting.")
            return
            
        if self.test_mode:
            codes = codes[:5]
            logger.info(f"[TEST MODE] Processing only {len(codes)} stocks.")

        all_results = []
        logger.info("Starting competitor information crawling...")
        
        for code in tqdm(codes, desc="Crawling Competitors"):
            url = f"https://comp.wisereport.co.kr/company/ajax/cF6001.aspx?cmp_cd={code}&finGubun=MAIN&sec_cd=FG000&frq=Y"
            html_content = self.fetch_html(url)

            if not html_content:
                logger.warning(f"[{code}] Data fetch failed. Skipping.")
                continue

            target_company, competitors = self.parse_company_data(html_content)

            if not target_company or not target_company.get("code"):
                logger.warning(f"[{code}] Parsing failed. No valid data found.")
                continue

            document = {
                "_id": target_company["code"],
                "target_company": target_company,
                "competitors": competitors,
                "last_crawled_at": datetime.utcnow().isoformat()
            }

            if self.test_mode:
                all_results.append(document)
            else:
                try:
                    self.collection.update_one(
                        {"_id": document["_id"]},
                        {"$set": document},
                        upsert=True
                    )
                    logger.debug(f"[{code}] Successfully saved to database.")
                except Exception as e:
                    logger.error(f"[{code}] Database save failed: {e}")
            
            sleep(0.1)

        if self.test_mode:
            logger.info("--- Crawling Results (JSON Output) ---")
            print(json.dumps(all_results, indent=2, ensure_ascii=False))
            logger.info("[TEST MODE] JSON output completed.")
        else:
            logger.info("Competitor information crawling and database saving completed for all companies.")