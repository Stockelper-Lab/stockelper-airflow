#!/bin/bash

# Stockelper Airflow Stop Script
# This script stops the Airflow environment

set -e

echo "🛑 Stopping Stockelper Airflow..."

# Navigate to the docker directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT/docker"

# Stop and remove containers
docker-compose down --remove-orphans

echo "✅ Airflow services stopped successfully!"
echo "💡 To start again, run: ./scripts/deploy.sh"
