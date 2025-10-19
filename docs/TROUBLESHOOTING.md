# 문제 해결 가이드

Stockelper Airflow 사용 중 발생할 수 있는 문제와 해결 방법을 안내합니다.

## 📋 목차

- [설치 및 배포 문제](#설치-및-배포-문제)
- [Docker 관련 문제](#docker-관련-문제)
- [MongoDB 연결 문제](#mongodb-연결-문제)
- [DAG 관련 문제](#dag-관련-문제)
- [크롤링 문제](#크롤링-문제)
- [로그 관련 문제](#로그-관련-문제)
- [성능 문제](#성능-문제)

---

## 설치 및 배포 문제

### ❌ 포트 충돌 오류

**증상**:
```
Error: port is already allocated
Bind for 0.0.0.0:21003 failed: port is already allocated
```

**원인**: 21003 포트가 이미 사용 중

**해결 방법**:

```bash
# 1. 포트 사용 중인 프로세스 확인
sudo lsof -i :21003

# 2. 프로세스 종료
sudo kill -9 <PID>

# 또는 .env 파일에서 포트 변경
# AIRFLOW__WEBSERVER__WEB_SERVER_PORT=21004
```

### ❌ 네트워크 생성 실패

**증상**:
```
Error: network stockelper not found
```

**원인**: Docker 네트워크가 생성되지 않음

**해결 방법**:

```bash
# 네트워크 수동 생성
docker network create stockelper

# 또는 setup 스크립트 실행
./scripts/setup_network.sh
```

### ❌ 환경 변수 누락

**증상**:
```
ValueError: MONGODB_URI environment variable is required
```

**원인**: `.env` 파일이 없거나 필수 변수 누락

**해결 방법**:

```bash
# .env 파일 생성
cp .env.example .env

# 필수 변수 설정
nano .env

# 최소 필수 변수:
# MONGODB_URI=mongodb+srv://...
# MONGO_DATABASE=stockelper
# AIRFLOW_SECRET_KEY=your-secret-key
```

---

## Docker 관련 문제

### ❌ 컨테이너가 계속 재시작됨

**증상**:
```bash
$ docker ps
CONTAINER ID   STATUS
abc123         Restarting (1) 5 seconds ago
```

**원인**: 컨테이너 시작 실패

**해결 방법**:

```bash
# 1. 로그 확인
docker logs stockelper-airflow

# 2. 일반적인 원인
# - 환경 변수 오류
# - 데이터베이스 초기화 실패
# - 포트 충돌

# 3. 컨테이너 재빌드
docker compose down
docker compose build --no-cache
docker compose up -d
```

### ❌ 볼륨 권한 문제

**증상**:
```
PermissionError: [Errno 13] Permission denied: '/opt/airflow/logs'
```

**원인**: 볼륨 권한 설정 오류

**해결 방법**:

```bash
# 1. 볼륨 삭제 후 재생성
docker compose down -v
docker compose up -d

# 2. 권한 수동 설정
docker exec -u root stockelper-airflow chown -R airflow:airflow /opt/airflow/logs
```

### ❌ 이미지 빌드 실패

**증상**:
```
ERROR: failed to solve: process "/bin/sh -c pip install -r requirements.txt" did not complete successfully
```

**원인**: 의존성 설치 실패

**해결 방법**:

```bash
# 1. requirements.txt 확인
cat requirements.txt

# 2. 캐시 없이 재빌드
docker compose build --no-cache

# 3. 특정 패키지 버전 문제 시
# requirements.txt에서 버전 제거 또는 변경
```

---

## MongoDB 연결 문제

### ❌ MongoDB 연결 실패

**증상**:
```
pymongo.errors.ServerSelectionTimeoutError: localhost:27017: [Errno 111] Connection refused
```

**원인**: MongoDB 서버에 연결할 수 없음

**해결 방법**:

```bash
# 1. MONGODB_URI 확인
echo $MONGODB_URI

# 2. MongoDB 서버 상태 확인
# MongoDB Atlas 사용 시: 웹 콘솔에서 확인
# 로컬 MongoDB 사용 시:
sudo systemctl status mongod

# 3. 네트워크 연결 테스트
docker exec stockelper-airflow python -c "
from pymongo import MongoClient
client = MongoClient('$MONGODB_URI', serverSelectionTimeoutMS=5000)
print(client.server_info())
"

# 4. IP 화이트리스트 확인 (Atlas)
# MongoDB Atlas 콘솔 → Network Access → IP Whitelist
```

### ❌ 인증 실패

**증상**:
```
pymongo.errors.OperationFailure: Authentication failed
```

**원인**: 잘못된 사용자명 또는 비밀번호

**해결 방법**:

```bash
# 1. .env 파일의 MONGODB_URI 확인
cat .env | grep MONGODB_URI

# 2. URI 형식 확인
# mongodb+srv://username:password@cluster.mongodb.net/

# 3. 비밀번호에 특수문자가 있는 경우 URL 인코딩
# 예: p@ssw0rd → p%40ssw0rd
```

### ❌ 데이터베이스 권한 부족

**증상**:
```
pymongo.errors.OperationFailure: not authorized on stockelper to execute command
```

**원인**: 사용자에게 데이터베이스 권한 없음

**해결 방법**:

```bash
# MongoDB Atlas에서:
# 1. Database Access 메뉴
# 2. 사용자 선택
# 3. Edit → Built-in Role → readWrite 또는 dbAdmin 권한 부여
```

---

## DAG 관련 문제

### ❌ DAG가 UI에 표시되지 않음

**증상**: Airflow UI에 DAG가 없음

**원인**: 
- DAG 파일 위치 오류
- 구문 오류
- Import 오류

**해결 방법**:

```bash
# 1. DAG 파일 위치 확인
docker exec stockelper-airflow ls -la /opt/airflow/dags

# 2. Import 오류 확인
docker exec stockelper-airflow airflow dags list-import-errors

# 3. DAG 구문 검사
docker exec stockelper-airflow python /opt/airflow/dags/my_dag.py

# 4. 스케줄러 재시작
docker compose restart
```

### ❌ DAG 실행 실패

**증상**: Task가 failed 상태

**해결 방법**:

```bash
# 1. Task 로그 확인
# Airflow UI → DAG → Task → Log 탭

# 2. CLI로 로그 확인
docker exec stockelper-airflow airflow tasks logs stock_report_crawler crawl_stock_report 2025-10-12

# 3. Task 재실행
# Airflow UI → Task → Clear → Confirm

# 4. 디버그 모드로 실행
docker exec stockelper-airflow airflow tasks test stock_report_crawler crawl_stock_report 2025-10-12
```

### ❌ Task가 Queued 상태에서 멈춤

**증상**: Task가 계속 queued 상태

**원인**: Executor 문제 또는 리소스 부족

**해결 방법**:

```bash
# 1. 스케줄러 상태 확인
docker exec stockelper-airflow airflow scheduler status

# 2. 스케줄러 재시작
docker compose restart

# 3. 리소스 확인
docker stats stockelper-airflow

# 4. Executor 설정 확인
docker exec stockelper-airflow airflow config get-value core executor
```

---

## 크롤링 문제

### ❌ Selenium WebDriver 오류

**증상**:
```
selenium.common.exceptions.WebDriverException: Message: unknown error: Chrome failed to start
```

**원인**: Chrome 또는 ChromeDriver 문제

**해결 방법**:

```bash
# 1. Chrome 버전 확인
docker exec stockelper-airflow google-chrome --version

# 2. ChromeDriver 버전 확인
docker exec stockelper-airflow chromedriver --version

# 3. 버전 불일치 시 Dockerfile 수정
# CHROME_DRIVER_VERSION="131.0.6778.204" → 최신 버전으로 변경

# 4. 이미지 재빌드
docker compose down
docker compose build --no-cache
docker compose up -d
```

### ❌ 크롤링 타임아웃

**증상**:
```
selenium.common.exceptions.TimeoutException: Message: timeout
```

**원인**: 페이지 로딩 시간 초과

**해결 방법**:

```python
# 크롤러 코드에서 타임아웃 증가
WebDriverWait(self.driver, 30).until(  # 10 → 30초로 증가
    EC.presence_of_element_located((By.CLASS_NAME, "report-list"))
)

# 또는 암시적 대기 추가
self.driver.implicitly_wait(10)
```

### ❌ 데이터 파싱 오류

**증상**:
```
NoSuchElementException: Message: no such element: Unable to locate element
```

**원인**: 웹사이트 구조 변경

**해결 방법**:

```python
# 1. 요소 존재 확인
try:
    element = self.driver.find_element(By.CLASS_NAME, "report-title")
except NoSuchElementException:
    logger.warning("Element not found, using alternative selector")
    element = self.driver.find_element(By.CSS_SELECTOR, ".report .title")

# 2. 웹사이트 구조 확인
# 브라우저에서 직접 확인 후 셀렉터 업데이트
```

---

## 로그 관련 문제

### ❌ 로그가 출력되지 않음

**증상**: Task 로그가 비어있음

**원인**: 로깅 설정 오류

**해결 방법**:

```python
# 1. 로거 설정 확인
from modules.common.logging_config import setup_logger
logger = setup_logger(__name__)

# 2. 로그 레벨 확인
logger.setLevel(logging.DEBUG)

# 3. 핸들러 확인
print(logger.handlers)
```

### ❌ 로그 파일이 너무 큼

**증상**: 디스크 공간 부족

**해결 방법**:

```bash
# 1. 로그 크기 확인
du -sh /opt/airflow/logs

# 2. 수동 정리
./scripts/cleanup_logs.sh

# 3. log_cleanup DAG 활성화
# Airflow UI에서 log_cleanup DAG 토글 ON

# 4. 보관 기간 조정
# dags/log_cleanup_dag.py
LOG_RETENTION_DAYS = 7  # 7일 → 3일로 변경
```

### ❌ 중복 로그 출력

**증상**: 같은 로그가 여러 번 출력됨

**원인**: 핸들러 중복 추가

**해결 방법**:

```python
# modules/common/logging_config.py 사용
# 이미 중복 방지 로직 포함됨

from modules.common.logging_config import setup_logger
logger = setup_logger(__name__)  # 자동으로 중복 방지
```

---

## 성능 문제

### ❌ DAG 실행이 느림

**증상**: Task 실행 시간이 과도하게 김

**해결 방법**:

```bash
# 1. 리소스 사용량 확인
docker stats stockelper-airflow

# 2. 메모리 증가
# docker-compose.yml
deploy:
  resources:
    limits:
      memory: 4G  # 2G → 4G

# 3. 병렬 처리 고려
# SequentialExecutor → LocalExecutor 변경

# 4. 크롤링 최적화
# - 불필요한 대기 시간 제거
# - 배치 처리 구현
# - 캐싱 활용
```

### ❌ 메모리 부족

**증상**:
```
MemoryError: Unable to allocate array
```

**해결 방법**:

```bash
# 1. 메모리 사용량 확인
docker exec stockelper-airflow free -h

# 2. Docker 메모리 제한 증가
# docker-compose.yml
deploy:
  resources:
    limits:
      memory: 8G

# 3. 데이터 처리 최적화
# - 청크 단위로 처리
# - 불필요한 데이터 즉시 삭제
# - Generator 사용
```

### ❌ 디스크 공간 부족

**증상**:
```
OSError: [Errno 28] No space left on device
```

**해결 방법**:

```bash
# 1. 디스크 사용량 확인
df -h

# 2. Docker 정리
docker system prune -a --volumes

# 3. 로그 정리
./scripts/cleanup_logs.sh

# 4. 오래된 DAG Run 삭제
# Airflow UI → Browse → DAG Runs → 삭제
```

---

## 🔍 디버깅 체크리스트

### 문제 발생 시 확인 사항

- [ ] `.env` 파일 존재 및 필수 변수 설정
- [ ] Docker 컨테이너 실행 중 (`docker ps`)
- [ ] 로그 확인 (`docker logs stockelper-airflow`)
- [ ] MongoDB 연결 테스트
- [ ] DAG Import 오류 확인
- [ ] 디스크 공간 충분
- [ ] 메모리 사용량 정상
- [ ] 네트워크 연결 정상

### 로그 수집 명령어

```bash
# 시스템 정보
docker info > debug_info.txt
docker ps -a >> debug_info.txt
docker stats --no-stream >> debug_info.txt

# 컨테이너 로그
docker logs stockelper-airflow > airflow_logs.txt 2>&1

# Airflow 상태
docker exec stockelper-airflow airflow dags list >> debug_info.txt
docker exec stockelper-airflow airflow dags list-import-errors >> debug_info.txt

# 환경 변수 (민감 정보 제외)
docker exec stockelper-airflow env | grep -v PASSWORD | grep -v SECRET >> debug_info.txt
```

---

## 🆘 추가 도움말

### 문서 참고

- [Quickstart](QUICKSTART.md) - 기본 사용법
- [Architecture](ARCHITECTURE.md) - 시스템 구조
- [Development](DEVELOPMENT.md) - 개발 가이드
- [Logging Guide](LOGGING_GUIDE.md) - 로깅 사용법

### 이슈 보고

문제가 해결되지 않으면:

1. GitHub Issues에 새 이슈 생성
2. 다음 정보 포함:
   - 문제 설명
   - 재현 단계
   - 에러 메시지
   - 로그 파일
   - 환경 정보 (OS, Docker 버전 등)

---

대부분의 문제는 이 가이드로 해결할 수 있습니다. 추가 도움이 필요하면 이슈를 생성해주세요!
