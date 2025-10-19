"""
Common Logging Configuration Module

This module provides a centralized logging configuration for all Stockelper Airflow modules.
It ensures consistent logging format and behavior across all DAGs and modules.

Author: Stockelper Team
License: MIT
"""

import logging
import sys
from typing import Optional


def setup_logger(
    name: str,
    level: int = logging.INFO,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Setup and return a configured logger instance.
    
    This function creates a logger with a consistent format and configuration
    that can be used across all modules in the Stockelper Airflow project.
    
    Args:
        name (str): Name of the logger (typically __name__ of the calling module)
        level (int): Logging level (default: logging.INFO)
        format_string (str, optional): Custom format string. If None, uses default format.
        
    Returns:
        logging.Logger: Configured logger instance
        
    Example:
        >>> from modules.common.logging_config import setup_logger
        >>> logger = setup_logger(__name__)
        >>> logger.info("This is an info message")
    """
    # Create logger
    logger = logging.getLogger(name)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    
    # Create formatter
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    formatter = logging.Formatter(format_string)
    handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(handler)
    
    # Prevent propagation to avoid duplicate logs in Airflow
    logger.propagate = False
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get an existing logger or create a new one with default settings.
    
    This is a convenience function that wraps setup_logger with default parameters.
    
    Args:
        name (str): Name of the logger
        
    Returns:
        logging.Logger: Logger instance
        
    Example:
        >>> from modules.common.logging_config import get_logger
        >>> logger = get_logger(__name__)
    """
    return setup_logger(name)


# Pre-configured logging levels for easy import
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL
