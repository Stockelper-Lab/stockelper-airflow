"""
Database Connection Module

This module provides a centralized way to connect to MongoDB.
It reads connection details from environment variables and provides a function
to get a database connection object.

Author: Stockelper Team
License: MIT
"""

import os
import pymongo
from .logging_config import setup_logger

# Setup logger
logger = setup_logger(__name__)

# Environment variables
MONGODB_URI = os.getenv("MONGODB_URI")
MONGO_DATABASE = os.getenv("MONGO_DATABASE")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is required")
if not MONGO_DATABASE:
    raise ValueError("MONGO_DATABASE environment variable is required")

def get_db_connection():
    """
    Establishes a connection to MongoDB and returns a database object.

    Returns:
        pymongo.database.Database: The MongoDB database object.
    
    Raises:
        ConnectionFailure: If the connection to MongoDB fails.
    """

    try:
        client = pymongo.MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.server_info()  # Test connection
        db = client[MONGO_DATABASE]
        logger.info(f"Successfully connected to MongoDB database: {MONGO_DATABASE}")
        return db
    except pymongo.errors.ConnectionFailure as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise
