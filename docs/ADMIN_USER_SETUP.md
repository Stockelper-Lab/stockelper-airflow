# Airflow Admin 사용자 설정 가이드

Airflow의 admin 사용자 계정을 환경 변수로 설정하는 방법을 설명합니다.

## 설정 방법

### 1. .env 파일 편집

`.env` 파일을 열어서 다음 내용을 수정하세요:

```bash
# Airflow Admin User Configuration
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=your-secure-password-here
AIRFLOW_ADMIN_EMAIL=admin@stockelper.com
```

### 2. 환경 변수 설명

| 환경 변수 | 설명 | 기본값 | 예시 |
|----------|------|--------|------|
| `AIRFLOW_ADMIN_USERNAME` | 관리자 사용자명 | `admin` | `admin`, `airflow_admin` |
| `AIRFLOW_ADMIN_PASSWORD` | 관리자 비밀번호 | `admin` | `SecureP@ssw0rd!` |
| `AIRFLOW_ADMIN_EMAIL` | 관리자 이메일 | `admin@stockelper.com` | `your-email@example.com` |

### 3. 기본값 동작

환경 변수를 설정하지 않으면 다음 기본값이 사용됩니다:

```yaml
AIRFLOW_ADMIN_USERNAME: admin
AIRFLOW_ADMIN_PASSWORD: admin
AIRFLOW_ADMIN_EMAIL: admin@stockelper.com
```

이는 `docker-compose.yml`의 다음 설정에 의해 제공됩니다:

```yaml
- AIRFLOW_ADMIN_USERNAME=${AIRFLOW_ADMIN_USERNAME:-admin}
- AIRFLOW_ADMIN_PASSWORD=${AIRFLOW_ADMIN_PASSWORD:-admin}
- AIRFLOW_ADMIN_EMAIL=${AIRFLOW_ADMIN_EMAIL:-admin@stockelper.com}
```

---

## 사용 예시

### 예시 1: 기본 설정 사용

`.env` 파일에 아무것도 설정하지 않으면:

```bash
# .env 파일에 AIRFLOW_ADMIN_* 변수가 없음
```

**결과**:
- 사용자명: `admin`
- 비밀번호: `admin`
- 이메일: `admin@stockelper.com`

### 예시 2: 커스텀 비밀번호 설정

`.env` 파일:

```bash
AIRFLOW_ADMIN_USERNAME=admin
AIRFLOW_ADMIN_PASSWORD=MySecurePassword123!
AIRFLOW_ADMIN_EMAIL=admin@stockelper.com
```

**결과**:
- 사용자명: `admin`
- 비밀번호: `MySecurePassword123!`
- 이메일: `admin@stockelper.com`

### 예시 3: 완전히 커스텀 설정

`.env` 파일:

```bash
AIRFLOW_ADMIN_USERNAME=stockelper_admin
AIRFLOW_ADMIN_PASSWORD=VerySecureP@ssw0rd!
AIRFLOW_ADMIN_EMAIL=devops@stockelper.com
```

**결과**:
- 사용자명: `stockelper_admin`
- 비밀번호: `VerySecureP@ssw0rd!`
- 이메일: `devops@stockelper.com`

---

## 비밀번호 변경 방법

### 방법 1: .env 파일 수정 후 재배포

1. `.env` 파일에서 `AIRFLOW_ADMIN_PASSWORD` 변경
2. 기존 데이터베이스 삭제 (사용자 정보가 저장되어 있음)
3. 재배포

```bash
# 1. .env 파일 수정
nano .env

# 2. 컨테이너 및 볼륨 삭제
docker compose down -v

# 3. 재배포
./scripts/deploy.sh
```

**주의**: `-v` 옵션은 모든 데이터(DAG 실행 기록 등)를 삭제합니다!

### 방법 2: Airflow CLI로 비밀번호 변경

실행 중인 컨테이너에서 비밀번호만 변경:

```bash
# 컨테이너 접속
docker exec -it stockelper-airflow bash

# 비밀번호 변경
airflow users update --username admin --password NewPassword123!

# 또는 대화형으로 변경
airflow users update --username admin --password-prompt
```

### 방법 3: Airflow UI에서 변경

1. Airflow UI 로그인: http://localhost:21003
2. 상단 메뉴: **Security** → **List Users**
3. 사용자 클릭 → **Edit Record**
4. 새 비밀번호 입력 → **Save**

---

## 보안 권장 사항

### 1. 강력한 비밀번호 사용

❌ **나쁜 예**:
```bash
AIRFLOW_ADMIN_PASSWORD=admin
AIRFLOW_ADMIN_PASSWORD=123456
AIRFLOW_ADMIN_PASSWORD=password
```

✅ **좋은 예**:
```bash
AIRFLOW_ADMIN_PASSWORD=Ae8$mK9#pL2@vN5!
AIRFLOW_ADMIN_PASSWORD=MyC0mpl3x!P@ssw0rd
```

### 2. 비밀번호 요구 사항

- **최소 길이**: 12자 이상
- **대문자**: 최소 1개
- **소문자**: 최소 1개
- **숫자**: 최소 1개
- **특수문자**: 최소 1개 (`!@#$%^&*`)

### 3. .env 파일 보안

```bash
# .env 파일 권한 설정 (소유자만 읽기/쓰기)
chmod 600 .env

# .gitignore에 추가 (이미 추가되어 있음)
echo ".env" >> .gitignore
```

### 4. 프로덕션 환경

프로덕션 환경에서는:

1. **기본 비밀번호 절대 사용 금지**
2. **정기적인 비밀번호 변경** (3-6개월마다)
3. **비밀번호 관리자 사용** (1Password, LastPass 등)
4. **환경 변수를 시크릿 관리 시스템에 저장** (AWS Secrets Manager, HashiCorp Vault 등)

---

## 문제 해결

### 로그인 실패

**증상**: "Invalid username or password" 오류

**해결 방법**:

1. `.env` 파일 확인:
   ```bash
   cat .env | grep AIRFLOW_ADMIN
   ```

2. 컨테이너 환경 변수 확인:
   ```bash
   docker exec stockelper-airflow env | grep AIRFLOW_ADMIN
   ```

3. 사용자 목록 확인:
   ```bash
   docker exec stockelper-airflow airflow users list
   ```

4. 비밀번호 재설정:
   ```bash
   docker exec -it stockelper-airflow airflow users update --username admin --password NewPassword
   ```

### 사용자가 생성되지 않음

**증상**: 로그인 화면에서 어떤 계정으로도 로그인 불가

**해결 방법**:

1. 컨테이너 로그 확인:
   ```bash
   docker logs stockelper-airflow | grep "users create"
   ```

2. 수동으로 사용자 생성:
   ```bash
   docker exec -it stockelper-airflow bash
   airflow users create \
     --username admin \
     --firstname Admin \
     --lastname User \
     --role Admin \
     --email admin@stockelper.com \
     --password admin
   ```

### 비밀번호 변경이 반영되지 않음

**원인**: 기존 데이터베이스에 이전 사용자 정보가 남아있음

**해결 방법**:

```bash
# 옵션 1: 볼륨 삭제 후 재배포 (모든 데이터 삭제)
docker compose down -v
./scripts/deploy.sh

# 옵션 2: CLI로 비밀번호만 업데이트
docker exec -it stockelper-airflow airflow users update --username admin --password NewPassword
```

---

## 추가 사용자 생성

Admin 외에 추가 사용자를 생성하려면:

```bash
# 컨테이너 접속
docker exec -it stockelper-airflow bash

# 새 사용자 생성
airflow users create \
  --username viewer \
  --firstname View \
  --lastname Only \
  --role Viewer \
  --email viewer@stockelper.com \
  --password ViewerPassword123

# 사용 가능한 역할:
# - Admin: 모든 권한
# - User: DAG 실행 및 조회
# - Viewer: 조회만 가능
# - Op: 운영자 권한
# - Public: 공개 권한
```

---

## 참고 자료

- [Airflow 공식 문서 - Security](https://airflow.apache.org/docs/apache-airflow/stable/security/index.html)
- [Airflow CLI - Users](https://airflow.apache.org/docs/apache-airflow/stable/cli-and-env-variables-ref.html#users)
- [Airflow RBAC](https://airflow.apache.org/docs/apache-airflow/stable/security/access-control.html)
