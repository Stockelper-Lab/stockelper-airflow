# 개발 가이드

Stockelper Airflow 프로젝트 개발을 위한 가이드입니다.

## 🛠️ 개발 환경 설정

### 사전 요구사항

- **Python 3.12+**
- **Docker & Docker Compose**
- **Git**
- **IDE**: VS Code, PyCharm 등

### 로컬 개발 환경

#### 1. 저장소 클론

```bash
git clone <repository-url>
cd stockelper-airflow
```

#### 2. Python 가상 환경 생성

```bash
# venv 생성
python -m venv venv

# 활성화 (Linux/Mac)
source venv/bin/activate

# 활성화 (Windows)
venv\Scripts\activate
```

#### 3. 의존성 설치

```bash
pip install --upgrade pip
pip install -r requirements.txt

# 개발 도구 설치
pip install pytest black flake8 mypy
```

#### 4. 환경 변수 설정

```bash
cp .env.example .env
nano .env
```

## 📝 새 DAG 작성하기

### DAG 템플릿

```python
"""
My Custom DAG

Description of what this DAG does.

Author: Your Name
License: MIT
"""

from datetime import datetime, timedelta
import os
import sys

# Add module path
sys.path.insert(0, '/opt/airflow')

from airflow import DAG
from airflow.operators.python import PythonOperator
from modules.common.logging_config import setup_logger

# Setup logger
logger = setup_logger(__name__)

# Environment variables
MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is required")

# Default arguments
default_args = {
    'owner': 'stockelper',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Task functions
def my_task(**kwargs):
    """Task description"""
    try:
        logger.info("Starting my task...")
        # Your logic here
        logger.info("Task completed successfully")
        return True
    except Exception as e:
        logger.error(f"Task failed: {e}")
        raise

# Create DAG
with DAG(
    dag_id='my_custom_dag',
    default_args=default_args,
    description='My custom DAG description',
    schedule='0 0 * * *',  # Daily at midnight
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['custom', 'my_tag'],
) as dag:
    
    task1 = PythonOperator(
        task_id='my_task',
        python_callable=my_task,
        provide_context=True,
    )
```

### DAG 파일 위치

```bash
# DAG 파일 생성
touch dags/my_custom_dag.py

# 권한 설정
chmod 644 dags/my_custom_dag.py
```

## 🔧 새 크롤러 모듈 작성하기

### 크롤러 템플릿

```python
"""
My Custom Crawler Module

Description of what this crawler does.

Author: Your Name
License: MIT
"""

import os
import sys
from pymongo import MongoClient

# Add module path
sys.path.insert(0, '/opt/airflow')

from modules.common.logging_config import setup_logger

# Setup logger
logger = setup_logger(__name__)

class MyCustomCrawler:
    """
    Custom crawler class.
    """
    
    def __init__(self, mongodb_uri=None, mongo_database="stockelper"):
        """
        Initialize the crawler.
        
        Args:
            mongodb_uri (str): MongoDB connection URI
            mongo_database (str): Database name
        """
        self.mongodb_uri = mongodb_uri or os.getenv("MONGODB_URI")
        self.mongo_database = mongo_database
        self.collection = None
        
        # Initialize MongoDB
        self._init_mongodb()
    
    def _init_mongodb(self):
        """Initialize MongoDB connection."""
        try:
            client = MongoClient(self.mongodb_uri, serverSelectionTimeoutMS=5000)
            client.server_info()
            db = client[self.mongo_database]
            self.collection = db["my_collection"]
            
            # Create indexes
            self.collection.create_index([("key", 1)], unique=True)
            
            logger.info("MongoDB connection successful")
        except Exception as e:
            logger.error(f"MongoDB connection failed: {e}")
            raise
    
    def crawl(self):
        """
        Main crawling logic.
        
        Returns:
            dict: Crawling results
        """
        try:
            logger.info("Starting crawl...")
            
            # Your crawling logic here
            data = self._fetch_data()
            
            # Save to MongoDB
            result = self._save_to_db(data)
            
            logger.info(f"Crawl completed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Crawl failed: {e}")
            raise
    
    def _fetch_data(self):
        """Fetch data from source."""
        # Implement your data fetching logic
        pass
    
    def _save_to_db(self, data):
        """Save data to MongoDB."""
        try:
            result = self.collection.update_one(
                {"_id": data["id"]},
                {"$set": data},
                upsert=True
            )
            return {
                "matched": result.matched_count,
                "modified": result.modified_count,
                "upserted": result.upserted_id
            }
        except Exception as e:
            logger.error(f"Failed to save to DB: {e}")
            raise

def main():
    """Main function for testing."""
    crawler = MyCustomCrawler()
    result = crawler.crawl()
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
```

### 모듈 파일 위치

```bash
# 모듈 디렉토리 생성
mkdir -p modules/my_crawler

# 파일 생성
touch modules/my_crawler/__init__.py
touch modules/my_crawler/my_crawler.py
```

## 🧪 테스트

### 단위 테스트 작성

```python
# tests/test_my_crawler.py
import pytest
from modules.my_crawler.my_crawler import MyCustomCrawler

def test_crawler_init():
    """Test crawler initialization."""
    crawler = MyCustomCrawler(
        mongodb_uri="mongodb://localhost:27017",
        mongo_database="test_db"
    )
    assert crawler.mongodb_uri is not None
    assert crawler.mongo_database == "test_db"

def test_crawl():
    """Test crawl function."""
    crawler = MyCustomCrawler()
    result = crawler.crawl()
    assert result is not None
    assert "matched" in result
```

### 테스트 실행

```bash
# 모든 테스트 실행
pytest tests/

# 특정 파일 테스트
pytest tests/test_my_crawler.py

# Coverage 확인
pytest --cov=modules tests/
```

### DAG 테스트

```bash
# DAG 구문 검사
docker exec stockelper-airflow airflow dags list-import-errors

# DAG 테스트 실행
docker exec stockelper-airflow airflow dags test my_custom_dag 2025-10-12

# 특정 Task 테스트
docker exec stockelper-airflow airflow tasks test my_custom_dag my_task 2025-10-12
```

## 🎨 코드 스타일

### Black (코드 포맷팅)

```bash
# 전체 코드 포맷팅
black dags/ modules/

# 특정 파일
black dags/my_custom_dag.py

# 체크만 (변경 안 함)
black --check dags/ modules/
```

### Flake8 (린팅)

```bash
# 전체 코드 린팅
flake8 dags/ modules/

# 특정 파일
flake8 dags/my_custom_dag.py

# 설정 파일 (.flake8)
[flake8]
max-line-length = 100
exclude = .git,__pycache__,venv
ignore = E203,W503
```

### MyPy (타입 체킹)

```bash
# 타입 체크
mypy modules/

# 설정 파일 (mypy.ini)
[mypy]
python_version = 3.12
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True
```

## 🔄 Git 워크플로우

### 브랜치 전략

```
main (production)
  └─► develop (development)
       ├─► feature/new-crawler
       ├─► feature/new-dag
       └─► bugfix/fix-issue
```

### 커밋 메시지 규칙

```
<type>(<scope>): <subject>

<body>

<footer>
```

**타입**:
- `feat`: 새 기능
- `fix`: 버그 수정
- `docs`: 문서 변경
- `style`: 코드 포맷팅
- `refactor`: 리팩토링
- `test`: 테스트 추가
- `chore`: 빌드/설정 변경

**예시**:
```
feat(crawler): Add news crawler module

- Implement news crawling logic
- Add MongoDB integration
- Add unit tests

Closes #123
```

### Pull Request 프로세스

1. **브랜치 생성**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **개발 및 커밋**
   ```bash
   git add .
   git commit -m "feat: Add new feature"
   ```

3. **테스트**
   ```bash
   pytest tests/
   black --check .
   flake8 .
   ```

4. **푸시**
   ```bash
   git push origin feature/my-feature
   ```

5. **PR 생성**
   - GitHub에서 Pull Request 생성
   - 리뷰어 지정
   - CI 통과 확인

## 🐳 Docker 개발

### 로컬 빌드

```bash
# 이미지 빌드
docker build -t stockelper-airflow:dev -f Dockerfile .

# 빌드 캐시 없이
docker build --no-cache -t stockelper-airflow:dev -f Dockerfile .
```

### 컨테이너 디버깅

```bash
# 컨테이너 접속
docker exec -it stockelper-airflow bash

# 로그 확인
docker logs -f stockelper-airflow

# 파일 복사 (컨테이너 → 호스트)
docker cp stockelper-airflow:/opt/airflow/logs ./logs

# 파일 복사 (호스트 → 컨테이너)
docker cp ./dags/new_dag.py stockelper-airflow:/opt/airflow/dags/
```

### Docker Compose 개발

```bash
# 개발 모드로 시작 (볼륨 마운트)
docker compose -f docker-compose.dev.yml up -d

# 특정 서비스만 재시작
docker compose restart airflow

# 로그 스트리밍
docker compose logs -f airflow
```

## 📊 디버깅

### Airflow CLI

```bash
# DAG 목록
docker exec stockelper-airflow airflow dags list

# Task 목록
docker exec stockelper-airflow airflow tasks list stock_report_crawler

# Variable 확인
docker exec stockelper-airflow airflow variables list

# Connection 확인
docker exec stockelper-airflow airflow connections list
```

### Python 디버거

```python
# DAG 파일에 추가
import pdb; pdb.set_trace()

# 또는
import ipdb; ipdb.set_trace()
```

### 로그 레벨 변경

```python
# 특정 모듈만 DEBUG 레벨
from modules.common.logging_config import setup_logger, DEBUG

logger = setup_logger(__name__, level=DEBUG)
```

## 🚀 배포

### 개발 환경

```bash
# 개발 서버 시작
./scripts/deploy.sh
```

### 프로덕션 환경

```bash
# 환경 변수 확인
cat .env

# 프로덕션 배포
docker compose -f docker-compose.prod.yml up -d

# 헬스 체크
curl http://localhost:21003/health
```

## 📚 유용한 리소스

### 공식 문서
- [Airflow Documentation](https://airflow.apache.org/docs/)
- [Python Best Practices](https://docs.python-guide.org/)
- [Docker Documentation](https://docs.docker.com/)

### 내부 문서
- [Architecture](ARCHITECTURE.md)
- [Logging Guide](LOGGING_GUIDE.md)
- [Troubleshooting](TROUBLESHOOTING.md)

## 🤝 기여 가이드라인

1. **코드 품질**
   - PEP 8 준수
   - 타입 힌트 사용
   - Docstring 작성

2. **테스트**
   - 단위 테스트 작성
   - 커버리지 80% 이상

3. **문서화**
   - README 업데이트
   - Docstring 작성
   - 변경사항 기록

4. **리뷰**
   - 최소 1명 승인 필요
   - CI 통과 필수

---
