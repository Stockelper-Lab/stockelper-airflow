# Stockelper Airflow DAGs

이 저장소는 Stockelper 프로젝트를 위한 Apache Airflow DAG와 모듈들을 포함하며, 오픈소스 배포를 위해 구성되었습니다. DAG들은 금융 분석과 주식 시장 인텔리전스를 위한 다양한 데이터 수집 및 처리 작업을 담당합니다.

## 🏗️ 아키텍처 개요

저장소는 다음과 같은 구조로 구성되어 있습니다:

```
stockelper-airflow/
├── dags/                           # Airflow DAG 정의 파일
│   ├── stock_report_crawler_dag.py
│   ├── competitor_crawler_dag.py
│   └── log_cleanup_dag.py
├── modules/                        # 재사용 가능한 Python 모듈
│   ├── common/                     # 공통 유틸리티
│   │   └── logging_config.py
│   ├── report_crawler/
│   │   └── stock_report_crawler.py
│   └── company_crawler/
│       └── compete_company_crawler.py
├── config/                         # 설정 파일
├── scripts/                        # 유틸리티 스크립트
├── docs/                           # 문서
└── README.md                       # 이 파일
```

## 📊 사용 가능한 DAG

### 1. 주식 리포트 크롤러 (`stock_report_crawler_dag.py`)

**스케줄**: 매일 00:00 UTC  
**목적**: 금융 웹사이트에서 주식 리서치 리포트를 크롤링하여 MongoDB에 저장

**태스크**:
- `check_mongodb_connection`: MongoDB 연결 확인
- `crawl_stock_reports`: 메인 크롤링 로직 실행
- `report_crawl_results`: 크롤링 통계 및 결과 보고

**데이터 소스**: 금융 리서치 리포트 웹사이트  
**출력**: 구조화된 리포트 데이터가 포함된 MongoDB 컬렉션

### 2. 경쟁사 크롤러 (`competitor_crawler_dag.py`)

**스케줄**: 매일 00:00 UTC  
**목적**: Wisereport에서 모든 상장 기업의 경쟁사 정보 크롤링

**태스크**:
- `crawl_competitor_companies`: KOSPI/KOSDAQ/KONEX 기업의 경쟁사 데이터 수집

**데이터 소스**: Wisereport 경쟁사 분석 API  
**출력**: 기업 경쟁사 관계가 포함된 MongoDB 컬렉션

### 3. 로그 정리 (`log_cleanup_dag.py`)

**스케줄**: 매일 02:00 UTC  
**목적**: 오래된 Airflow 로그 파일 자동 정리

**태스크**:
- `get_log_statistics`: 현재 로그 상태 확인
- `cleanup_old_logs`: 7일 이상 된 로그 삭제
- `get_log_statistics_after_cleanup`: 정리 후 상태 확인

**보관 기간**: 7일  
**효과**: 디스크 공간 관리 및 성능 최적화

### 4. DART 공시(엄선된) 수집 (`dart_disclosure_collection_dag.py`)

**ID**: `dart_disclosure_collection_curated_major_reports`  
**스케줄**: 매일 08:00 KST  
**목적**: OpenDART major-report 엔드포인트 중 **엄선된 공시 유형만** 전 종목 대상으로 수집하여 Postgres에 적재

**태스크**:
- `load_universe_template`: (이벤트 추출용) 유니버스 로드
- `collect_curated_major_reports`: 엄선된 공시 엔드포인트 수집
- `extract_events`: (유니버스 대상) LLM 이벤트/감성 추출
- `pattern_matching`: (placeholder) 후처리

**출력**: `postgres_default` DB의 `dart_*` 테이블들 + `dart_event_extractions`

### 5. DART 공시(엄선된) 백필 (`dart_disclosure_collection_backfill_dag.py`)

**ID**: `dart_disclosure_collection_curated_major_reports_backfill`  
**스케줄**: 매일 1회 (`@daily`)  
**목적**: 장기 기간(기본 20년) 범위에서 엄선된 공시 엔드포인트를 청크 단위로 백필

### 6. DART 이벤트/감성 추출 백필 (`dart_event_extraction_backfill_dag.py`)

**ID**: `dart_event_extraction_universe_backfill`  
**스케줄**: 수동 (schedule=None)  
**목적**: 백필된 `dart_*` 테이블을 기반으로 유니버스 종목에 대해 이벤트/감성 추출을 재처리

## 🔧 모듈

### 공통 모듈

**위치**: `modules/common/logging_config.py`

**주요 기능**:
- 통합 로깅 설정
- 일관된 로그 포맷
- Airflow 환경 최적화
- 중복 핸들러 방지

**주요 함수**:
- `setup_logger()`: 로거 인스턴스 생성 및 설정
- `get_logger()`: 기본 설정으로 로거 가져오기

### 리포트 크롤러 모듈

**위치**: `modules/report_crawler/stock_report_crawler.py`

**주요 기능**:
- Selenium 기반 웹 스크래핑
- 중복 방지 기능이 포함된 MongoDB 통합
- 설정 가능한 날짜 범위 크롤링
- 포괄적인 로깅 및 오류 처리

**메인 클래스**: `StockReportCrawler`
- `crawl_daily_report()`: 지정된 날짜 범위의 리포트 크롤링
- `setup_driver()`: Selenium WebDriver 설정
- `get_crawl_statistics()`: 크롤링 통계 조회

### 기업 크롤러 모듈

**위치**: `modules/company_crawler/compete_company_crawler.py`

**주요 기능**:
- 주식 목록을 위한 FinanceDataReader 통합
- REST API 데이터 수집
- MongoDB upsert 작업
- 재시도 메커니즘
- 개발용 테스트 모드

**주요 함수**:
- `get_all_stock_codes()`: 모든 상장 기업 코드 조회
- `fetch_html()`: 재시도 기능이 포함된 HTTP 요청 처리
- `parse_company_data()`: JSON 데이터 파싱 및 추출

## 🚀 시작하기

### 사전 요구사항

- Docker 및 Docker Compose (권장)
- 또는 Python 3.11+ 및 MongoDB (수동 설치용)

### Docker를 사용한 빠른 시작 (권장)

제공된 Docker 설정을 사용하는 것이 가장 쉬운 방법입니다:

1. **저장소 클론**:
   ```bash
   git clone <repository-url>
   cd stockelper-airflow
   ```

2. **환경 설정** (선택사항):
   ```bash
   cp .env.example .env
   # MongoDB 연결 및 기타 설정을 사용자 정의하려면 .env 파일을 편집하세요
   ```

3. **원클릭 배포**:
   ```bash
   ./scripts/deploy.sh
   ```

4. **Airflow 웹 UI 접속**:
   - URL: `http://localhost:21003`
   - 기본 자격증명: `.env` 파일에서 설정 가능
   - 네트워크: `stockelper` 공유 네트워크 사용

5. **서비스 중지**:
   ```bash
   docker compose down
   ```

### 수동 설치

Docker 없이 설치하려는 경우:

1. **의존성 설치**:
   ```bash
   pip install -r requirements.txt
   ```

2. **MongoDB 설정**:
   - MongoDB 설치 및 시작
   - 환경에서 `MONGODB_URI` 업데이트

3. **Airflow 초기화**:
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

4. **Airflow 시작**:
   ```bash
   # 터미널 1: 스케줄러 시작
   airflow scheduler
   
   # 터미널 2: 웹서버 시작
   airflow webserver --port 8080
   ```

### 환경 설정

저장소에는 모든 설정 가능한 옵션이 포함된 `.env.example` 파일이 있습니다:

```bash
# MongoDB 설정
MONGODB_URI=mongodb+srv://stockelper:YOUR_PASSWORD@stockelper.btl2cdx.mongodb.net/
MONGO_DATABASE=stockelper

# Airflow Secret Key
AIRFLOW_SECRET_KEY=change-this-secret-key-in-production

# Airflow Admin 계정 (선택사항)
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=admin
AIRFLOW_ADMIN_EMAIL=admin@stockelper.com
```

상세한 설정 방법은 [docs/ADMIN_USER_SETUP.md](docs/ADMIN_USER_SETUP.md)를 참고하세요.

## 📝 설정

### MongoDB 컬렉션

DAG들은 다음 MongoDB 컬렉션을 생성하고 사용합니다:

- **`stock_reports`**: 금융 리서치 리포트
  - 필드: `date`, `company`, `code`, `title`, `summary`, `url`, `crawled_at`
  - 인덱스: 중복 방지를 위한 `(date, company, code)` 복합 인덱스

- **`competitors`**: 기업 경쟁사 관계
  - 필드: `_id` (기업 코드), `target_company`, `competitors`, `last_crawled_at`
  - 인덱스: 기업 코드의 기본 키

### 로깅

모든 모듈은 통합 로깅 설정(`modules/common/logging_config.py`)을 사용합니다:
- **레벨**: INFO (변경 가능)
- **형식**: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- **출력**: 콘솔 및 Airflow 태스크 로그
- **특징**: 중복 방지, Airflow 최적화

상세한 사용법은 [docs/LOGGING_GUIDE.md](docs/LOGGING_GUIDE.md)를 참고하세요.

## 🔍 모니터링 및 디버깅

### DAG 모니터링

- Airflow 웹 UI를 사용하여 DAG 실행 모니터링
- 상세한 실행 정보는 태스크 로그 확인
- 실패한 태스크에 대한 알림 설정

### 일반적인 문제

문제 해결에 대한 상세한 가이드는 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)를 참고하세요.

**주요 문제**:
- MongoDB 연결 실패
- Selenium WebDriver 오류
- DAG가 표시되지 않음
- 포트 충돌
- 메모리 부족

## 🛡️ 보안 고려사항

- **자격증명**: 모든 민감한 정보는 `<>` 플레이스홀더로 편집됨
- **환경 변수**: 모든 설정에 환경 변수 사용
- **네트워크 보안**: MongoDB가 공용 인터넷에 노출되지 않도록 확인
- **속도 제한**: 대상 웹사이트에 과부하를 주지 않도록 내장된 지연

## 📚 문서

전체 문서는 `docs/` 폴더에서 확인할 수 있습니다:

- **[QUICKSTART.md](docs/QUICKSTART.md)** - 빠른 시작 가이드
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - 시스템 아키텍처
- **[DEVELOPMENT.md](docs/DEVELOPMENT.md)** - 개발 가이드
- **[API_REFERENCE.md](docs/API_REFERENCE.md)** - API 레퍼런스
- **[TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - 문제 해결
- **[LOGGING_GUIDE.md](docs/LOGGING_GUIDE.md)** - 로깅 가이드
- **[ADMIN_USER_SETUP.md](docs/ADMIN_USER_SETUP.md)** - Admin 설정
- **[LOG_MANAGEMENT.md](docs/LOG_MANAGEMENT.md)** - 로그 관리
- **[DOCKER_COMPOSE_CHANGES.md](docs/DOCKER_COMPOSE_CHANGES.md)** - Docker 변경사항

## 🤝 기여하기

1. 저장소 포크
2. 기능 브랜치 생성: `git checkout -b feature/new-feature`
3. 변경사항 및 테스트 추가
4. 변경사항 커밋: `git commit -am 'Add new feature'`
5. 브랜치에 푸시: `git push origin feature/new-feature`
6. Pull Request 제출

상세한 개발 가이드는 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)를 참고하세요.

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 라이선스가 부여됩니다 - 자세한 내용은 LICENSE 파일을 참조하세요.

## 🙋‍♂️ 지원

질문, 이슈 또는 기여에 대해서는:

- GitHub 저장소에 이슈 생성
- 기존 문서 및 로그 확인
- Airflow 모범 사례 검토

## 📚 추가 자료

- [Apache Airflow 문서](https://airflow.apache.org/docs/)
- [MongoDB Python 드라이버](https://pymongo.readthedocs.io/)
- [Selenium WebDriver](https://selenium-python.readthedocs.io/)
- [FinanceDataReader](https://github.com/FinanceData/FinanceDataReader)