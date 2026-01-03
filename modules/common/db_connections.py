"""
Database Connection Module

This module provides a centralized way to connect to MongoDB.
It reads connection details from environment variables and provides a function
to get a database connection object.

Author: Stockelper Team
License: MIT
"""

import pymongo
from .logging_config import setup_logger
from .airflow_settings import get_required_setting

# Setup logger
logger = setup_logger(__name__)

def get_db_connection():
    """
    Establishes a connection to MongoDB and returns a database object.

    Returns:
        pymongo.database.Database: The MongoDB database object.
    
    Raises:
        ConnectionFailure: If the connection to MongoDB fails.
    """

    try:
        mongodb_uri = get_required_setting("MONGODB_URI")
        mongo_database = get_required_setting("MONGO_DATABASE")

        client = pymongo.MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        client.server_info()  # Test connection
        db = client[mongo_database]
        logger.info("Successfully connected to MongoDB database: %s", mongo_database)
        return db
    except pymongo.errors.ConnectionFailure as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise
