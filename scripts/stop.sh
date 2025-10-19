#!/bin/bash

##############################################################################
# Stockelper Airflow Stop Script
#
# This script stops the Airflow environment
#
# Author: Stockelper Team
# License: MIT
##############################################################################

set -e

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🛑 Stopping Stockelper Airflow...${NC}"

# Navigate to the project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Stop and remove containers
docker compose down --remove-orphans

echo -e "${GREEN}✅ Airflow services stopped successfully!${NC}"
echo -e "${YELLOW}💡 To start again, run:${NC} ./scripts/deploy.sh"
