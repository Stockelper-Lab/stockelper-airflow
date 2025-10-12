# Stockelper Airflow Scripts

This directory contains utility scripts for managing the Stockelper Airflow environment.

## Available Scripts

### 1. deploy.sh
**Purpose**: Complete deployment script for Airflow environment

**Usage**:
```bash
./scripts/deploy.sh
```

**What it does**:
- Checks Docker and Docker Compose installation
- Validates required files (Dockerfile, docker-compose.yml, .env)
- Sets up Docker network
- Builds Docker image
- Starts Airflow services
- Displays access information

**Requirements**:
- Docker and Docker Compose installed
- `.env` file configured (will create from `.env.example` if missing)

---

### 2. stop.sh
**Purpose**: Stop all Airflow services

**Usage**:
```bash
./scripts/stop.sh
```

**What it does**:
- Stops and removes all Airflow containers
- Removes orphaned containers
- Preserves volumes (logs and database)

---

### 3. setup_network.sh
**Purpose**: Create shared Docker network for Stockelper services

**Usage**:
```bash
./scripts/setup_network.sh
```

**What it does**:
- Creates `stockelper` Docker bridge network if it doesn't exist
- Displays network details
- Used by other Stockelper services (Neo4j, MongoDB, etc.)

**Note**: This script is automatically called by `deploy.sh`

---

### 4. cleanup_logs.sh
**Purpose**: Clean up old Airflow log files

**Usage**:
```bash
# Inside the container
docker exec stockelper-airflow /opt/airflow/scripts/cleanup_logs.sh [OPTIONS]

# Or copy to container and run
docker cp scripts/cleanup_logs.sh stockelper-airflow:/tmp/
docker exec stockelper-airflow /tmp/cleanup_logs.sh [OPTIONS]
```

**Options**:
- `-d, --days DAYS`: Number of days to retain logs (default: 7)
- `-p, --path PATH`: Path to Airflow logs directory (default: /opt/airflow/logs)
- `-n, --dry-run`: Show what would be deleted without actually deleting
- `-v, --verbose`: Enable verbose output
- `-h, --help`: Show help message

**Examples**:
```bash
# Clean logs older than 7 days (default)
docker exec stockelper-airflow /tmp/cleanup_logs.sh

# Clean logs older than 30 days
docker exec stockelper-airflow /tmp/cleanup_logs.sh --days 30

# Dry run to see what would be deleted
docker exec stockelper-airflow /tmp/cleanup_logs.sh --dry-run

# Clean logs with verbose output
docker exec stockelper-airflow /tmp/cleanup_logs.sh --verbose --days 14
```

---

### 5. cleanup_logs_container.sh
**Purpose**: Wrapper script to run log cleanup from host machine

**Usage**:
```bash
./scripts/cleanup_logs_container.sh [OPTIONS]
```

**Options**:
- `-d, --days DAYS`: Number of days to retain logs (default: 7)
- `-n, --dry-run`: Show what would be deleted without actually deleting
- `-v, --verbose`: Enable verbose output
- `-h, --help`: Show help message

**Examples**:
```bash
# Clean logs older than 7 days (default)
./scripts/cleanup_logs_container.sh

# Clean logs older than 30 days
./scripts/cleanup_logs_container.sh --days 30

# Dry run to see what would be deleted
./scripts/cleanup_logs_container.sh --dry-run

# Clean logs with verbose output
./scripts/cleanup_logs_container.sh --verbose --days 14
```

**What it does**:
- Checks if Airflow container is running
- Copies `cleanup_logs.sh` to container
- Executes cleanup inside the container
- Displays results

---

## Common Workflows

### Initial Setup
```bash
# 1. Create .env file from example
cp .env.example .env

# 2. Edit .env with your configuration
nano .env

# 3. Deploy Airflow
./scripts/deploy.sh
```

### Daily Operations
```bash
# View logs
docker compose logs -f

# Restart services
docker compose restart

# Stop services
./scripts/stop.sh

# Start services again
docker compose up -d
```

### Maintenance
```bash
# Clean up old logs (dry run first)
./scripts/cleanup_logs_container.sh --dry-run

# Actually clean logs
./scripts/cleanup_logs_container.sh --days 7

# Rebuild and redeploy
./scripts/stop.sh
./scripts/deploy.sh
```

### Troubleshooting
```bash
# Check container status
docker ps -a | grep stockelper

# View container logs
docker logs stockelper-airflow

# Access container shell
docker exec -it stockelper-airflow bash

# Check Airflow configuration
docker exec stockelper-airflow airflow config list

# Test DAG
docker exec stockelper-airflow airflow dags test <dag_id> <execution_date>
```

---

## Environment Variables

All scripts use the following environment variables from `.env`:

- `AIRFLOW_SECRET_KEY`: Secret key for Airflow webserver
- `AIRFLOW_ADMIN_USERNAME`: Admin username (default: admin)
- `AIRFLOW_ADMIN_PASSWORD`: Admin password (default: admin)
- `AIRFLOW_ADMIN_EMAIL`: Admin email (default: admin@stockelper.com)
- `MONGODB_URI`: MongoDB connection string
- `MONGO_DATABASE`: MongoDB database name (default: stockelper)

---

## Network Configuration

The scripts use the `stockelper` Docker network for inter-service communication:

- **Network name**: `stockelper`
- **Driver**: bridge
- **External**: yes (shared with other Stockelper services)

Services on this network:
- Airflow (stockelper-airflow)
- Neo4j (stockelper-neo4j)
- MongoDB (mongodb-container)

---

## Port Configuration

- **Airflow Web UI**: http://localhost:21003
- **Container internal port**: 8080
- **Port mapping**: 21003:8080

---

## Volume Configuration

- **airflow_logs**: Persistent log storage
- **airflow_db**: SQLite database storage

---

## Notes

1. All scripts should be run from the project root directory
2. Scripts use color-coded output for better readability
3. Error handling is built into all scripts
4. Scripts follow the principle of least surprise
5. All scripts are idempotent (safe to run multiple times)

---

## License

MIT License - See LICENSE file for details

---

## Author

Stockelper Team
