# 로깅 가이드

Stockelper Airflow 프로젝트의 통합 로깅 시스템 사용 가이드입니다.

## 개요

모든 모듈과 DAG에서 일관된 로깅을 위해 공통 로깅 설정 모듈(`modules/common/logging_config.py`)을 사용합니다.

## 로깅 설정의 중복 문제 해결

### 이전 방식 (중복된 설정)

각 파일마다 로깅 설정을 반복:

```python
# ❌ 나쁜 예: 각 파일마다 중복
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
```

**문제점**:
- 코드 중복
- 일관성 없는 로그 포맷
- 유지보수 어려움
- Airflow에서 중복 로그 발생 가능

### 새로운 방식 (통합 설정)

공통 모듈 사용:

```python
# ✅ 좋은 예: 공통 모듈 사용
import sys
sys.path.insert(0, '/opt/airflow')

from modules.common.logging_config import setup_logger

logger = setup_logger(__name__)
```

**장점**:
- 코드 중복 제거
- 일관된 로그 포맷
- 중앙 집중식 관리
- Airflow 환경에 최적화

---

## 사용 방법

### 1. 기본 사용법

```python
from modules.common.logging_config import setup_logger

# 로거 생성
logger = setup_logger(__name__)

# 로그 출력
logger.debug("디버그 메시지")
logger.info("정보 메시지")
logger.warning("경고 메시지")
logger.error("에러 메시지")
logger.critical("치명적 에러 메시지")
```

### 2. 커스텀 로그 레벨

```python
from modules.common.logging_config import setup_logger, DEBUG

# 디버그 레벨로 로거 생성
logger = setup_logger(__name__, level=DEBUG)
```

### 3. 커스텀 포맷

```python
from modules.common.logging_config import setup_logger

# 커스텀 포맷 지정
custom_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
logger = setup_logger(__name__, format_string=custom_format)
```

### 4. 간편한 로거 가져오기

```python
from modules.common.logging_config import get_logger

# 기본 설정으로 로거 가져오기
logger = get_logger(__name__)
```

---

## 로그 레벨

| 레벨 | 값 | 사용 시기 |
|------|-----|----------|
| `DEBUG` | 10 | 상세한 디버깅 정보 |
| `INFO` | 20 | 일반 정보 메시지 (기본값) |
| `WARNING` | 30 | 경고 메시지 |
| `ERROR` | 40 | 에러 메시지 |
| `CRITICAL` | 50 | 치명적 에러 |

### 레벨별 사용 예시

```python
# DEBUG: 변수 값, 상태 추적
logger.debug(f"Processing company: {company_name}, code: {code}")

# INFO: 주요 작업 진행 상황
logger.info("Starting report crawling...")
logger.info(f"Successfully crawled {count} reports")

# WARNING: 문제가 될 수 있지만 계속 진행 가능
logger.warning(f"Could not find summary for report: {title}")

# ERROR: 에러 발생, 작업 실패
logger.error(f"Failed to connect to MongoDB: {error}")

# CRITICAL: 시스템 중단이 필요한 심각한 에러
logger.critical("Database connection lost, shutting down")
```

---

## DAG에서 사용하기

### 예시: stock_report_crawler_dag.py

```python
import sys
sys.path.insert(0, '/opt/airflow')

from modules.common.logging_config import setup_logger

# 로거 설정
logger = setup_logger(__name__)

def crawl_stock_report(**kwargs):
    """Execute report crawling"""
    try:
        logger.info("Starting report crawling...")
        # 크롤링 로직
        logger.info("Report crawling completed")
        return True
    except Exception as e:
        logger.error(f"Report crawling failed: {e}")
        raise
```

---

## 모듈에서 사용하기

### 예시: stock_report_crawler.py

```python
import sys
sys.path.insert(0, '/opt/airflow')

from modules.common.logging_config import setup_logger

# 로거 설정
logger = setup_logger(__name__)

class StockReportCrawler:
    def __init__(self):
        logger.info("Initializing StockReportCrawler")
        
    def crawl(self):
        logger.info("Starting crawl operation")
        try:
            # 크롤링 로직
            logger.debug(f"Found {len(reports)} reports")
            logger.info("Crawl completed successfully")
        except Exception as e:
            logger.error(f"Crawl failed: {e}")
            raise
```

---

## 로그 포맷

### 기본 포맷

```
%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

### 출력 예시

```
2025-10-12 20:30:15,123 - dags.stock_report_crawler_dag - INFO - Starting report crawling...
2025-10-12 20:30:20,456 - modules.report_crawler.stock_report_crawler - INFO - Found 50 reports
2025-10-12 20:30:25,789 - dags.stock_report_crawler_dag - INFO - Report crawling completed
```

### 포맷 구성 요소

- `%(asctime)s`: 타임스탬프
- `%(name)s`: 로거 이름 (모듈 경로)
- `%(levelname)s`: 로그 레벨
- `%(message)s`: 로그 메시지

---

## Airflow 로그 확인

### 1. Airflow UI에서 확인

1. Airflow UI 접속: http://localhost:21003
2. DAG 선택
3. Task Instance 클릭
4. **Log** 탭 선택

### 2. 파일 시스템에서 확인

```bash
# 로그 디렉토리
cd /opt/airflow/logs

# 특정 DAG 로그
cat logs/stock_report_crawler/crawl_stock_report/2025-10-12/1.log

# 실시간 로그 확인
tail -f logs/stock_report_crawler/crawl_stock_report/2025-10-12/1.log
```

### 3. Docker 컨테이너에서 확인

```bash
# 컨테이너 로그
docker logs -f stockelper-airflow

# 컨테이너 내부 로그 파일
docker exec stockelper-airflow tail -f /opt/airflow/logs/scheduler/latest/scheduler.log
```

---

## 로그 관리

### 로그 정리

`log_cleanup_dag`가 자동으로 오래된 로그를 정리합니다:

- **스케줄**: 매일 오전 2시 (UTC)
- **보관 기간**: 7일
- **자동 정리**: 7일 이상 된 로그 파일 삭제

### 수동 로그 정리

```bash
# 스크립트 실행
/opt/airflow/scripts/cleanup_logs.sh

# 또는 직접 삭제
find /opt/airflow/logs -type f -mtime +7 -delete
```

---

## 모범 사례

### 1. 적절한 로그 레벨 사용

```python
# ✅ 좋은 예
logger.info("Starting crawl operation")  # 주요 작업
logger.debug(f"Processing item {i}/{total}")  # 상세 정보
logger.warning("Retrying after connection timeout")  # 경고
logger.error(f"Failed to save data: {error}")  # 에러

# ❌ 나쁜 예
logger.info(f"Processing item {i}/{total}")  # 너무 많은 INFO 로그
logger.error("Connection timeout")  # 재시도 가능한 경우 WARNING 사용
```

### 2. 구조화된 로그 메시지

```python
# ✅ 좋은 예: 명확하고 구조화된 메시지
logger.info(f"Crawling completed: {success_count} success, {error_count} errors")
logger.error(f"MongoDB connection failed: host={host}, port={port}, error={error}")

# ❌ 나쁜 예: 모호한 메시지
logger.info("Done")
logger.error("Error occurred")
```

### 3. 예외 처리와 로깅

```python
# ✅ 좋은 예: 예외 정보 포함
try:
    result = risky_operation()
except Exception as e:
    logger.error(f"Operation failed: {e}", exc_info=True)
    raise

# ❌ 나쁜 예: 예외 정보 누락
try:
    result = risky_operation()
except Exception as e:
    logger.error("Operation failed")
    raise
```

### 4. 민감한 정보 보호

```python
# ✅ 좋은 예: 민감한 정보 마스킹
logger.info(f"Connecting to MongoDB: {uri.split('@')[1]}")  # 비밀번호 제외

# ❌ 나쁜 예: 민감한 정보 노출
logger.info(f"Connecting to MongoDB: {uri}")  # 비밀번호 포함
```

---

## 문제 해결

### 로그가 출력되지 않음

**원인**: 로거가 제대로 설정되지 않음

**해결**:
```python
# sys.path 확인
import sys
print(sys.path)

# 로거 확인
logger = setup_logger(__name__)
print(logger.handlers)
```

### 중복 로그 출력

**원인**: 여러 핸들러가 추가됨

**해결**: `setup_logger`는 이미 중복 방지 로직이 있음
```python
# 로거가 이미 핸들러를 가지고 있으면 스킵
if logger.handlers:
    return logger
```

### 로그 레벨이 적용되지 않음

**원인**: Airflow 설정이 우선순위가 높음

**해결**: `airflow.cfg` 또는 환경 변수 확인
```bash
# 환경 변수로 설정
export AIRFLOW__LOGGING__LOGGING_LEVEL=DEBUG
```

---

## 참고 자료

- [Python Logging Documentation](https://docs.python.org/3/library/logging.html)
- [Airflow Logging Documentation](https://airflow.apache.org/docs/apache-airflow/stable/logging-monitoring/logging-tasks.html)
- [Best Practices for Logging](https://docs.python-guide.org/writing/logging/)

---

## 요약

1. **공통 모듈 사용**: `modules/common/logging_config.py`
2. **일관된 사용법**: `setup_logger(__name__)`
3. **적절한 레벨**: DEBUG < INFO < WARNING < ERROR < CRITICAL
4. **구조화된 메시지**: 명확하고 정보가 풍부한 로그
5. **민감 정보 보호**: 비밀번호, API 키 등 마스킹

이 가이드를 따르면 Stockelper Airflow 프로젝트에서 일관되고 효율적인 로깅을 구현할 수 있습니다.
