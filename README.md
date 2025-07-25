# Stockelper Airflow DAGs

This repository contains Apache Airflow DAGs and modules for the Stockelper project, organized for open-source distribution. The DAGs handle various data collection and processing tasks for financial analysis and stock market intelligence.

## 🏗️ Architecture Overview

The repository is organized into the following structure:

```
stockelper-airflow/
├── dags/                    # Airflow DAG definitions
│   ├── stock_report_crawler_dag.py
│   └── competitor_crawler_dag.py
├── modules/                 # Reusable Python modules
│   ├── report_crawler/
│   │   └── crawler.py
│   └── company_crawler/
│       └── compete_company_crawler.py
├── config/                  # Configuration files
├── docker/                  # Docker setup files
├── scripts/                 # Utility scripts
└── README.md               # This file
```

## 📊 Available DAGs

### 1. Stock Report Crawler (`stock_report_crawler_dag.py`)

**Schedule**: Daily at 00:00 UTC  
**Purpose**: Crawls stock research reports from financial websites and stores them in MongoDB

**Tasks**:
- `check_mongodb_connection`: Verifies MongoDB connectivity
- `crawl_stock_reports`: Executes the main crawling logic
- `report_crawl_results`: Reports crawling statistics and results

**Data Source**: Financial research report websites  
**Output**: MongoDB collection with structured report data

### 2. Competitor Crawler (`competitor_crawler_dag.py`)

**Schedule**: Daily at midnight UTC  
**Purpose**: Crawls competitor information for all listed companies from Wisereport

**Tasks**:
- `crawl_competitor_companies`: Collects competitor data for KOSPI/KOSDAQ/KONEX companies

**Data Source**: Wisereport competitor analysis API  
**Output**: MongoDB collection with company competitor relationships

## 🔧 Modules

### Report Crawler Module

**Location**: `modules/report_crawler/crawler.py`

**Key Features**:
- Selenium-based web scraping
- Pandas data processing
- MongoDB integration with duplicate prevention
- Configurable date range crawling
- Comprehensive logging and error handling

**Main Class**: `StockReportCrawler`
- `crawl_daily_report()`: Crawls reports for specified date range
- `setup_driver()`: Configures Selenium WebDriver
- `process_data()`: Cleans and structures scraped data

### Company Crawler Module

**Location**: `modules/company_crawler/compete_company_crawler.py`

**Key Features**:
- FinanceDataReader integration for stock listings
- REST API data collection
- MongoDB upsert operations
- Retry mechanism with exponential backoff
- Test mode for development

**Main Functions**:
- `get_all_stock_codes()`: Retrieves all listed company codes
- `fetch_html()`: HTTP request handling with retries
- `parse_company_data()`: JSON data parsing and extraction

## 🚀 Getting Started

### Prerequisites

- Docker and Docker Compose (recommended)
- OR Python 3.11+ and MongoDB (for manual installation)

### Quick Start with Docker (Recommended)

The easiest way to get started is using the provided Docker setup:

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd stockelper-airflow
   ```

2. **Configure environment** (optional):
   ```bash
   cp .env.example .env
   # Edit .env file to customize MongoDB connection and other settings
   ```

3. **Deploy with one command**:
   ```bash
   ./scripts/deploy.sh
   ```

4. **Access Airflow Web UI**:
   - URL: `http://localhost:8080`
   - Default credentials: `admin/admin`

5. **Stop the services**:
   ```bash
   ./scripts/stop.sh
   ```

### Manual Installation

If you prefer to install without Docker:

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up MongoDB**:
   - Install and start MongoDB
   - Update `MONGODB_URI` in your environment

3. **Initialize Airflow**:
   ```bash
   export AIRFLOW_HOME=$(pwd)
   airflow db init
   airflow users create \
     --username admin \
     --firstname Admin \
     --lastname User \
     --role Admin \
     --email admin@stockelper.com \
     --password admin
   ```

4. **Start Airflow**:
   ```bash
   # Terminal 1: Start scheduler
   airflow scheduler
   
   # Terminal 2: Start webserver
   airflow webserver --port 8080
   ```

### Environment Configuration

The repository includes a `.env.example` file with all configurable options:

```bash
# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017/

# Airflow Configuration
AIRFLOW__CORE__EXECUTOR=SequentialExecutor
AIRFLOW__CORE__LOAD_EXAMPLES=False
AIRFLOW__WEBSERVER__WEB_SERVER_PORT=8080

# And many more options...
```

## 📝 Configuration

### MongoDB Collections

The DAGs create and use the following MongoDB collections:

- **`stock_reports`**: Financial research reports
  - Fields: `date`, `company`, `code`, `title`, `summary`, `url`, `crawled_at`
  - Indexes: Compound index on `(date, company, code)` for duplicate prevention

- **`competitors`**: Company competitor relationships
  - Fields: `_id` (company code), `target_company`, `competitors`, `last_crawled_at`
  - Indexes: Primary key on company code

### Logging

All modules use Python's `logging` module with the following configuration:
- **Level**: INFO
- **Format**: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- **Output**: Both console and Airflow task logs

## 🔍 Monitoring and Debugging

### DAG Monitoring

- Use Airflow Web UI to monitor DAG runs
- Check task logs for detailed execution information
- Set up alerts for failed tasks

### Common Issues

1. **MongoDB Connection Failures**:
   - Verify `MONGODB_URI` environment variable
   - Check network connectivity
   - Ensure MongoDB service is running

2. **Selenium WebDriver Issues**:
   - Ensure Chrome/ChromeDriver compatibility
   - Check headless mode configuration
   - Verify sufficient memory allocation

3. **Data Quality Issues**:
   - Monitor crawling success rates
   - Check for website structure changes
   - Validate data completeness

## 🛡️ Security Considerations

- **Credentials**: All sensitive information has been redacted with `<>` placeholders
- **Environment Variables**: Use environment variables for all configuration
- **Network Security**: Ensure MongoDB is not exposed to public internet
- **Rate Limiting**: Built-in delays prevent overwhelming target websites

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/new-feature`
3. Make changes and add tests
4. Commit changes: `git commit -am 'Add new feature'`
5. Push to branch: `git push origin feature/new-feature`
6. Submit a Pull Request

### Development Guidelines

- Follow PEP 8 style guidelines
- Add comprehensive logging
- Include error handling and retries
- Write unit tests for new modules
- Update documentation for new features

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙋‍♂️ Support

For questions, issues, or contributions:

- Create an issue in the GitHub repository
- Check existing documentation and logs
- Review Airflow best practices

## 📚 Additional Resources

- [Apache Airflow Documentation](https://airflow.apache.org/docs/)
- [MongoDB Python Driver](https://pymongo.readthedocs.io/)
- [Selenium WebDriver](https://selenium-python.readthedocs.io/)
- [FinanceDataReader](https://github.com/FinanceData/FinanceDataReader)