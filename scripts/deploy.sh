#!/bin/bash

# Stockelper Airflow Deployment Script
# This script builds and deploys the Airflow environment

set -e

echo "🚀 Starting Stockelper Airflow Deployment..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Navigate to the project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "📁 Project root: $PROJECT_ROOT"

# Check if required files exist
if [ ! -f "docker/Dockerfile" ]; then
    echo "❌ Dockerfile not found in docker/ directory"
    exit 1
fi

if [ ! -f "docker/docker-compose.yml" ]; then
    echo "❌ docker-compose.yml not found in docker/ directory"
    exit 1
fi

# Stop existing containers if running
echo "🛑 Stopping existing containers..."
cd docker
docker-compose down --remove-orphans || true

# Build the Docker image
echo "🔨 Building Docker image..."
docker-compose build --no-cache

# Start the services
echo "🚀 Starting Airflow services..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for Airflow to be ready..."
sleep 30

# Check if Airflow is running
if docker-compose ps | grep -q "Up"; then
    echo "✅ Airflow is running successfully!"
    echo ""
    echo "🌐 Access Airflow Web UI at: http://localhost:8080"
    echo "👤 Default credentials: admin/admin"
    echo ""
    echo "📊 Available DAGs:"
    echo "  - stock_report_crawler: Daily stock report crawling"
    echo "  - competitor_crawler: Daily competitor data collection"
    echo ""
    echo "🔧 To view logs: docker-compose logs -f"
    echo "🛑 To stop: docker-compose down"
else
    echo "❌ Failed to start Airflow services"
    echo "📋 Check logs with: docker-compose logs"
    exit 1
fi
