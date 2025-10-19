# Airflow 로그 관리 가이드

Airflow는 실행 중 대량의 로그를 생성합니다. 이 문서는 로그를 효율적으로 관리하는 방법을 설명합니다.

## 목차
1. [로그 보관 정책](#로그-보관-정책)
2. [자동 로그 정리](#자동-로그-정리)
3. [수동 로그 정리](#수동-로그-정리)
4. [로그 모니터링](#로그-모니터링)
5. [원격 로그 저장](#원격-로그-저장)

---

## 로그 보관 정책

### 기본 설정

`config/airflow.cfg` 파일에서 로그 보관 정책을 설정할 수 있습니다:

```ini
[logging]
# 로그 보관 기간 (일 단위)
log_retention_days = 7

# 태스크 인스턴스당 최대 로그 파일 수
max_log_files_per_task = 5

[scheduler]
# 로그 정리 활성화
enable_log_cleanup = True

# 로그 정리 주기 (초 단위, 86400 = 24시간)
log_cleanup_interval = 86400
```

### 권장 설정

| 환경 | 보관 기간 | 설명 |
|------|----------|------|
| **개발** | 3-7일 | 빠른 디버깅을 위해 짧은 기간 |
| **스테이징** | 7-14일 | 테스트 및 검증을 위한 중간 기간 |
| **프로덕션** | 30-90일 | 감사 및 문제 해결을 위한 긴 기간 |

---

## 자동 로그 정리

### 1. Airflow DAG를 통한 자동 정리

`dags/log_cleanup_dag.py` DAG가 매일 자동으로 실행되어 오래된 로그를 삭제합니다.

**특징:**
- 매일 새벽 2시(UTC)에 실행
- 7일 이상 된 로그 자동 삭제
- 삭제 전후 통계 제공
- 빈 디렉토리 자동 제거

**설정 변경:**

```python
# dags/log_cleanup_dag.py 파일에서 수정
LOG_RETENTION_DAYS = 7  # 보관 기간 변경
DRY_RUN = False  # True로 설정하면 삭제 없이 확인만
```

**수동 실행:**

```bash
# Airflow UI에서 log_cleanup DAG를 찾아 수동 실행
# 또는 CLI로 실행
docker exec stockelper-airflow airflow dags trigger log_cleanup
```

### 2. Cron을 통한 자동 정리

호스트 시스템에서 cron을 설정하여 정기적으로 로그를 정리할 수 있습니다.

```bash
# crontab 편집
crontab -e

# 매일 새벽 3시에 로그 정리 (7일 보관)
0 3 * * * /home/jys/workspace/02_PseudoLab/stockelper-airflow/scripts/cleanup_logs.sh --days 7

# 매주 일요일 새벽 4시에 로그 정리 (30일 보관)
0 4 * * 0 /home/jys/workspace/02_PseudoLab/stockelper-airflow/scripts/cleanup_logs.sh --days 30
```

---

## 수동 로그 정리

### 스크립트 사용

```bash
# 기본 사용 (7일 보관)
./scripts/cleanup_logs.sh

# 30일 보관
./scripts/cleanup_logs.sh --days 30

# Dry run (삭제하지 않고 확인만)
./scripts/cleanup_logs.sh --dry-run

# 상세 출력
./scripts/cleanup_logs.sh --verbose --days 14

# 사용자 정의 경로
./scripts/cleanup_logs.sh --path /custom/log/path --days 7
```

### Docker 컨테이너 내부에서 실행

```bash
# 컨테이너 접속
docker exec -it stockelper-airflow bash

# 로그 정리
find /opt/airflow/logs -type f -mtime +7 -delete
find /opt/airflow/logs -type d -empty -delete
```

### 수동 명령어

```bash
# 7일 이상 된 로그 파일 찾기
find /opt/airflow/logs -type f -mtime +7

# 7일 이상 된 로그 파일 삭제
find /opt/airflow/logs -type f -mtime +7 -delete

# 빈 디렉토리 삭제
find /opt/airflow/logs -type d -empty -delete

# 특정 DAG의 로그만 삭제
find /opt/airflow/logs/dag_id=my_dag -type f -mtime +7 -delete
```

---

## 로그 모니터링

### 1. 디스크 사용량 확인

```bash
# 로그 폴더 전체 크기
du -sh /opt/airflow/logs

# 로그 폴더 내 상위 10개 디렉토리
du -h /opt/airflow/logs | sort -rh | head -10

# 파일 개수 확인
find /opt/airflow/logs -type f | wc -l
```

### 2. Docker 컨테이너에서 확인

```bash
# 컨테이너 내부 디스크 사용량
docker exec stockelper-airflow df -h /opt/airflow/logs

# 로그 폴더 크기
docker exec stockelper-airflow du -sh /opt/airflow/logs
```

### 3. 로그 통계 스크립트

```bash
#!/bin/bash
# log_stats.sh

LOG_PATH="/opt/airflow/logs"

echo "=== Airflow Log Statistics ==="
echo "Total size: $(du -sh $LOG_PATH | cut -f1)"
echo "Total files: $(find $LOG_PATH -type f | wc -l)"
echo "Total directories: $(find $LOG_PATH -type d | wc -l)"
echo ""
echo "=== Top 10 Largest DAGs ==="
du -h $LOG_PATH/dag_id=* 2>/dev/null | sort -rh | head -10
```

---

## 원격 로그 저장

프로덕션 환경에서는 로그를 원격 스토리지에 저장하는 것을 권장합니다.

### 1. AWS S3 설정

```ini
# config/airflow.cfg
[logging]
remote_logging = True
remote_log_conn_id = aws_default
remote_base_log_folder = s3://my-bucket/airflow-logs
```

```bash
# Airflow Connection 추가
docker exec stockelper-airflow airflow connections add aws_default \
    --conn-type aws \
    --conn-extra '{"aws_access_key_id": "YOUR_KEY", "aws_secret_access_key": "YOUR_SECRET", "region_name": "us-east-1"}'
```

### 2. Google Cloud Storage 설정

```ini
# config/airflow.cfg
[logging]
remote_logging = True
remote_log_conn_id = google_cloud_default
remote_base_log_folder = gs://my-bucket/airflow-logs
```

### 3. Azure Blob Storage 설정

```ini
# config/airflow.cfg
[logging]
remote_logging = True
remote_log_conn_id = azure_default
remote_base_log_folder = wasb://my-container/airflow-logs
```

---

## 로그 압축

디스크 공간을 절약하기 위해 오래된 로그를 압축할 수 있습니다.

### 자동 압축 스크립트

```bash
#!/bin/bash
# compress_old_logs.sh

LOG_PATH="/opt/airflow/logs"
COMPRESS_DAYS=3  # 3일 이상 된 로그 압축

# 3일 이상 된 .log 파일을 찾아 gzip으로 압축
find "$LOG_PATH" -type f -name "*.log" -mtime +$COMPRESS_DAYS ! -name "*.gz" -exec gzip {} \;

echo "Log compression completed!"
```

### Cron 설정

```bash
# 매일 새벽 1시에 로그 압축
0 1 * * * /path/to/compress_old_logs.sh
```

---

## 문제 해결

### 디스크 공간 부족

```bash
# 1. 현재 디스크 사용량 확인
df -h

# 2. 로그 폴더 크기 확인
du -sh /opt/airflow/logs

# 3. 긴급 정리 (1일 이상 된 로그 삭제)
find /opt/airflow/logs -type f -mtime +1 -delete

# 4. 빈 디렉토리 정리
find /opt/airflow/logs -type d -empty -delete
```

### 로그 정리 실패

```bash
# 1. 권한 확인
ls -la /opt/airflow/logs

# 2. 소유자 변경 (필요시)
sudo chown -R airflow:airflow /opt/airflow/logs

# 3. 권한 변경 (필요시)
sudo chmod -R 755 /opt/airflow/logs
```

---

## 모범 사례

1. **정기적인 모니터링**: 주기적으로 로그 크기를 확인하세요
2. **적절한 보관 기간**: 환경에 맞는 보관 기간을 설정하세요
3. **원격 저장소 사용**: 프로덕션에서는 S3, GCS 등 사용
4. **로그 레벨 조정**: 불필요한 DEBUG 로그는 비활성화
5. **압축 활용**: 오래된 로그는 압축하여 저장
6. **알림 설정**: 디스크 사용량이 임계값을 초과하면 알림

---

## 참고 자료

- [Airflow 공식 문서 - Logging](https://airflow.apache.org/docs/apache-airflow/stable/logging-monitoring/logging-tasks.html)
- [Airflow 로그 관리 Best Practices](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)
