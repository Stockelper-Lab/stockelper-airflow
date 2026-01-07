# 빠른 시작 가이드

Stockelper Airflow를 빠르게 시작하는 방법을 안내합니다.

## 📋 요구사항

- **Docker** 및 **Docker Compose** 설치
- **Git** 설치
- 최소 **4GB RAM** 및 **10GB 디스크 공간**

## 🚀 5분 안에 시작하기

### 1. 저장소 클론

```bash
git clone <repository-url>
cd stockelper-airflow
```

### 2. 환경 변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집
nano .env
```

**필수 설정**:
```bash
# MongoDB 설정
MONGODB_URI=mongodb+srv://stockelper:YOUR_PASSWORD@stockelper.btl2cdx.mongodb.net/
MONGO_DATABASE=stockelper

# Airflow Secret Key
AIRFLOW_SECRET_KEY=your-secure-secret-key-here

# Admin 계정 (선택사항)
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=your-secure-password
AIRFLOW_ADMIN_EMAIL=admin@stockelper.com

# Postgres (Airflow 메타DB + KG 적재 소스)
# - stockelper-postgresql 컨테이너를 재사용합니다.
# - AIRFLOW_META_DB_NAME: Airflow 메타DB(자동 생성됨)
POSTGRES_HOST=stockelper-postgresql
POSTGRES_PORT=5432
POSTGRES_USER=stockelper
POSTGRES_PASSWORD=your-postgres-password
POSTGRES_DB=postgres
AIRFLOW_META_DB_NAME=airflow_meta

# Neo4j (KG 타깃)
NEO4J_HOST=stockelper-neo4j
NEO4J_PORT=7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password
```

### 3. 배포

```bash
# 원클릭 배포
./scripts/deploy.sh
```

배포 스크립트가 자동으로:
- ✅ Docker 네트워크 생성
- ✅ Docker 이미지 빌드
- ✅ 컨테이너 시작
- ✅ 데이터베이스 초기화
- ✅ Admin 사용자 생성

### 4. 접속

**Airflow 웹 UI**:
- URL: http://localhost:21003
- 사용자명: `.env`에 설정한 값 (기본: `admin`)
- 비밀번호: `.env`에 설정한 값 (기본: `admin`)

## 🎯 첫 DAG 실행하기

### 1. DAG 활성화

1. Airflow UI 접속
2. DAG 목록에서 토글 스위치 클릭하여 활성화
   - `stock_report_crawler`
   - `competitor_crawler`
   - `log_cleanup`
   - `dart_disclosure_collection_curated_major_reports`

### 2. 수동 실행

1. DAG 이름 클릭
2. 우측 상단 **▶ Trigger DAG** 버튼 클릭
3. **Graph** 탭에서 실행 상태 확인

### 3. 로그 확인

1. Task 클릭
2. **Log** 탭 선택
3. 실시간 로그 확인

## 📊 사용 가능한 DAG

### 1. Stock Report Crawler
- **ID**: `stock_report_crawler`
- **스케줄**: 매일 00:00 UTC (09:00 KST)
- **목적**: 주식 리서치 리포트 크롤링

### 2. Competitor Crawler
- **ID**: `competitor_crawler`
- **스케줄**: 매일 00:00 UTC
- **목적**: 기업 경쟁사 정보 크롤링

### 3. Log Cleanup
- **ID**: `log_cleanup`
- **스케줄**: 매일 02:00 UTC
- **목적**: 오래된 로그 파일 정리

### 4. DART 공시(엄선된) 수집
- **ID**: `dart_disclosure_collection_curated_major_reports`
- **스케줄**: 매일 08:00 KST
- **목적**: OpenDART major-report 엔드포인트 중 엄선된 공시 유형 수집 → Postgres 적재

### 5. DART 공시(엄선된) 백필
- **ID**: `dart_disclosure_collection_curated_major_reports_backfill`
- **스케줄**: 매일 1회 (`@daily`)
- **목적**: 장기 기간(기본 20년) 범위 백필(청크 단위)

### 6. DART 이벤트/감성 추출 백필
- **ID**: `dart_event_extraction_universe_backfill`
- **스케줄**: 수동 (schedule=None)
- **목적**: 백필된 `dart_*` 테이블 기반으로 유니버스 종목 이벤트/감성 추출 재처리

## 🛠️ 기본 명령어

### 서비스 관리

```bash
# 서비스 시작
docker compose up -d

# 서비스 중지
docker compose down

# 서비스 재시작
docker compose restart

# 로그 확인
docker compose logs -f

# 특정 서비스 로그
docker compose logs -f airflow
```

### 컨테이너 접속

```bash
# Airflow 컨테이너 접속
docker exec -it stockelper-airflow bash

# Airflow CLI 사용
docker exec stockelper-airflow airflow dags list
docker exec stockelper-airflow airflow tasks list stock_report_crawler
```

### 데이터베이스 확인

```bash
# MongoDB 접속 (별도 MongoDB 컨테이너 사용 시)
docker exec -it stockelper-mongodb mongosh

# 데이터 확인
use stockelper
db.stock_reports.find().limit(5)
db.competitors.find().limit(5)
```

## 🔍 문제 해결

### 포트 충돌

**증상**: "port is already allocated" 에러

**해결**:
```bash
# 21003 포트 사용 중인 프로세스 확인
sudo lsof -i :21003

# 프로세스 종료 또는 .env에서 포트 변경
```

### MongoDB 연결 실패

**증상**: "MongoDB connection failed" 에러

**해결**:
1. `.env` 파일의 `MONGODB_URI` 확인
2. MongoDB 서버 상태 확인
3. 네트워크 연결 확인

```bash
# MongoDB 연결 테스트
docker exec stockelper-airflow python -c "from pymongo import MongoClient; client = MongoClient('$MONGODB_URI'); print(client.server_info())"
```

### 컨테이너가 시작되지 않음

**증상**: 컨테이너가 계속 재시작됨

**해결**:
```bash
# 로그 확인
docker logs stockelper-airflow

# 컨테이너 재빌드
docker compose down
docker compose build --no-cache
docker compose up -d
```

### DAG가 표시되지 않음

**증상**: Airflow UI에 DAG가 없음

**해결**:
```bash
# DAG 폴더 확인
docker exec stockelper-airflow ls -la /opt/airflow/dags

# DAG 파일 구문 오류 확인
docker exec stockelper-airflow airflow dags list-import-errors

# 스케줄러 재시작
docker compose restart
```

## 📚 다음 단계

### 학습 자료

1. **[Architecture](ARCHITECTURE.md)** - 시스템 아키텍처 이해
2. **[Development](DEVELOPMENT.md)** - 개발 환경 설정
3. **[Logging Guide](LOGGING_GUIDE.md)** - 로깅 시스템 사용법
4. **[Troubleshooting](TROUBLESHOOTING.md)** - 상세한 문제 해결

### 커스터마이징

1. **새 DAG 추가**
   - `dags/` 폴더에 새 파일 생성
   - [Development Guide](DEVELOPMENT.md) 참고

2. **크롤러 수정**
   - `modules/` 폴더의 크롤러 코드 수정
   - 테스트 후 컨테이너 재빌드

3. **스케줄 변경**
   - DAG 파일의 `schedule` 파라미터 수정
   - Cron 표현식 사용

## 🎓 유용한 팁

### 1. 개발 모드로 실행

```bash
# 로컬에서 DAG 테스트
docker exec stockelper-airflow airflow dags test stock_report_crawler 2025-10-12
```

### 2. 특정 Task만 실행

```bash
# Task 단위 테스트
docker exec stockelper-airflow airflow tasks test stock_report_crawler check_mongodb_connection 2025-10-12
```

### 3. 변수 설정

Airflow UI에서:
1. **Admin** → **Variables**
2. **+** 버튼으로 새 변수 추가
3. DAG에서 `Variable.get("key")` 로 사용

### 4. 연결 설정

Airflow UI에서:
1. **Admin** → **Connections**
2. **+** 버튼으로 새 연결 추가
3. MongoDB, HTTP 등 다양한 연결 타입 지원

## 🆘 도움말

- **이슈 보고**: GitHub Issues
- **문서**: `docs/` 폴더의 상세 가이드
- **로그**: `docker compose logs -f`

---