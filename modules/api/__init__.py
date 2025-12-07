"""
API module for data validation and external API clients

This module provides functions for validating data using DART and KIS APIs.
"""

from .data_validator import run_validate

__all__ = ["run_validate"]

