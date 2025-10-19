# Scripts 업데이트 완료 (2025-10-12)

## 변경 사항 요약

스크립트 파일들을 현재 프로젝트 구조에 맞게 업데이트했습니다.

---

## 1. 수정된 스크립트

### deploy.sh
**변경 사항**:
- Dockerfile 경로 수정: `docker/Dockerfile` → `Dockerfile` (프로젝트 루트)
- 에러 메시지 업데이트

**변경 전**:
```bash
if [ ! -f "docker/Dockerfile" ]; then
    echo -e "${RED}❌ Dockerfile not found in docker/ directory${NC}"
    exit 1
fi
```

**변경 후**:
```bash
if [ ! -f "Dockerfile" ]; then
    echo -e "${RED}❌ Dockerfile not found in project root${NC}"
    exit 1
fi
```

---

### stop.sh
**변경 사항**:
- 프로젝트 루트 경로 수정: `docker` 디렉토리 → 프로젝트 루트
- `docker-compose` → `docker compose` (최신 명령어)
- 색상 코드 및 포맷팅 개선
- 헤더 주석 추가

**변경 전**:
```bash
cd "$PROJECT_ROOT/docker"
docker-compose down --remove-orphans
```

**변경 후**:
```bash
cd "$PROJECT_ROOT"
docker compose down --remove-orphans
```

---

## 2. 신규 스크립트

### cleanup_logs_container.sh
**목적**: 호스트에서 컨테이너 내부의 로그 정리 실행

**기능**:
- 컨테이너 실행 상태 확인
- `cleanup_logs.sh` 스크립트를 컨테이너에 복사
- 컨테이너 내부에서 로그 정리 실행
- 결과 출력

**사용법**:
```bash
# 기본 실행 (7일 이상 된 로그 삭제)
./scripts/cleanup_logs_container.sh

# 30일 이상 된 로그 삭제
./scripts/cleanup_logs_container.sh --days 30

# 드라이런 (실제 삭제 없이 확인만)
./scripts/cleanup_logs_container.sh --dry-run

# 상세 출력
./scripts/cleanup_logs_container.sh --verbose --days 14
```

**옵션**:
- `-d, --days DAYS`: 보관 기간 (기본값: 7일)
- `-n, --dry-run`: 삭제 시뮬레이션
- `-v, --verbose`: 상세 출력
- `-h, --help`: 도움말

---

### scripts/README.md
**목적**: 모든 스크립트에 대한 종합 문서

**내용**:
1. 각 스크립트 설명 및 사용법
2. 일반적인 워크플로우
3. 환경 변수 설명
4. 네트워크 및 포트 설정
5. 볼륨 설정
6. 문제 해결 가이드

---

## 3. 유지된 스크립트

### cleanup_logs.sh
- 변경 없음 (컨테이너 내부에서 실행되는 스크립트)
- 독립적으로 작동

### setup_network.sh
- 변경 없음
- `stockelper` Docker 네트워크 생성 및 관리

---

## 4. 디렉토리 구조

```
scripts/
├── README.md                    # 신규: 스크립트 종합 문서
├── cleanup_logs.sh              # 유지: 로그 정리 (컨테이너 내부)
├── cleanup_logs_container.sh    # 신규: 로그 정리 래퍼 (호스트)
├── deploy.sh                    # 수정: Dockerfile 경로 수정
├── setup_network.sh             # 유지: 네트워크 설정
└── stop.sh                      # 수정: 경로 및 명령어 업데이트
```

---

## 5. 주요 개선 사항

### 일관성
- 모든 스크립트가 프로젝트 루트에서 실행
- 통일된 색상 코드 및 출력 포맷
- 일관된 에러 처리

### 사용성
- 명확한 에러 메시지
- 상세한 도움말 (`--help`)
- 드라이런 모드 지원

### 문서화
- 모든 스크립트에 헤더 주석 추가
- 종합 README 작성
- 사용 예제 포함

### 안전성
- 스크립트 실행 전 검증
- 컨테이너 상태 확인
- 안전한 에러 처리 (`set -e`)

---

## 6. 사용 가이드

### 초기 배포
```bash
# 1. 환경 설정
cp .env.example .env
nano .env

# 2. 배포
./scripts/deploy.sh
```

### 일상 운영
```bash
# 로그 확인
docker compose logs -f

# 서비스 재시작
docker compose restart

# 서비스 중지
./scripts/stop.sh
```

### 유지보수
```bash
# 로그 정리 (드라이런)
./scripts/cleanup_logs_container.sh --dry-run

# 로그 정리 (실제 실행)
./scripts/cleanup_logs_container.sh --days 7

# 재배포
./scripts/stop.sh
./scripts/deploy.sh
```

---

## 7. 접속 정보

### Airflow Web UI
- **URL**: http://localhost:21003
- **사용자명**: admin (또는 `.env`에 설정한 값)
- **비밀번호**: admin (또는 `.env`에 설정한 값)

### 컨테이너 접속
```bash
# 쉘 접속
docker exec -it stockelper-airflow bash

# 명령 실행
docker exec stockelper-airflow airflow dags list
```

---

## 8. 파일 권한

모든 스크립트는 실행 권한이 설정되어 있습니다:
```bash
-rwxrwxr-x scripts/cleanup_logs.sh
-rwxrwxr-x scripts/cleanup_logs_container.sh
-rwxrwxr-x scripts/deploy.sh
-rwxrwxr-x scripts/setup_network.sh
-rwxrwxr-x scripts/stop.sh
```

---

## 9. 테스트 완료

모든 스크립트는 다음 환경에서 테스트되었습니다:
- OS: Linux
- Docker: 최신 버전
- Docker Compose: V2 (docker compose)
- Airflow: 2.10.4

---

## 10. 다음 단계

1. ✅ 스크립트 업데이트 완료
2. ✅ 문서화 완료
3. ✅ 실행 권한 설정 완료
4. 📝 팀원들에게 변경 사항 공유
5. 📝 CI/CD 파이프라인에 스크립트 통합 (향후)

---

## 참고 문서

- [scripts/README.md](scripts/README.md): 스크립트 상세 문서
- [docs/QUICKSTART.md](docs/QUICKSTART.md): 빠른 시작 가이드
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): 문제 해결 가이드
- [README.md](README.md): 프로젝트 전체 문서

---

## 작성자

Stockelper Team

## 날짜

2025-10-12
