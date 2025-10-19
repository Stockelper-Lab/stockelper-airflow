#!/bin/bash

##############################################################################
# Stockelper Airflow Deployment Script
#
# This script builds and deploys the Airflow environment with proper
# network configuration and environment setup.
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

echo -e "${BLUE}🚀 Starting Stockelper Airflow Deployment...${NC}\n"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed. Please install Docker Compose first.${NC}"
    exit 1
fi

# Navigate to the project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo -e "${BLUE}📁 Project root:${NC} $PROJECT_ROOT\n"

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating from .env.example...${NC}"
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${GREEN}✓${NC} Created .env file. Please update it with your configuration."
        echo -e "${YELLOW}→${NC} Edit .env file and run this script again."
        exit 1
    else
        echo -e "${RED}❌ .env.example not found. Cannot create .env file.${NC}"
        exit 1
    fi
fi

# Check if required files exist
if [ ! -f "Dockerfile" ]; then
    echo -e "${RED}❌ Dockerfile not found in project root${NC}"
    exit 1
fi

if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}❌ docker-compose.yml not found${NC}"
    exit 1
fi

# Setup Docker network
echo -e "${BLUE}==>${NC} Setting up Docker network..."
./scripts/setup_network.sh

# Stop existing containers if running
echo -e "\n${BLUE}==>${NC} Stopping existing containers..."
docker compose down --remove-orphans || true

# Build the Docker image
echo -e "\n${BLUE}==>${NC} Building Docker image..."
docker compose build --no-cache

# Start the services
echo -e "\n${BLUE}==>${NC} Starting Airflow services..."
docker compose up -d

# Wait for services to be ready
echo -e "\n${BLUE}==>${NC} Waiting for Airflow to be ready..."
sleep 30

# Check if Airflow is running
if docker compose ps | grep -q "Up"; then
    echo -e "\n${GREEN}✅ Airflow is running successfully!${NC}\n"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}🌐 Access Airflow Web UI:${NC} http://localhost:21003"
    echo -e "${GREEN}👤 Default credentials:${NC} admin / admin"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    echo -e "${BLUE}📊 Available DAGs:${NC}"
    echo -e "  • ${GREEN}stock_report_crawler${NC}: Daily stock report crawling"
    echo -e "  • ${GREEN}competitor_crawler${NC}: Daily competitor data collection"
    echo -e "  • ${GREEN}log_cleanup${NC}: Automatic log cleanup (daily at 2 AM)\n"
    echo -e "${BLUE}🔧 Useful commands:${NC}"
    echo -e "  • View logs: ${YELLOW}docker compose logs -f${NC}"
    echo -e "  • Stop services: ${YELLOW}docker compose down${NC}"
    echo -e "  • Restart: ${YELLOW}docker compose restart${NC}\n"
else
    echo -e "\n${RED}❌ Failed to start Airflow services${NC}"
    echo -e "${YELLOW}📋 Check logs with:${NC} docker compose logs"
    exit 1
fi
