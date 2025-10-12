# Docker Compose 설정 변경 사항

stockelper-kg의 docker-compose.yml 스타일에 맞춰 Airflow 설정을 통일했습니다.

## 주요 변경 사항

### 1. 서비스 구조 통일

#### 이전 (Airflow)
```yaml
services:
  stockelper-airflow:
    build: ...
    ports:
      - "8080:8080"
    env_file:
      - .env
    environment:
      - AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/dags
      - ...
    restart: unless-stopped
```

#### 변경 후 (stockelper-kg 스타일)
```yaml
services:
  airflow:
    build: ...
    environment:
      - AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/dags
      - AIRFLOW__WEBSERVER__SECRET_KEY=${AIRFLOW_SECRET_KEY}
      - MONGODB_URI=${MONGODB_URI}
      - ...
    ports:
      - "21003:8080"   # Webserver
    networks:
      - stockelper
    restart: always
```

### 2. 네트워크 설정 추가

#### stockelper-kg
```yaml
networks:
  stockelper:
    driver: bridge
    name: stockelper
    external: true
```

#### Airflow (추가됨)
```yaml
networks:
  stockelper:
    driver: bridge
    name: stockelper
    external: true
```

**효과**: 모든 Stockelper 서비스가 동일한 네트워크를 공유하여 서로 통신 가능

### 3. 볼륨 명명 규칙 통일

#### 이전
```yaml
volumes:
  airflow-logs:
    driver: local
  airflow-db:
    driver: local
```

#### 변경 후 (stockelper-kg 스타일)
```yaml
volumes:
  airflow_logs:
  airflow_db:
```

**변경점**: 
- 하이픈(`-`) → 언더스코어(`_`)
- `driver: local` 제거 (기본값)

### 4. 환경 변수 관리 개선

#### 이전
```yaml
env_file:
  - .env
environment:
  - AIRFLOW__WEBSERVER__SECRET_KEY=stockelper-secret-key-change-in-production
  - MONGODB_URI=mongodb://...
```

#### 변경 후
```yaml
environment:
  - AIRFLOW__WEBSERVER__SECRET_KEY=${AIRFLOW_SECRET_KEY}
  - MONGODB_URI=${MONGODB_URI}
```

**효과**: 
- `.env` 파일에서 환경 변수 참조
- 민감한 정보를 하드코딩하지 않음
- stockelper-kg와 동일한 패턴

### 5. 포트 변경

#### 이전
```yaml
ports:
  - "8080:8080"
```

#### 변경 후
```yaml
ports:
  - "21003:8080"   # Webserver
```

**이유**: 
- 다른 Stockelper 서비스와 포트 충돌 방지
- Neo4j: 21004 (HTTP), 21005 (Bolt)
- Airflow: 21003 (Webserver)

### 6. Restart 정책 통일

#### 이전
```yaml
restart: unless-stopped
```

#### 변경 후
```yaml
restart: always
```

**이유**: stockelper-kg와 동일한 정책 사용

---

## 전체 비교표

| 항목 | 이전 (Airflow) | 변경 후 | stockelper-kg |
|------|---------------|---------|---------------|
| **서비스 이름** | `stockelper-airflow` | `airflow` | `neo4j` |
| **포트** | `8080:8080` | `21003:8080` | `21004:7474`, `21005:7687` |
| **네트워크** | ❌ 없음 | ✅ `stockelper` | ✅ `stockelper` |
| **볼륨 명명** | `airflow-logs` | `airflow_logs` | `neo4j_data` |
| **Restart** | `unless-stopped` | `always` | `always` |
| **환경 변수** | 하드코딩 | `.env` 참조 | `.env` 참조 |
| **Driver 명시** | `driver: local` | 생략 (기본값) | 생략 (기본값) |

---

## 새로운 파일 구조

```
stockelper-airflow/
├── docker-compose.yml          # 루트로 이동 (이전: docker/docker-compose.yml)
├── .env                        # 환경 변수 (gitignore)
├── .env.example                # 환경 변수 템플릿
├── docker/
│   └── Dockerfile
├── scripts/
│   ├── deploy.sh               # 업데이트됨
│   ├── setup_network.sh        # 신규 추가
│   └── cleanup_logs.sh
└── docs/
    └── DOCKER_COMPOSE_CHANGES.md  # 이 문서
```

---

## .env 파일 변경

### 이전 (.env.example)
```bash
# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017/
MONGODB_HOST=localhost
MONGODB_PORT=27017

# Airflow Configuration
AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/dags
AIRFLOW__CORE__PLUGINS_FOLDER=/opt/airflow/plugins
...
AIRFLOW__WEBSERVER__SECRET_KEY=change-this-secret-key-in-production
```

### 변경 후 (.env.example)
```bash
# MongoDB Configuration
MONGODB_URI=mongodb+srv://stockelper:YOUR_PASSWORD@stockelper.btl2cdx.mongodb.net/

# Airflow Secret Key
AIRFLOW_SECRET_KEY=change-this-secret-key-in-production
```

**변경점**:
- 불필요한 환경 변수 제거 (docker-compose.yml에서 직접 설정)
- 필수 환경 변수만 `.env`에서 관리
- MongoDB Atlas URI 형식으로 변경

---

## 배포 스크립트 개선

### 새로운 기능

1. **네트워크 자동 생성**
   ```bash
   ./scripts/setup_network.sh
   ```
   - `stockelper` 네트워크가 없으면 자동 생성
   - 이미 존재하면 스킵

2. **.env 파일 자동 생성**
   ```bash
   ./scripts/deploy.sh
   ```
   - `.env` 파일이 없으면 `.env.example`에서 자동 생성
   - 사용자에게 수정 요청

3. **컬러 출력**
   - 가독성 향상
   - 에러/경고/성공 메시지 구분

---

## 마이그레이션 가이드

### 1. 기존 컨테이너 중지
```bash
cd /home/jys/workspace/02_PseudoLab/stockelper-airflow
docker compose down
```

### 2. .env 파일 업데이트
```bash
# .env 파일 편집
nano .env

# 다음 내용으로 변경:
MONGODB_URI=mongodb+srv://stockelper:YOUR_PASSWORD@stockelper.btl2cdx.mongodb.net/
AIRFLOW_SECRET_KEY=your-secret-key-here
```

### 3. 네트워크 생성
```bash
./scripts/setup_network.sh
```

### 4. 배포
```bash
./scripts/deploy.sh
```

### 5. 접속 확인
- **URL**: http://localhost:21003
- **계정**: admin / admin

---

## 서비스 간 통신

이제 모든 Stockelper 서비스가 `stockelper` 네트워크를 공유하므로 서로 통신할 수 있습니다.

### 예시: Airflow에서 Neo4j 접속
```python
from neo4j import GraphDatabase

# 컨테이너 이름으로 접속 가능
uri = "bolt://stockelper-neo4j:7687"
driver = GraphDatabase.driver(uri, auth=("neo4j", "password"))
```

### 예시: Airflow에서 MongoDB 접속
```python
from pymongo import MongoClient

# .env의 MONGODB_URI 사용
client = MongoClient(os.getenv("MONGODB_URI"))
```

---

## 장점

1. **일관성**: 모든 Stockelper 서비스가 동일한 패턴 사용
2. **보안**: 민감한 정보를 `.env`로 관리
3. **확장성**: 새로운 서비스 추가 용이
4. **네트워크**: 서비스 간 통신 간소화
5. **포트 관리**: 충돌 방지를 위한 체계적인 포트 할당

---

## 포트 할당 체계

| 서비스 | 포트 | 용도 |
|--------|------|------|
| **MongoDB** | 21002 | Database |
| **Airflow** | 21003 | Webserver |
| **Neo4j HTTP** | 21004 | Web UI |
| **Neo4j Bolt** | 21005 | Database |

---

## 문제 해결

### 네트워크 오류
```bash
# 네트워크 재생성
docker network rm stockelper
./scripts/setup_network.sh
```

### 포트 충돌
```bash
# 사용 중인 포트 확인
sudo lsof -i :21003

# 프로세스 종료 후 재시작
docker compose restart
```

### 볼륨 문제
```bash
# 볼륨 초기화 (주의: 데이터 삭제됨)
docker compose down -v
docker compose up -d
```
