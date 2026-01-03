#!/bin/bash

##############################################################################
# Docker Network Setup Script
#
# This script creates the shared 'stockelper' Docker network if it doesn't exist.
# This network is used by all Stockelper services (Airflow, Neo4j, etc.)
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

NETWORK_NAME="stockelper"

echo -e "${BLUE}==>${NC} Checking Docker network: ${NETWORK_NAME}"

# Check if network already exists
if docker network ls | grep -q "${NETWORK_NAME}"; then
    echo -e "${GREEN}✓${NC} Network '${NETWORK_NAME}' already exists"
else
    echo -e "${YELLOW}→${NC} Creating network '${NETWORK_NAME}'..."
    docker network create --driver bridge "${NETWORK_NAME}"
    echo -e "${GREEN}✓${NC} Network '${NETWORK_NAME}' created successfully"
fi

# Show network details
echo -e "\n${BLUE}==>${NC} Network details:"
docker network inspect "${NETWORK_NAME}" --format '{{json .}}' | python3 -m json.tool | head -20

echo -e "\n${GREEN}✓${NC} Network setup completed!"
