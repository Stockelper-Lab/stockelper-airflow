# Stockelper Airflow 배포 가이드

## 🚀 빠른 시작

### 1. 사전 요구사항

- Docker 및 Docker Compose 설치
- MongoDB 접속 정보 (URI)
- 최소 2GB RAM, 10GB 디스크 공간

### 2. 환경 설정

`.env` 파일을 생성하고 다음 정보를 입력하세요:

```bash
# MongoDB 설정
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/
MONGO_DATABASE=stockelper

# Airflow 관리자 계정
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=your_secure_password
AIRFLOW_ADMIN_EMAIL=admin@example.com

# Airflow Secret Key (랜덤 문자열)
AIRFLOW_SECRET_KEY=your_random_secret_key_here
```

### 3. 배포 실행

```bash
# 배포 스크립트 실행
./scripts/deploy.sh
```

또는 수동으로:

```bash
# Docker 네트워크 생성
docker network create stockelper

# 이미지 빌드
docker compose build

# 컨테이너 시작
docker compose up -d

# 로그 확인
docker compose logs -f
```

### 4. 접속 확인

- **Airflow Web UI**: http://localhost:21003
- **기본 계정**: admin / admin (`.env`에서 변경 가능)

## 📋 주요 DAG

### Stock Report Crawler
- **스케줄**: 매일 UTC 00:00 (한국 시간 09:00)
- **기능**: fnguide.com에서 주식 리포트 크롤링
- **저장소**: MongoDB `report` 컬렉션

### Competitor Crawler
- **스케줄**: 매일 UTC 00:00
- **기능**: Wisereport에서 경쟁사 정보 크롤링
- **저장소**: MongoDB `competitors` 컬렉션

### Log Cleanup
- **스케줄**: 매일 UTC 18:00 (한국 시간 03:00)
- **기능**: 30일 이상 된 로그 파일 자동 삭제

## 🔧 문제 해결

### ChromeDriver 버전 불일치

**증상**: `This version of ChromeDriver only supports Chrome version XXX`

**해결**: Dockerfile이 자동으로 Chrome 버전에 맞는 ChromeDriver를 설치하도록 수정되었습니다. 이미지를 다시 빌드하세요:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

### MongoDB 연결 실패

**증상**: `Failed to connect to MongoDB`

**확인 사항**:
1. `.env` 파일의 `MONGODB_URI`가 올바른지 확인
2. MongoDB 서버가 실행 중인지 확인
3. 네트워크 방화벽 설정 확인

```bash
# MongoDB 연결 테스트
docker exec stockelper-airflow python -c "
from pymongo import MongoClient
import os
client = MongoClient(os.environ['MONGODB_URI'], serverSelectionTimeoutMS=5000)
print('✓ MongoDB connection successful')
print(f'Databases: {client.list_database_names()}')
"
```

### DAG가 로드되지 않음

**확인**:
```bash
# DAG 목록 확인
docker exec stockelper-airflow airflow dags list

# DAG 상세 정보 확인
docker exec stockelper-airflow airflow dags show stock_report_crawler
```

## 🧪 테스트

### Stock Report Crawler 테스트

```bash
# 수동 실행
docker exec stockelper-airflow airflow dags test stock_report_crawler $(date +%Y-%m-%d)

# MongoDB에 데이터 확인
docker exec stockelper-airflow python -c "
from pymongo import MongoClient
import os
client = MongoClient(os.environ['MONGODB_URI'])
db = client[os.environ['MONGO_DATABASE']]
count = db['report'].count_documents({})
print(f'Total reports: {count}')
"
```

### Competitor Crawler 테스트

```bash
# 수동 실행
docker exec stockelper-airflow airflow dags test competitor_crawler $(date +%Y-%m-%d)

# MongoDB에 데이터 확인
docker exec stockelper-airflow python -c "
from pymongo import MongoClient
import os
client = MongoClient(os.environ['MONGODB_URI'])
db = client[os.environ['MONGO_DATABASE']]
count = db['competitors'].count_documents({})
print(f'Total competitors: {count}')
"
```

## 🔄 업데이트 및 재배포

코드 변경 후 재배포:

```bash
# 컨테이너 중지
docker compose down

# 이미지 재빌드
docker compose build

# 컨테이너 재시작
docker compose up -d
```

## 📊 모니터링

### 로그 확인

```bash
# 전체 로그
docker compose logs -f

# 특정 시간대 로그
docker compose logs --since 1h

# 에러 로그만
docker compose logs | grep ERROR
```

### 컨테이너 상태 확인

```bash
# 컨테이너 상태
docker compose ps

# 리소스 사용량
docker stats stockelper-airflow
```

### DAG 실행 이력

```bash
# 최근 실행 이력
docker exec stockelper-airflow airflow dags list-runs -d stock_report_crawler

# 실패한 작업 확인
docker exec stockelper-airflow airflow tasks list stock_report_crawler --tree
```

## 🛑 서비스 중지

```bash
# 컨테이너 중지 (데이터 유지)
docker compose stop

# 컨테이너 삭제 (데이터 유지)
docker compose down

# 컨테이너 및 볼륨 삭제 (데이터 삭제)
docker compose down -v
```

## 📝 주요 변경 사항

### 2025-10-13
- ✅ Stock Report Crawler 수정 (mongo_database 파라미터 추가)
- ✅ ChromeDriver 자동 버전 매칭 구현
- ✅ PyMongo Collection bool 체크 수정
- ✅ 날짜 형식 유연하게 처리 (YYYY-MM-DD, YYYY/MM/DD 모두 지원)

자세한 변경 사항은 [CHANGELOG.md](CHANGELOG.md)를 참조하세요.

## 🆘 지원

문제가 발생하면 다음을 확인하세요:
1. [CHANGELOG.md](CHANGELOG.md) - 최근 변경 사항
2. [README.md](README.md) - 프로젝트 개요
3. GitHub Issues - 알려진 문제 및 해결 방법
