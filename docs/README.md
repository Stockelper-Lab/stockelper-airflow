# 📚 Stockelper Airflow 문서

Stockelper Airflow 프로젝트의 전체 문서 모음입니다.

## 🚀 시작하기

### 빠른 시작
- **[QUICKSTART.md](QUICKSTART.md)** - 5분 안에 시작하기
  - 설치 및 배포
  - 첫 DAG 실행
  - 기본 명령어

### 아키텍처
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - 시스템 구조 이해
  - 전체 구조
  - 데이터 흐름
  - Docker 아키텍처
  - 보안 설계

## 🛠️ 개발

### 개발 가이드
- **[DEVELOPMENT.md](DEVELOPMENT.md)** - 개발 환경 및 가이드
  - 개발 환경 설정
  - 새 DAG 작성
  - 새 크롤러 작성
  - 테스트 및 배포

### API 레퍼런스
- **[API_REFERENCE.md](API_REFERENCE.md)** - 모듈 및 함수 상세 문서
  - 공통 모듈
  - 크롤러 모듈
  - DAG 함수
  - 환경 변수

## 🔧 운영

### 로깅
- **[LOGGING_GUIDE.md](LOGGING_GUIDE.md)** - 로깅 시스템 사용법
  - 통합 로깅 설정
  - 로그 레벨
  - 모범 사례
  - 문제 해결

- **[LOG_MANAGEMENT.md](LOG_MANAGEMENT.md)** - 로그 관리
  - 로그 정리 전략
  - 디스크 공간 관리
  - 로그 분석

### 설정
- **[ADMIN_USER_SETUP.md](ADMIN_USER_SETUP.md)** - Admin 사용자 설정
  - 비밀번호 설정
  - 사용자 관리
  - 보안 권장사항

- **[DOCKER_COMPOSE_CHANGES.md](DOCKER_COMPOSE_CHANGES.md)** - Docker Compose 변경사항
  - 설정 통일 과정
  - 네트워크 구성
  - 마이그레이션 가이드

## 🆘 문제 해결

### 트러블슈팅
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - 문제 해결 가이드
  - 설치 및 배포 문제
  - Docker 관련 문제
  - MongoDB 연결 문제
  - DAG 관련 문제
  - 크롤링 문제
  - 성능 문제

## 📖 문서 구조

```
docs/
├── README.md                   # 이 파일
├── QUICKSTART.md               # 빠른 시작 가이드
├── ARCHITECTURE.md             # 시스템 아키텍처
├── DEVELOPMENT.md              # 개발 가이드
├── API_REFERENCE.md            # API 레퍼런스
├── TROUBLESHOOTING.md          # 문제 해결
├── LOGGING_GUIDE.md            # 로깅 가이드
├── LOG_MANAGEMENT.md           # 로그 관리
├── ADMIN_USER_SETUP.md         # Admin 설정
└── DOCKER_COMPOSE_CHANGES.md   # Docker 변경사항
```

## 🎯 학습 경로

### 초보자
1. [QUICKSTART.md](QUICKSTART.md) - 시작하기
2. [ARCHITECTURE.md](ARCHITECTURE.md) - 구조 이해
3. [LOGGING_GUIDE.md](LOGGING_GUIDE.md) - 로깅 사용법

### 개발자
1. [DEVELOPMENT.md](DEVELOPMENT.md) - 개발 환경 설정
2. [API_REFERENCE.md](API_REFERENCE.md) - API 학습
3. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - 문제 해결

### 운영자
1. [ADMIN_USER_SETUP.md](ADMIN_USER_SETUP.md) - 사용자 관리
2. [LOG_MANAGEMENT.md](LOG_MANAGEMENT.md) - 로그 관리
3. [DOCKER_COMPOSE_CHANGES.md](DOCKER_COMPOSE_CHANGES.md) - 설정 이해

## 🔗 외부 리소스

### 공식 문서
- [Apache Airflow Documentation](https://airflow.apache.org/docs/)
- [MongoDB Documentation](https://www.mongodb.com/docs/)
- [Docker Documentation](https://docs.docker.com/)
- [Selenium Documentation](https://selenium-python.readthedocs.io/)

### 커뮤니티
- [Airflow Slack](https://apache-airflow.slack.com/)
- [Stack Overflow - Airflow](https://stackoverflow.com/questions/tagged/airflow)

## 📝 문서 기여

문서 개선에 기여하고 싶으시다면:

1. 오타나 오류 발견 시 Issue 생성
2. 문서 개선 제안 시 Pull Request
3. 새로운 가이드 추가 제안

### 문서 작성 가이드라인

- **명확성**: 간결하고 명확하게 작성
- **예시**: 실용적인 예시 포함
- **구조**: 마크다운 헤딩으로 구조화
- **코드**: 코드 블록에 언어 지정
- **링크**: 관련 문서 상호 참조

## 📅 문서 업데이트

| 문서 | 최종 업데이트 | 버전 |
|------|--------------|------|
| QUICKSTART.md | 2025-10-12 | 1.0 |
| ARCHITECTURE.md | 2025-10-12 | 1.0 |
| DEVELOPMENT.md | 2025-10-12 | 1.0 |
| API_REFERENCE.md | 2025-10-12 | 1.0 |
| TROUBLESHOOTING.md | 2025-10-12 | 1.0 |
| LOGGING_GUIDE.md | 2025-10-12 | 1.0 |
| LOG_MANAGEMENT.md | 기존 | 1.0 |
| ADMIN_USER_SETUP.md | 2025-10-12 | 1.0 |
| DOCKER_COMPOSE_CHANGES.md | 2025-10-12 | 1.0 |

---

**문서에 대한 질문이나 제안이 있으시면 GitHub Issues를 이용해주세요.**
