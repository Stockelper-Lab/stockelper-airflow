#!/bin/bash

##############################################################################
# Airflow Log Cleanup Script (Container Version)
#
# This script runs the log cleanup inside the Airflow container.
# It's a wrapper around the cleanup_logs.sh script.
#
# Usage:
#   ./cleanup_logs_container.sh [OPTIONS]
#
# Options:
#   -d, --days DAYS       Number of days to retain logs (default: 7)
#   -n, --dry-run         Show what would be deleted without actually deleting
#   -v, --verbose         Enable verbose output
#   -h, --help            Show this help message
#
# Author: Stockelper Team
# License: MIT
##############################################################################

set -e

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default configuration
RETENTION_DAYS=7
DRY_RUN=""
VERBOSE=""
CONTAINER_NAME="stockelper-airflow"

# Show help message
show_help() {
    cat << EOF
Airflow Log Cleanup Script (Container Version)

Usage: $0 [OPTIONS]

Options:
  -d, --days DAYS       Number of days to retain logs (default: 7)
  -n, --dry-run         Show what would be deleted without actually deleting
  -v, --verbose         Enable verbose output
  -h, --help            Show this help message

Examples:
  # Clean logs older than 7 days (default)
  $0

  # Clean logs older than 30 days
  $0 --days 30

  # Dry run to see what would be deleted
  $0 --dry-run

  # Clean logs with verbose output
  $0 --verbose --days 14

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--days)
            RETENTION_DAYS="$2"
            shift 2
            ;;
        -n|--dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        -v|--verbose)
            VERBOSE="--verbose"
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}[ERROR]${NC} Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}[ERROR]${NC} Container '${CONTAINER_NAME}' is not running"
    echo -e "${YELLOW}[INFO]${NC} Start the container with: docker compose up -d"
    exit 1
fi

echo -e "${BLUE}[INFO]${NC} Running log cleanup in container '${CONTAINER_NAME}'..."
echo -e "${BLUE}[INFO]${NC} Retention period: ${RETENTION_DAYS} days"

# Copy cleanup script to container
echo -e "${BLUE}[INFO]${NC} Copying cleanup script to container..."
docker cp "$(dirname "$0")/cleanup_logs.sh" "${CONTAINER_NAME}:/tmp/cleanup_logs.sh"

# Make script executable and run it
docker exec "${CONTAINER_NAME}" bash -c "
    chmod +x /tmp/cleanup_logs.sh && \
    /tmp/cleanup_logs.sh --days ${RETENTION_DAYS} --path /opt/airflow/logs ${DRY_RUN} ${VERBOSE}
"

echo -e "${GREEN}[SUCCESS]${NC} Log cleanup completed!"
