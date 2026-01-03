#!/bin/bash

##############################################################################
# Airflow Log Cleanup Script
#
# This script cleans up old Airflow logs to prevent disk space issues.
# It can be run manually or scheduled via cron.
#
# Usage:
#   ./cleanup_logs.sh [OPTIONS]
#
# Options:
#   -d, --days DAYS       Number of days to retain logs (default: 7)
#   -p, --path PATH       Path to Airflow logs directory (default: /opt/airflow/logs)
#   -n, --dry-run         Show what would be deleted without actually deleting
#   -v, --verbose         Enable verbose output
#   -h, --help            Show this help message
#
# Author: Stockelper Team
# License: MIT
##############################################################################

set -e

# Default configuration
RETENTION_DAYS=7
LOG_PATH="/opt/airflow/logs"
DRY_RUN=false
VERBOSE=false

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "\n${GREEN}==>${NC} $1"
}

# Show help message
show_help() {
    cat << EOF
Airflow Log Cleanup Script

Usage: $0 [OPTIONS]

Options:
  -d, --days DAYS       Number of days to retain logs (default: 7)
  -p, --path PATH       Path to Airflow logs directory (default: /opt/airflow/logs)
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
        -p|--path)
            LOG_PATH="$2"
            shift 2
            ;;
        -n|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validate inputs
if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
    log_error "Retention days must be a positive integer"
    exit 1
fi

if [ ! -d "$LOG_PATH" ]; then
    log_error "Log path does not exist: $LOG_PATH"
    exit 1
fi

# Main cleanup function
cleanup_logs() {
    log_step "Starting Airflow log cleanup"
    
    log_info "Configuration:"
    log_info "  Log path: $LOG_PATH"
    log_info "  Retention period: $RETENTION_DAYS days"
    log_info "  Dry run: $DRY_RUN"
    log_info "  Verbose: $VERBOSE"
    
    # Get current disk usage
    log_step "Checking current disk usage"
    BEFORE_SIZE=$(du -sh "$LOG_PATH" 2>/dev/null | cut -f1)
    BEFORE_FILES=$(find "$LOG_PATH" -type f 2>/dev/null | wc -l)
    log_info "Current size: $BEFORE_SIZE"
    log_info "Current files: $BEFORE_FILES"
    
    # Find and delete old log files
    log_step "Finding old log files"
    
    if [ "$DRY_RUN" = true ]; then
        log_warn "DRY RUN MODE - No files will be deleted"
        
        OLD_FILES=$(find "$LOG_PATH" -type f -mtime +$RETENTION_DAYS 2>/dev/null)
        OLD_FILES_COUNT=$(echo "$OLD_FILES" | grep -c . || echo "0")
        
        if [ "$OLD_FILES_COUNT" -gt 0 ]; then
            log_info "Would delete $OLD_FILES_COUNT files:"
            
            if [ "$VERBOSE" = true ]; then
                echo "$OLD_FILES"
            else
                echo "$OLD_FILES" | head -10
                if [ "$OLD_FILES_COUNT" -gt 10 ]; then
                    log_info "... and $((OLD_FILES_COUNT - 10)) more files"
                fi
            fi
        else
            log_info "No files to delete"
        fi
    else
        log_info "Deleting files older than $RETENTION_DAYS days..."
        
        DELETED_COUNT=0
        while IFS= read -r file; do
            if [ "$VERBOSE" = true ]; then
                log_info "Deleting: $file"
            fi
            rm -f "$file"
            ((DELETED_COUNT++))
        done < <(find "$LOG_PATH" -type f -mtime +$RETENTION_DAYS 2>/dev/null)
        
        log_success "Deleted $DELETED_COUNT files"
        
        # Remove empty directories
        log_step "Removing empty directories"
        EMPTY_DIRS=$(find "$LOG_PATH" -type d -empty 2>/dev/null | wc -l)
        
        if [ "$EMPTY_DIRS" -gt 0 ]; then
            find "$LOG_PATH" -type d -empty -delete 2>/dev/null
            log_success "Removed $EMPTY_DIRS empty directories"
        else
            log_info "No empty directories found"
        fi
        
        # Get final disk usage
        log_step "Final disk usage"
        AFTER_SIZE=$(du -sh "$LOG_PATH" 2>/dev/null | cut -f1)
        AFTER_FILES=$(find "$LOG_PATH" -type f 2>/dev/null | wc -l)
        
        log_info "Final size: $AFTER_SIZE (was: $BEFORE_SIZE)"
        log_info "Final files: $AFTER_FILES (was: $BEFORE_FILES)"
        log_success "Freed up space by removing $((BEFORE_FILES - AFTER_FILES)) files"
    fi
}

# Run cleanup
cleanup_logs

log_step "Log cleanup completed!"
