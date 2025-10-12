# API 레퍼런스

Stockelper Airflow 모듈 및 함수의 상세 API 문서입니다.

## 📚 목차

- [공통 모듈](#공통-모듈)
- [크롤러 모듈](#크롤러-모듈)
- [DAG 함수](#dag-함수)
- [환경 변수](#환경-변수)

---

## 공통 모듈

### modules.common.logging_config

통합 로깅 설정 모듈

#### `setup_logger(name, level=INFO, format_string=None)`

로거 인스턴스를 생성하고 설정합니다.

**Parameters**:
- `name` (str): 로거 이름 (일반적으로 `__name__` 사용)
- `level` (int, optional): 로깅 레벨. 기본값: `logging.INFO`
- `format_string` (str, optional): 커스텀 포맷 문자열. 기본값: `'%(asctime)s - %(name)s - %(levelname)s - %(message)s'`

**Returns**:
- `logging.Logger`: 설정된 로거 인스턴스

**Example**:
```python
from modules.common.logging_config import setup_logger

logger = setup_logger(__name__)
logger.info("This is an info message")
```

#### `get_logger(name)`

기본 설정으로 로거를 가져옵니다.

**Parameters**:
- `name` (str): 로거 이름

**Returns**:
- `logging.Logger`: 로거 인스턴스

**Example**:
```python
from modules.common.logging_config import get_logger

logger = get_logger(__name__)
```

---

## 크롤러 모듈

### modules.report_crawler.stock_report_crawler

주식 리포트 크롤링 모듈

#### `class StockReportCrawler`

주식 리서치 리포트를 크롤링하는 클래스

##### `__init__(mongodb_uri=None, mongo_database='stockelper', headless=True)`

크롤러를 초기화합니다.

**Parameters**:
- `mongodb_uri` (str, optional): MongoDB 연결 URI. 기본값: 환경 변수 `MONGODB_URI`
- `mongo_database` (str, optional): 데이터베이스 이름. 기본값: `'stockelper'`
- `headless` (bool, optional): 헤드리스 모드 사용 여부. 기본값: `True`

**Raises**:
- `Exception`: MongoDB 연결 실패 시

**Example**:
```python
from modules.report_crawler.stock_report_crawler import StockReportCrawler

crawler = StockReportCrawler(
    mongodb_uri="mongodb://localhost:27017",
    mongo_database="stockelper",
    headless=True
)
```

##### `crawl_daily_report(daily=True, start_date=None, end_date=None)`

지정된 날짜 범위의 리포트를 크롤링합니다.

**Parameters**:
- `daily` (bool, optional): True면 오늘 날짜만 크롤링. 기본값: `True`
- `start_date` (str, optional): 시작 날짜 (YYYY-MM-DD 형식)
- `end_date` (str, optional): 종료 날짜 (YYYY-MM-DD 형식)

**Returns**:
- `dict`: 크롤링 결과
  ```python
  {
      "success": True,
      "total_reports": 50,
      "successful_saves": 48,
      "errors": [],
      "date_range": ["2025-10-12"]
  }
  ```

**Example**:
```python
# 오늘 날짜만 크롤링
result = crawler.crawl_daily_report(daily=True)

# 날짜 범위 지정
result = crawler.crawl_daily_report(
    daily=False,
    start_date="2025-10-01",
    end_date="2025-10-12"
)
```

##### `setup_driver()`

Selenium WebDriver를 설정합니다.

**Returns**:
- `bool`: 성공 시 `True`, 실패 시 `False`

**Example**:
```python
if crawler.setup_driver():
    print("WebDriver initialized successfully")
```

##### `get_crawl_statistics(date_str=None)`

크롤링 통계를 조회합니다.

**Parameters**:
- `date_str` (str, optional): 특정 날짜 필터 (YYYY-MM-DD 형식)

**Returns**:
- `dict`: 통계 정보
  ```python
  {
      "total_reports": 1000,
      "unique_companies": 150,
      "latest_crawl": "2025-10-12T20:30:15.123Z",
      "companies": ["삼성전자", "SK하이닉스", ...]
  }
  ```

**Example**:
```python
# 전체 통계
stats = crawler.get_crawl_statistics()

# 특정 날짜 통계
stats = crawler.get_crawl_statistics(date_str="2025-10-12")
```

---

### modules.company_crawler.compete_company_crawler

기업 경쟁사 정보 크롤링 모듈

#### `get_mongo_collection()`

MongoDB 컬렉션에 연결합니다.

**Returns**:
- `pymongo.Collection`: MongoDB 컬렉션 객체
- `None`: 연결 실패 시

**Example**:
```python
from modules.company_crawler.compete_company_crawler import get_mongo_collection

collection = get_mongo_collection()
if collection:
    print("Connected to MongoDB")
```

#### `get_all_stock_codes()`

모든 상장 기업의 종목 코드를 조회합니다.

**Returns**:
- `list`: 종목 코드 리스트
  ```python
  ["005930", "000660", "035420", ...]
  ```

**Example**:
```python
from modules.company_crawler.compete_company_crawler import get_all_stock_codes

codes = get_all_stock_codes()
print(f"Total stocks: {len(codes)}")
```

#### `fetch_html(url, retries=3, delay=1)`

재시도 메커니즘이 있는 HTTP 요청을 수행합니다.

**Parameters**:
- `url` (str): 요청할 URL
- `retries` (int, optional): 재시도 횟수. 기본값: `3`
- `delay` (int, optional): 재시도 간 대기 시간(초). 기본값: `1`

**Returns**:
- `bytes`: HTML 컨텐츠
- `None`: 실패 시

**Example**:
```python
from modules.company_crawler.compete_company_crawler import fetch_html

html = fetch_html("https://example.com", retries=5, delay=2)
if html:
    print("HTML fetched successfully")
```

#### `parse_company_data(html_content)`

HTML 컨텐츠에서 기업 데이터를 파싱합니다.

**Parameters**:
- `html_content` (bytes): HTML 컨텐츠

**Returns**:
- `tuple`: (target_company, competitors)
  ```python
  (
      {"code": "005930", "name": "삼성전자", "market_value": "400000000000000"},
      [
          {"code": "000660", "name": "SK하이닉스", "market_value": "80000000000000"},
          ...
      ]
  )
  ```

**Example**:
```python
from modules.company_crawler.compete_company_crawler import parse_company_data

target, competitors = parse_company_data(html_content)
print(f"Target: {target['name']}, Competitors: {len(competitors)}")
```

#### `main(test_mode=False)`

메인 실행 함수

**Parameters**:
- `test_mode` (bool, optional): 테스트 모드 (5개 종목만 처리). 기본값: `False`

**Example**:
```python
from modules.company_crawler.compete_company_crawler import main

# 전체 실행
main(test_mode=False)

# 테스트 모드
main(test_mode=True)
```

---

## DAG 함수

### dags.stock_report_crawler_dag

#### `check_mongodb_connection(**kwargs)`

MongoDB 연결을 확인합니다.

**Parameters**:
- `**kwargs`: Airflow 컨텍스트

**Returns**:
- `bool`: 성공 시 `True`

**Raises**:
- `Exception`: 연결 실패 시

**Example**:
```python
# Airflow Task로 사용
check_mongodb = PythonOperator(
    task_id='check_mongodb_connection',
    python_callable=check_mongodb_connection,
)
```

#### `crawl_stock_report(**kwargs)`

리포트 크롤링을 실행합니다.

**Parameters**:
- `**kwargs`: Airflow 컨텍스트
  - `ti`: TaskInstance (XCom 통신용)

**Returns**:
- `bool`: 성공 시 `True`

**XCom Pushes**:
- `crawl_result`: 크롤링 결과
  ```python
  {
      "status": "success",
      "result": {...}
  }
  ```

**Example**:
```python
crawl_report = PythonOperator(
    task_id='crawl_stock_report',
    python_callable=crawl_stock_report,
)
```

#### `report_results(**kwargs)`

크롤링 결과를 보고합니다.

**Parameters**:
- `**kwargs`: Airflow 컨텍스트
  - `ti`: TaskInstance (XCom 통신용)

**Returns**:
- `bool`: 항상 `True`

**Example**:
```python
report = PythonOperator(
    task_id='report_results',
    python_callable=report_results,
)
```

---

### dags.log_cleanup_dag

#### `cleanup_old_logs(**context)`

오래된 로그 파일을 정리합니다.

**Parameters**:
- `**context`: Airflow 컨텍스트
  - `ti`: TaskInstance

**Returns**:
- `dict`: 정리 결과
  ```python
  {
      "deleted_files": 150,
      "deleted_size_mb": 250.5,
      "errors": 0
  }
  ```

**XCom Pushes**:
- `deleted_files`: 삭제된 파일 수
- `deleted_size_mb`: 확보된 공간 (MB)
- `error_count`: 오류 수

**Example**:
```python
cleanup_task = PythonOperator(
    task_id='cleanup_old_logs',
    python_callable=cleanup_old_logs,
)
```

#### `get_log_statistics(**context)`

로그 폴더 통계를 조회합니다.

**Parameters**:
- `**context`: Airflow 컨텍스트
  - `ti`: TaskInstance

**Returns**:
- `dict`: 통계 정보
  ```python
  {
      "total_files": 500,
      "total_size_mb": 1024.5,
      "total_size_gb": 1.0
  }
  ```

**XCom Pushes**:
- `total_files`: 전체 파일 수
- `total_size_mb`: 전체 크기 (MB)

---

## 환경 변수

### 필수 환경 변수

#### `MONGODB_URI`

MongoDB 연결 URI

**Type**: `str`  
**Required**: Yes  
**Example**: `mongodb+srv://user:password@cluster.mongodb.net/`

#### `MONGO_DATABASE`

MongoDB 데이터베이스 이름

**Type**: `str`  
**Required**: Yes  
**Default**: `stockelper`  
**Example**: `stockelper`

#### `AIRFLOW_SECRET_KEY`

Airflow 웹서버 시크릿 키

**Type**: `str`  
**Required**: Yes  
**Example**: `your-secret-key-here`

### 선택적 환경 변수

#### `AIRFLOW_ADMIN_USERNAME`

Airflow Admin 사용자명

**Type**: `str`  
**Required**: No  
**Default**: `admin`  
**Example**: `admin`

#### `AIRFLOW_ADMIN_PASSWORD`

Airflow Admin 비밀번호

**Type**: `str`  
**Required**: No  
**Default**: `admin`  
**Example**: `your-secure-password`

#### `AIRFLOW_ADMIN_EMAIL`

Airflow Admin 이메일

**Type**: `str`  
**Required**: No  
**Default**: `admin@stockelper.com`  
**Example**: `admin@example.com`

---

## MongoDB 스키마

### stock_reports 컬렉션

```javascript
{
  "_id": ObjectId,
  "date": String,           // YYYY-MM-DD
  "company": String,        // 기업명
  "code": String,           // 종목코드
  "title": String,          // 리포트 제목
  "summary": String,        // 요약
  "url": String,            // 리포트 URL
  "crawled_at": ISODate     // 크롤링 시각
}
```

**인덱스**:
```javascript
{ date: 1, company: 1, code: 1 }  // unique
```

### competitors 컬렉션

```javascript
{
  "_id": String,            // 기업 코드
  "target_company": {
    "code": String,
    "name": String,
    "market_value": String
  },
  "competitors": [
    {
      "code": String,
      "name": String,
      "market_value": String
    }
  ],
  "last_crawled_at": ISODate
}
```

**인덱스**:
```javascript
{ _id: 1 }  // primary key
```

---

## 타입 정의

### CrawlResult

```python
from typing import TypedDict, List

class CrawlResult(TypedDict):
    success: bool
    total_reports: int
    successful_saves: int
    errors: List[str]
    date_range: List[str]
```

### CompanyData

```python
from typing import TypedDict

class CompanyData(TypedDict):
    code: str
    name: str
    market_value: str
```

### LogStatistics

```python
from typing import TypedDict

class LogStatistics(TypedDict):
    total_files: int
    total_size_mb: float
    total_size_gb: float
```

---

## 예외 처리

### 공통 예외

- `ValueError`: 필수 환경 변수 누락
- `pymongo.errors.ServerSelectionTimeoutError`: MongoDB 연결 실패
- `pymongo.errors.OperationFailure`: MongoDB 작업 실패
- `selenium.common.exceptions.WebDriverException`: WebDriver 오류
- `selenium.common.exceptions.TimeoutException`: 페이지 로딩 타임아웃

### 예외 처리 예시

```python
from pymongo.errors import ServerSelectionTimeoutError

try:
    crawler = StockReportCrawler()
    result = crawler.crawl_daily_report()
except ValueError as e:
    logger.error(f"Configuration error: {e}")
except ServerSelectionTimeoutError as e:
    logger.error(f"MongoDB connection failed: {e}")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise
```

---

## 버전 정보

- **Airflow**: 2.10.4
- **Python**: 3.12
- **Selenium**: 4.x
- **PyMongo**: 4.x
- **FinanceDataReader**: Latest

---

이 API 레퍼런스는 주요 모듈과 함수를 다룹니다. 추가 정보는 소스 코드의 docstring을 참고하세요.
