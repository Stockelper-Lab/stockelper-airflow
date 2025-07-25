"""
Report Crawler Module

This module provides functionality for crawling stock research reports
from financial websites and storing them in MongoDB.
"""

from .crawler import StockReportCrawler

__all__ = ['StockReportCrawler']
