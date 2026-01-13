# Stockelper Airflow

한국 주식 시장 분석, 금융 공시 및 지식 그래프 구축을 위한 Apache Airflow 기반 데이터 오케스트레이션 및 ETL 파이프라인입니다.

## 개요

Stockelper Airflow는 한국 금융 시장 데이터의 수집, 처리 및 저장을 자동화하는 종합적인 데이터 엔지니어링 플랫폼입니다. KRX(한국거래소), DART(전자공시시스템), 다양한 금융 리포트 플랫폼 등 여러 데이터 소스와 통합하여 통합 데이터 웨어하우스 및 지식 그래프를 구축합니다.

### 주요 기능

- **자동화된 데이터 수집**: 주가, 금융 리포트, 규제 공시의 일일 자동 수집
- **다중 소스 통합**: KRX, DART, Wisereport 및 기타 금융 데이터 제공자
- **지식 그래프 구축**: 고급 분석을 위한 Neo4j 기반 관계형 데이터 모델링
- **확장 가능한 아키텍처**: 영구 스토리지를 갖춘 Docker 기반 배포
- **모니터링 및 유지보수**: 내장된 로그 관리 및 상태 확인 기능
- **PostgreSQL 및 MongoDB**: 구조화/비구조화 데이터를 위한 이중 데이터베이스 아키텍처

## 아키텍처

### 기술 스택

- **오케스트레이션**: Apache Airflow 2.10.4
- **데이터베이스**:
  - PostgreSQL (구조화 데이터: 주가, DART 공시)
  - MongoDB (비구조화 데이터: 리포트, 경쟁사 정보)
  - Neo4j (지식 그래프)
- **웹 스크래핑**: Selenium 4.27+ with Chrome/ChromeDriver
- **데이터 처리**: Pandas, FinanceDataReader
- **컨테이너 플랫폼**: Docker & Docker Compose

### 데이터 흐름

```
┌─────────────────┐
│  데이터 소스     │
│  - KRX          │
│  - DART         │
│  - Wisereport   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Airflow DAGs   │
│  - 크롤러       │
│  - ETL 작업     │
└────────┬────────┘
         │
         ├──────────┐
         ▼          ▼
┌──────────┐  ┌─────────┐
│PostgreSQL│  │ MongoDB │
│ (주가/공시)│  │(리포트) │
└─────┬────┘  └────┬────┘
      │            │
      └────┬───────┘
           ▼
    ┌──────────────┐
    │    Neo4j     │
    │  (지식 그래프) │
    └──────────────┘
```

## 프로젝트 구조

```
stockelper-airflow/
├── dags/                           # Airflow DAG 정의
│   ├── stock_report_crawler_dag.py
│   ├── competitor_crawler_dag.py
│   ├── stock_to_postgres_dag.py
│   ├── dart_disclosure_collection_dag.py
│   ├── dart_disclosure_collection_backfill_dag.py
│   ├── neo4j_kg_etl_dag.py
│   ├── neo4j_kg_rebuild_dag.py
│   └── log_cleanup_dag.py
│
├── modules/                        # Python 모듈
│   ├── common/                     # 공통 유틸리티
│   │   ├── logging_config.py
│   │   ├── airflow_settings.py
│   │   └── db_connections.py
│   ├── report_crawler/             # 금융 리포트 크롤러
│   │   └── stock_report_crawler.py
│   ├── company_crawler/            # 기업 데이터 크롤러
│   │   └── compete_company_crawler.py
│   ├── stock_price/                # 주가 ETL
│   │   ├── stock_to_db.py
│   │   └── fetch_stock_operators.py
│   ├── dart_disclosure/            # DART API 통합
│   │   ├── runner.py
│   │   ├── opendart_api.py
│   │   ├── llm_extractor.py
│   │   ├── mongo_repo.py
│   │   └── universe.py
│   ├── postgres/                   # PostgreSQL 커넥터
│   │   └── postgres_connector.py
│   ├── neo4j/                      # Neo4j 오퍼레이터
│   │   └── neo4j_operators.py
│   └── api/                        # API 유틸리티
│       └── data_validator.py
│
├── scripts/                        # 배포 및 유지보수 스크립트
│   ├── deploy.sh
│   ├── stop.sh
│   ├── bootstrap_airflow.sh
│   ├── setup_network.sh
│   ├── cleanup_logs.sh
│   └── smoke_test_dart_disclosure.py
│
├── config/                         # 설정 파일
│   └── airflow.cfg
│
├── data/                          # 데이터 저장소 (마운트 볼륨)
├── docker-compose.yml             # Docker 오케스트레이션
├── Dockerfile                     # 컨테이너 이미지 정의
├── requirements.txt               # Python 의존성
├── .env.example                   # 환경 변수 템플릿
└── README.md                      # 이 파일
```

## DAG 개요

### 데이터 수집 DAG

#### 1. stock_report_crawler_dag
- **스케줄**: 매일 00:00 UTC
- **목적**: 한국 금융 플랫폼에서 금융 리포트 크롤링
- **기술**: Selenium 기반 웹 스크래핑
- **출력**: MongoDB `stock_reports` 컬렉션
- **작업**:
  1. MongoDB 연결 체크
  2. 헤드리스 Chrome으로 리포트 크롤링
  3. 결과 리포트 및 검증

#### 2. competitor_crawler_dag
- **스케줄**: 매일 00:00 UTC
- **목적**: Wisereport에서 경쟁사 정보 수집
- **데이터 소스**: KOSPI, KOSDAQ, KONEX 시장 구분
- **출력**: MongoDB `competitors` 컬렉션
- **방법**: REST API 통합

#### 3. stock_to_postgres_dag
- **스케줄**: @daily
- **목적**: KRX에서 일일 주가 데이터 가져오기 및 저장
- **데이터 소스**: FinanceDataReader (KRX API)
- **출력**: PostgreSQL `daily_stock_price` 테이블
- **작업**:
  1. 테이블 스키마 생성 확인
  2. 주식 심볼 유니버스 업데이트
  3. 일일 가격 데이터 가져오기
  4. PostgreSQL에 upsert 로직으로 로드

### DART 공시 DAG

#### 4. dart_disclosure_collection_dag
- **스케줄**: 매일 08:00 KST
- **목적**: DART에서 36개 주요 공시 유형 수집
- **데이터 소스**: OpenDART API
- **출력**: PostgreSQL `dart_*` 테이블 (공시 유형별 1개)
- **기능**:
  - 엄선된 주요 리포트 엔드포인트
  - API 키 로테이션 지원
  - 자동 커서 관리
  - 대용량 데이터셋을 위한 청크 처리
- **참고**: 2025-01-06 기준 LLM 기반 이벤트 추출은 보류됨

#### 5. dart_disclosure_collection_backfill_dag
- **스케줄**: 수동 트리거
- **목적**: DART 공시 과거 데이터 백필
- **사용 사례**: 초기 데이터 로드 또는 누락 구간 채우기

### 인프라 DAG

#### 6. log_cleanup_dag
- **스케줄**: 매일 02:00 UTC
- **목적**: 7일 이상 된 Airflow 로그 자동 정리
- **작업**:
  1. 정리 전 통계
  2. 로그 파일 삭제
  3. 정리 후 통계

### 지식 그래프 DAG

#### 7. neo4j_kg_etl_dag
- **스케줄**: 매일 20:10 KST (주가 수집 완료 후)
- **목적**: Neo4j 지식 그래프 구축 및 업데이트
- **아키텍처**: 날짜 기반 허브 모델
- **데이터 소스**:
  - PostgreSQL `daily_stock_price`
  - PostgreSQL `dart_*` 테이블
- **작업**:
  1. 기본 KG 스키마 생성 (제약조건, 인덱스)
  2. 증분 로드를 위한 대상 날짜 결정
  3. 일일 주가 로드
  4. DART 공시 이벤트 로드
  5. 경쟁사 관계 로드 (MongoDB에서)

#### 8. neo4j_kg_rebuild_dag
- **스케줄**: 수동 트리거
- **목적**: Neo4j 지식 그래프 전체 재구축
- **사용 사례**: 스키마 변경 또는 데이터 손상 복구

## 설치

### 사전 요구사항

- Docker & Docker Compose
- Git
- Docker에 최소 4GB RAM 할당
- 다음에 대한 네트워크 액세스:
  - KRX 데이터 소스
  - DART OpenAPI (api.opendart.fsk.or.kr)
  - MongoDB Atlas (클라우드 MongoDB 사용 시)

### 빠른 시작 (Docker - 권장)

1. **저장소 클론**
   ```bash
   cd /path/to/your/workspace
   git clone <repository-url> stockelper-airflow
   cd stockelper-airflow
   ```

2. **환경 변수 설정**
   ```bash
   cp .env.example .env
   ```

   `.env` 파일을 편집하여 설정:
   ```bash
   # MongoDB 연결
   MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/
   MONGO_DATABASE=stockelper

   # PostgreSQL 연결
   POSTGRES_HOST=stockelper-postgresql
   POSTGRES_PORT=5432
   POSTGRES_USER=stockelper
   POSTGRES_PASSWORD=your_secure_password
   POSTGRES_DB=postgres

   # Airflow 보안
   AIRFLOW_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
   AIRFLOW_ADMIN_USERNAME=admin
   AIRFLOW_ADMIN_PASSWORD=change_this_password
   AIRFLOW_ADMIN_EMAIL=admin@yourdomain.com

   # DART API
   OPEN_DART_API_KEY=your_dart_api_key_here

   # Neo4j (선택사항)
   NEO4J_HOST=stockelper-neo4j
   NEO4J_PORT=7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=your_neo4j_password
   ```

3. **Docker 네트워크 생성**
   ```bash
   ./scripts/setup_network.sh
   ```

4. **Docker Compose로 배포**
   ```bash
   ./scripts/deploy.sh
   ```

5. **Airflow UI 접속**
   - URL: http://localhost:21003
   - 사용자명: admin (또는 설정한 값)
   - 비밀번호: admin (또는 설정한 값)

6. **설치 확인**
   ```bash
   docker logs stockelper-airflow
   ```

### 수동 설치 (개발용)

1. **가상 환경 생성**
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

2. **의존성 설치**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **데이터베이스 설정**
   - PostgreSQL 및 MongoDB 인스턴스 시작
   - `.env`에서 연결 문자열 설정

4. **Airflow 초기화**
   ```bash
   export AIRFLOW_HOME=$(pwd)
   airflow db init
   ```

5. **관리자 사용자 생성**
   ```bash
   airflow users create \
     --username admin \
     --password admin \
     --firstname Admin \
     --lastname User \
     --role Admin \
     --email admin@stockelper.com
   ```

6. **Airflow 서비스 시작**
   ```bash
   # 터미널 1: 스케줄러 시작
   airflow scheduler

   # 터미널 2: 웹서버 시작
   airflow webserver --port 8080
   ```

7. **Airflow UI 접속**
   - URL: http://localhost:8080

## 설정

### 환경 변수

| 변수 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `MONGODB_URI` | 예 | - | MongoDB 연결 문자열 |
| `MONGO_DATABASE` | 예 | `stockelper` | MongoDB 데이터베이스 이름 |
| `POSTGRES_HOST` | 예 | `stockelper-postgresql` | PostgreSQL 호스트 |
| `POSTGRES_PORT` | 아니오 | `5432` | PostgreSQL 포트 |
| `POSTGRES_USER` | 예 | `stockelper` | PostgreSQL 사용자명 |
| `POSTGRES_PASSWORD` | 예 | - | PostgreSQL 비밀번호 |
| `POSTGRES_DB` | 아니오 | `postgres` | PostgreSQL 데이터베이스 이름 |
| `AIRFLOW_SECRET_KEY` | 예 | - | Airflow 웹 서버 비밀 키 |
| `AIRFLOW_ADMIN_USERNAME` | 아니오 | `admin` | 초기 관리자 사용자명 |
| `AIRFLOW_ADMIN_PASSWORD` | 아니오 | `admin` | 초기 관리자 비밀번호 |
| `AIRFLOW_ADMIN_EMAIL` | 아니오 | `admin@stockelper.com` | 관리자 이메일 주소 |
| `OPEN_DART_API_KEY` | 예 | - | DART OpenAPI 키 |
| `DART36_LOOKBACK_DAYS` | 아니오 | `30` | DART 수집 조회 기간 |
| `DART36_SLEEP_SECONDS` | 아니오 | `0.2` | DART API 호출 간 지연 시간 |
| `DART36_TIMEOUT_SECONDS` | 아니오 | `30` | DART API 요청 타임아웃 |
| `DART36_MAX_RETRIES` | 아니오 | `3` | DART API 호출 최대 재시도 횟수 |
| `STOCK_PRICE_EOD_CUTOFF_HOUR` | 아니오 | `18` | 장 마감 기준 시간 (KST) |
| `NEO4J_HOST` | 아니오 | `stockelper-neo4j` | Neo4j 호스트 |
| `NEO4J_PORT` | 아니오 | `7687` | Neo4j bolt 포트 |
| `NEO4J_USER` | 아니오 | `neo4j` | Neo4j 사용자명 |
| `NEO4J_PASSWORD` | 아니오 | - | Neo4j 비밀번호 |

### Airflow 연결

다음 Airflow 연결은 부트스트랩 스크립트에 의해 자동으로 생성됩니다:

- **postgres_default**: 주식 데이터를 위한 PostgreSQL 연결
- **neo4j_default**: 지식 그래프를 위한 Neo4j 연결

### Airflow 변수

Airflow UI (Admin > Variables)에서 다음을 설정하세요:

- `OPEN_DART_API_KEY`: DART API 키
- `DART_CURATED_UNIVERSE_JSON`: 유니버스 JSON 파일 경로
- `DART_CURATED_LOOKBACK_DAYS`: DART 데이터 조회 일수

## 데이터베이스 스키마

### PostgreSQL

#### daily_stock_price
```sql
CREATE TABLE daily_stock_price (
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(15, 2),
    high DECIMAL(15, 2),
    low DECIMAL(15, 2),
    close DECIMAL(15, 2),
    volume BIGINT,
    adjusted_close DECIMAL(15, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);
```

#### dart_* 테이블
각 DART 공시 유형별로 다음 패턴을 따르는 여러 테이블:
```sql
CREATE TABLE dart_{report_type} (
    rcept_no VARCHAR(50) PRIMARY KEY,
    corp_code VARCHAR(8),
    corp_name VARCHAR(255),
    stock_code VARCHAR(6),
    report_nm VARCHAR(255),
    rcept_dt DATE,
    flr_nm VARCHAR(255),
    -- 리포트 유형별 추가 필드
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### MongoDB

#### stock_reports
```javascript
{
    _id: ObjectId,
    date: ISODate,
    company: String,
    code: String,
    title: String,
    summary: String,
    url: String,
    crawled_at: ISODate
}
// 인덱스: { date: 1, company: 1, code: 1 }
```

#### competitors
```javascript
{
    _id: String,  // 기업 코드
    target_company: String,
    competitors: [
        {
            name: String,
            code: String,
            similarity_score: Number
        }
    ],
    last_crawled_at: ISODate
}
```

### Neo4j 지식 그래프

#### 노드 레이블
- `Date`: 날짜 허브 노드 (YYYY-MM-DD)
- `Company`: 주식 심볼/기업
- `Event`: DART 공시 이벤트
- `Sector`: 산업 섹터

#### 관계 타입
- `HAS_PRICE`: Company -> Date (주가 데이터)
- `HAS_EVENT`: Company -> Event -> Date
- `COMPETES_WITH`: Company -> Company
- `BELONGS_TO`: Company -> Sector

## 사용법

### 파이프라인 시작

1. **Airflow UI에서 DAG 활성화**
   - http://localhost:21003 으로 이동
   - DAG를 "On" 상태로 토글

2. **수동 실행 (선택사항)**
   - DAG 이름 클릭
   - "Trigger DAG" 버튼 클릭

3. **실행 모니터링**
   - Airflow UI에서 로그 확인
   - 작업 상태 및 실행 시간 확인

### 백필 실행

DART 과거 데이터를 백필하려면:

1. `dart_disclosure_collection_backfill_dag`로 이동
2. "Trigger DAG w/ config" 클릭
3. 설정 제공:
   ```json
   {
     "start_date": "2024-01-01",
     "end_date": "2024-12-31"
   }
   ```

### 모니터링

#### Airflow UI
- DAG 실행 이력: http://localhost:21003/dags
- 작업 로그: 작업 인스턴스 클릭 -> View Log
- 작업 실행 시간: Graph View에서 실행 시간 표시

#### 데이터베이스 쿼리

최근 주가 확인:
```sql
SELECT * FROM daily_stock_price
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY date DESC, symbol
LIMIT 100;
```

DART 공시 확인:
```sql
SELECT report_nm, COUNT(*) as count
FROM dart_major_reports
WHERE rcept_dt >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY report_nm
ORDER BY count DESC;
```

#### Neo4j 쿼리

지식 그래프 검증:
```cypher
// 레이블별 노드 수
MATCH (n) RETURN labels(n) AS label, COUNT(*) AS count

// 최근 주가
MATCH (c:Company)-[r:HAS_PRICE]->(d:Date)
WHERE d.date >= date() - duration('P7D')
RETURN c.symbol, d.date, r.close
ORDER BY d.date DESC, c.symbol
LIMIT 100
```

## 유지보수

### 로그 정리

로그는 `log_cleanup_dag`에 의해 자동으로 정리됩니다 (매일 02:00 UTC 실행). 수동 정리:

```bash
# 컨테이너 내부
docker exec stockelper-airflow bash /opt/airflow/scripts/cleanup_logs.sh

# 호스트에서
./scripts/cleanup_logs_container.sh
```

### 데이터베이스 유지보수

PostgreSQL vacuum 및 analyze:
```sql
VACUUM ANALYZE daily_stock_price;
VACUUM ANALYZE dart_major_reports;
```

MongoDB 인덱스 최적화:
```javascript
db.stock_reports.reIndex();
db.competitors.reIndex();
```

### DAG 업데이트

1. **DAG 파일 수정**
   ```bash
   # DAG는 ./dags 디렉토리에서 마운트됨
   vim dags/my_custom_dag.py
   ```

2. **Airflow 자동 변경 감지**
   - 30-60초 대기하여 Airflow가 새로고침
   - 또는 즉시 업데이트를 위해 스케줄러 재시작

3. **Airflow 재시작 (필요시)**
   ```bash
   docker-compose restart airflow
   ```

## 문제 해결

### 일반적인 문제

#### MongoDB 연결 실패
```
Error: MongoServerError: Authentication failed
```
**해결책**:
- `MONGODB_URI`가 올바른지 확인
- MongoDB Atlas IP 화이트리스트 확인
- 네트워크 연결 확인

#### PostgreSQL 연결 실패
```
Error: could not connect to server
```
**해결책**:
- PostgreSQL 컨테이너가 실행 중인지 확인: `docker ps | grep postgres`
- `POSTGRES_*` 환경 변수 확인
- 네트워크 확인: `docker network inspect stockelper`

#### Selenium WebDriver 오류
```
Error: selenium.common.exceptions.WebDriverException: Message: unknown error: Chrome failed to start
```
**해결책**:
- Chrome/ChromeDriver는 Docker 이미지에 사전 설치됨
- 충분한 메모리 확보 (Docker에 4GB 이상)
- 로그 확인: `docker logs stockelper-airflow`

#### DAG가 UI에 표시되지 않음
```
DAG 파일이 Airflow UI에 표시되지 않음
```
**해결책**:
- Python 구문 오류 확인: `python dags/my_dag.py`
- 파일이 `./dags` 디렉토리에 있는지 확인
- 스케줄러 로그 확인: `docker logs stockelper-airflow | grep scheduler`
- DAG 새로고침: Admin > Reload DAGs

#### 포트가 이미 사용 중
```
Error: Bind for 0.0.0.0:21003 failed: port is already allocated
```
**해결책**:
- `docker-compose.yml`에서 포트 변경:
  ```yaml
  ports:
    - "21004:8080"  # 21003을 사용 가능한 포트로 변경
  ```

#### 메모리 부족
```
Error: MemoryError or container killed
```
**해결책**:
- Docker 메모리 제한 증가 (Docker Desktop > Settings > Resources)
- 동시 작업 수 줄이기: `airflow.cfg` 편집 -> `parallelism = 4`

### 디버그 모드

디버그 로깅 활성화:

1. **환경 변수**
   ```bash
   # docker-compose.yml에서
   - AIRFLOW__CORE__LOGGING_LEVEL=DEBUG
   ```

2. **서비스 재시작**
   ```bash
   docker-compose restart airflow
   ```

3. **로그 확인**
   ```bash
   docker logs -f stockelper-airflow
   ```

### 상태 확인

Airflow 상태 엔드포인트:
```bash
curl http://localhost:21003/health
```

데이터베이스 연결 테스트:
```bash
# PostgreSQL
docker exec stockelper-postgresql psql -U stockelper -c "SELECT 1"

# MongoDB
docker exec stockelper-airflow python -c "from pymongo import MongoClient; print(MongoClient('$MONGODB_URI').server_info())"
```

## 개발

### 새로운 DAG 추가

1. **DAG 파일 생성**
   ```python
   # dags/my_new_dag.py
   from airflow import DAG
   from airflow.operators.python import PythonOperator
   import pendulum

   def my_task():
       print("Hello from my task")

   with DAG(
       dag_id="my_new_dag",
       start_date=pendulum.datetime(2025, 1, 1, tz="Asia/Seoul"),
       schedule="@daily",
       catchup=False,
   ) as dag:
       task = PythonOperator(
           task_id="my_task",
           python_callable=my_task,
       )
   ```

2. **버전 관리에 추가**
   ```bash
   git add dags/my_new_dag.py
   git commit -m "Add new DAG for [목적]"
   ```

3. **로컬 테스트**
   ```bash
   # DAG 검증
   python dags/my_new_dag.py

   # 작업 테스트
   airflow tasks test my_new_dag my_task 2025-01-01
   ```

### 테스트

단위 테스트 실행:
```bash
pytest tests/
```

DART 수집 스모크 테스트 실행:
```bash
python scripts/smoke_test_dart_disclosure.py
```

### 기여

1. 저장소 포크
2. 기능 브랜치 생성: `git checkout -b feature/my-feature`
3. 변경사항 커밋: `git commit -am 'Add new feature'`
4. 브랜치에 푸시: `git push origin feature/my-feature`
5. Pull Request 생성

## 프로덕션 배포

### 권장 설정

1. **외부 데이터베이스 사용**
   - 관리형 PostgreSQL (AWS RDS, GCP Cloud SQL)
   - MongoDB Atlas
   - Neo4j AuraDB

2. **인증 활성화**
   ```bash
   # 강력한 비밀번호
   AIRFLOW_ADMIN_PASSWORD=$(openssl rand -base64 32)
   AIRFLOW_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
   ```

3. **백업 구성**
   - PostgreSQL: 30일 보관 기간의 일일 백업
   - MongoDB: 특정 시점 복구 활성화
   - Airflow 로그: S3/GCS에 아카이브

4. **병렬 처리를 위한 CeleryExecutor 사용**
   ```yaml
   environment:
     - AIRFLOW__CORE__EXECUTOR=CeleryExecutor
   ```

5. **모니터링 설정**
   - 메트릭을 위한 Prometheus + Grafana
   - Airflow StatsD 통합
   - 데이터베이스 성능 모니터링

6. **HTTPS 활성화**
   - 리버스 프록시 사용 (nginx, traefik)
   - SSL/TLS 인증서 (Let's Encrypt)

## API 액세스

### Airflow REST API

`airflow.cfg`에서 실험적 API 활성화:
```ini
[api]
auth_backend = airflow.api.auth.backend.basic_auth
```

예제: API를 통한 DAG 트리거
```bash
curl -X POST \
  http://localhost:21003/api/v1/dags/stock_to_postgres_dag/dagRuns \
  -H 'Content-Type: application/json' \
  -u admin:admin \
  -d '{}'
```

## 성능 최적화

### 데이터베이스 인덱싱

인덱스 존재 확인:
```sql
-- PostgreSQL
CREATE INDEX idx_stock_price_date ON daily_stock_price(date);
CREATE INDEX idx_stock_price_symbol ON daily_stock_price(symbol);
CREATE INDEX idx_dart_rcept_dt ON dart_major_reports(rcept_dt);
```

### DAG 최적화

- 독립적인 실행을 위해 `depends_on_past=False` 설정
- 동시 실행 방지를 위해 `max_active_runs=1` 사용
- 리소스 집약적 작업에 `pool` 구현

### Airflow 설정

`config/airflow.cfg`의 주요 설정:
```ini
[core]
parallelism = 32
dag_concurrency = 16
max_active_runs_per_dag = 1

[scheduler]
scheduler_heartbeat_sec = 5
min_file_process_interval = 30
```

## 보안 모범 사례

1. **비밀 정보 커밋 금지**
   - `.env` 파일 사용 (gitignore됨)
   - 또는 환경 변수
   - 또는 Airflow Variables (암호화됨)

2. **네트워크 액세스 제한**
   - 데이터베이스 포트에 대한 방화벽 규칙
   - 데이터베이스 액세스를 위한 VPN/VPC

3. **정기적 업데이트**
   ```bash
   pip install --upgrade apache-airflow
   docker-compose pull
   ```

4. **감사 로깅**
   - Airflow 감사 로그 활성화
   - 로그인 실패 시도 모니터링

## 라이선스

MIT License - 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

Copyright (c) 2025 Stockelper-Lab

## 지원

- **이슈**: [GitHub Issues](https://github.com/stockelper-lab/stockelper-airflow/issues)
- **문서**: `docs/` 디렉토리 참조
- **이메일**: admin@stockelper.com

## 감사의 글

- Apache Airflow 커뮤니티
- OpenDART API
- FinanceDataReader 라이브러리
- 한국 금융 데이터 제공자

## 변경 이력

### 2025-01-10
- 포괄적인 문서로 README 개선
- 문제 해결 섹션 추가
- 설정 예제 확장

### 2025-01-06
- LLM 기반 이벤트 추출 보류
- DART 수집을 주요 리포트 유형을 이벤트로 사용하도록 업데이트
- 지식 그래프 ETL 파이프라인 단순화

### 2025-01-03
- Neo4j 지식 그래프 통합 추가
- 엄선된 DART 주요 리포트 수집 구현
- Docker 배포 스크립트 개선

### 2024-12-31
- 초기 릴리스
- 주가 및 DART 수집을 위한 핵심 DAG
- MongoDB 및 PostgreSQL 통합
