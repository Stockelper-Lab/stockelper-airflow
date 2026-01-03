# Stockelper Airflow DAGs

Apache Airflow 기반 데이터 수집 및 처리 파이프라인입니다.

## 🏗️ 주요 DAG

### 데이터 수집

**1. stock_report_crawler_dag.py**
- 스케줄: 매일 00:00 UTC
- 목적: 금융 리포트 크롤링 → MongoDB
- 태스크: MongoDB 연결 체크 → 크롤링 → 결과 리포트

**2. competitor_crawler_dag.py**
- 스케줄: 매일 00:00 UTC
- 목적: Wisereport에서 경쟁사 정보 수집 → MongoDB
- 데이터 소스: KOSPI/KOSDAQ/KONEX

**3. stock_to_postgres_dag.py**
- 스케줄: @daily
- 목적: KRX 일일 주가 데이터 → PostgreSQL
- 태스크: 테이블 생성 → 심볼 업데이트 → 데이터 페치 → PostgreSQL 로드

### DART 공시 수집

**4. dart_disclosure_collection_dag.py**
- 스케줄: 매일 08:00 KST
- 목적: DART 36개 주요 공시 유형 수집 → PostgreSQL
- 태스크: 유니버스 로드 → 36개 보고서 수집 → 이벤트 추출 (LLM)

**5. dart_disclosure_collection_backfill_dag.py**
- 스케줄: 수동
- 목적: DART 과거 데이터 백필

**6. dart_event_extraction_backfill_dag.py**
- 스케줄: 수동
- 목적: 유니버스 종목 이벤트/감정 추출 (20년 백필 이후)

### 유지보수 & 지식 그래프

**7. log_cleanup_dag.py**
- 스케줄: 매일 02:00 UTC
- 목적: 7일 이상 된 Airflow 로그 자동 삭제
- 태스크: 로그 통계 → 정리 → 정리 후 통계

**8. neo4j_kg_etl_dag.py**
- 스케줄: @daily
- 목적: Neo4j 지식 그래프 구축 및 업데이트
- 태스크: 기본 데이터 생성 → 데이터 추출 → Neo4j 로드

## 📁 모듈 구조

### Common (`modules/common/`)
- `logging_config.py` - 통합 로깅
- `airflow_settings.py` - 설정 관리
- `db_connections.py` - DB 연결

### Crawlers (`modules/*/`)
- `stock_report_crawler.py` - Selenium 기반 리포트 크롤러
- `compete_company_crawler.py` - REST API 경쟁사 크롤러

### DART (`modules/dart_disclosure/`)
- `runner.py` - DART 수집 오케스트레이션
- `opendart_api.py` - OpenDART API 클라이언트
- `llm_extractor.py` - OpenAI 이벤트 추출
- `mongo_repo.py` - MongoDB 저장소
- `universe.py` - 유니버스 관리

### Database (`modules/postgres/`, `modules/neo4j/`)
- `postgres_connector.py` - PostgreSQL 엔진
- `neo4j_operators.py` - Neo4j 오퍼레이터

### Stock Price (`modules/stock_price/`)
- `stock_to_db.py` - 주가 ETL
- `fetch_stock_operators.py` - 배치 오퍼레이터

## ⚙️ 환경 변수

```bash
# MongoDB
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGO_DATABASE=stockelper

# Airflow 보안
AIRFLOW_SECRET_KEY=
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=admin
AIRFLOW_ADMIN_EMAIL=admin@stockelper.com

# Neo4j (선택)
NEO4J_URI=bolt://stockelper-neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=

# PostgreSQL
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql://user:pass@host:5432/db

# DART
OPEN_DART_API_KEY=
DART36_LOOKBACK_DAYS=30
DART36_SLEEP_SECONDS=0.2
DART36_TIMEOUT_SECONDS=30
DART36_MAX_RETRIES=3
DART36_UNIVERSE_JSON=/opt/airflow/stockelper-kg/modules/dart_disclosure/universe.ai-sector.template.json

# 주가 수집
STOCK_PRICE_EOD_CUTOFF_HOUR=18
```

## 🚀 빠른 시작

### Docker로 배포 (권장)

```bash
# 1. .env 파일 생성
cp .env.example .env
# .env 수정

# 2. 배포
./scripts/deploy.sh

# 3. Airflow UI 접속
# http://localhost:21003
# 기본 로그인: admin / admin
```

### 수동 설치

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. MongoDB 설정
# MongoDB 실행 및 환경변수 설정

# 3. Airflow 초기화
export AIRFLOW_HOME=$(pwd)
airflow db init
airflow users create   --username admin   --password admin   --firstname Admin   --lastname User   --role Admin   --email admin@stockelper.com

# 4. Airflow 실행
airflow scheduler &    # 터미널 1
airflow webserver --port 8080  # 터미널 2
```

## 🐳 Docker 설정

### 포트
- Airflow Web UI: 21003

### 네트워크
- 네트워크: stockelper (bridge)

### 볼륨
- `airflow_logs` - 로그 저장
- `./dags` - DAG 정의 (읽기/쓰기)
- `./modules` - Python 모듈 (읽기/쓰기)
- `../stockelper-kg` - KG 레포 (읽기 전용)

### 헬스체크
- 엔드포인트: http://localhost:8080/health
- 간격: 30초

## 📊 데이터베이스 스키마

### MongoDB 컬렉션

**stock_reports**
- date, company, code, title, summary, url, crawled_at
- 인덱스: (date, company, code) 복합

**competitors**
- _id (기업 코드), target_company, competitors, last_crawled_at

### PostgreSQL 테이블

**daily_stock_price**
- symbol, date, open, high, low, close, volume, adjusted_close

**dart_major_reports**
- 36개 DART 공시 유형 데이터

**dart_event_extractions**
- LLM 추출 이벤트 + 감정 점수

## 🔧 문제 해결

### MongoDB 연결 실패
- `MONGODB_URI` 환경변수 확인

### Selenium WebDriver 오류
- Chrome/ChromeDriver 버전 확인 (Docker 이미지 자동 설치)

### DAG가 표시되지 않음
- `./dags` 폴더 권한 확인
- Airflow scheduler 로그 확인

### 포트 충돌
- `docker-compose.yml`에서 포트 변경

## 📚 문서

- [QUICKSTART.md](docs/QUICKSTART.md) - 빠른 시작
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) - 문제 해결
- [LOGGING_GUIDE.md](docs/LOGGING_GUIDE.md) - 로깅 가이드
- [ADMIN_USER_SETUP.md](docs/ADMIN_USER_SETUP.md) - 관리자 설정

## 📄 라이선스

MIT License
