# 런타임 모니터링 운영 가이드

미니 PC에서 Prometheus / Grafana / Alertmanager 스택을 기동·검증·유지하는 절차입니다.  
앱 배포(`docker-compose.yml`)와 모니터링(`docker-compose.monitoring.yml`)은 **수명주기가 분리**되어 있으며, Jenkinsfile은 변경하지 않습니다.

## 사전 준비 (Prep)

### 1. 앱 스택 실행 확인

모니터링은 앱 컨테이너를 scrape하므로, 아래 서비스가 먼저 healthy 상태여야 합니다.

| 컨테이너 | 역할 |
|----------|------|
| `saksak-back` | FastAPI 앱 (`/metrics` 제공) |
| `saksak-db` | PostgreSQL |
| `saksak-redis` | Redis |

```bash
docker ps --filter name=saksak-back --filter name=saksak-db --filter name=saksak-redis
```

앱 compose 기동 (Jenkins 배포 경로와 동일한 디렉터리):

```bash
docker compose up -d
```

### 2. 공유 Docker 네트워크 (`saksak-network`)

`docker-compose.yml`에 `name: saksak-network`가 적용되어 있어야 합니다. 모니터링 compose는 이 네트워크를 `external: true`로 join합니다.

```yaml
networks:
  saksak-network:
    name: saksak-network
  npm-network:
    external: true
```

**네트워크 이름 변경 주의 (Task 2):**  
이미 운영 중인 서버에서 기존 네트워크 이름이 `saksak_saksak-network`처럼 compose 프로젝트 접두사가 붙어 있으면, `docker compose up -d`만으로는 `saksak-network`로 rename되지 **않을 수** 있습니다.

- 다운타임 허용 시: `docker compose down` 후 `docker compose up -d`로 네트워크를 재생성
- 또는 기존 네트워크를 수동으로 `saksak-network`에 맞춘 뒤 서비스를 재연결

적용 후 확인:

```bash
docker network inspect saksak-network --format '{{.Name}}'
# 출력: saksak-network
```

### 3. 모니터링 환경 변수

앱과 동일하게 **프로젝트 루트 `.env`** 에 아래 키를 추가합니다 (`docker-compose.monitoring.yml`이 `./.env`를 읽음).  
키 목록 참고: `monitoring/.env.example` (복사본을 만들지 말고, 내용을 루트 `.env`에 붙이면 됨).

| 변수 | 설명 |
|------|------|
| `GF_SECURITY_ADMIN_USER` | Grafana admin 계정 |
| `GF_SECURITY_ADMIN_PASSWORD` | Grafana admin 비밀번호 (강력한 값) |
| `DISCORD_WEBHOOK_URL` | Alertmanager → Discord 웹훅 (Jenkins와 동일 URL 가능) |

Postgres exporter는 별도 DSN 없이, 이미 `.env`에 있는 `DB_USER` / `DB_PASSWORD` / `DB_NAME`(`src/core/config.py`와 동일)으로 compose가 `DATA_SOURCE_NAME`을 조립합니다. 호스트는 Docker DNS `saksak-db:5432`입니다.

## 기동 (Start)

`docker-compose.yml`과 `docker-compose.monitoring.yml`이 **같은 디렉터리**에 있는 경로(미니 PC 배포 경로, 예: `DEPLOY_PATH`)에서 실행합니다.

Jenkins 배포(stage 6)가 매 배포마다 아래로 동기화합니다 (모니터링 스택은 **자동 재기동하지 않음**).

- `docker-compose.yml`
- `docker-compose.monitoring.yml`
- `monitoring/` (prometheus·alertmanager·grafana 설정; `.env` 제외)

```bash
docker compose -f docker-compose.monitoring.yml up -d
```

기동되는 서비스: `saksak-prometheus`, `saksak-alertmanager`, `saksak-grafana`, `saksak-node-exporter`, `saksak-cadvisor`, `saksak-postgres-exporter`, `saksak-redis-exporter`.

Prometheus / Alertmanager / exporter는 **호스트 포트를 publish하지 않습니다** (내부 Docker 네트워크 전용).

## Nginx Proxy Manager (NPM)

Grafana만 NPM으로 공개합니다.

| 항목 | 값 |
|------|-----|
| Forward Hostname / IP | `saksak-grafana` |
| Forward Port | `3000` |
| 네트워크 | Grafana 컨테이너가 `npm-network`에 연결되어 있어야 함 |

설정 체크:

- **HTTPS** 사용 (Let's Encrypt 등)
- Grafana admin 비밀번호를 루트 `.env`의 `GF_SECURITY_ADMIN_PASSWORD`로 강력하게 설정
- **프록시하지 않을 것:** Prometheus (`9090`), Alertmanager (`9093`), 앱 `/metrics` (`saksak-back:8000/metrics`)

로컬 디버그가 필요할 때만 compose 주석의 `127.0.0.1:3000:3000` 바인딩을 임시 사용하고, 사용 후 제거합니다.

## 검증 (Verify)

### Grafana 대시보드

1. NPM 경유 HTTPS URL로 Grafana 접속
2. 루트 `.env`의 Grafana admin 계정으로 로그인
3. **Saksak Overview** 대시보드에서 패널에 데이터가 채워지는지 확인 (App up, RPS, CPU/메모리/디스크 등)

스택 기동 직후 scrape interval(15s)만큼 잠시 **No data**일 수 있습니다.

### Prometheus → 앱 `/metrics` scrape

Prometheus 컨테이너 내부에서 앱 메트릭에 접근 가능한지 확인:

```bash
docker exec saksak-prometheus wget -qO- http://saksak-back:8000/metrics | head
```

`http_requests_total` 등 Prometheus 텍스트 포맷이 출력되면 정상입니다.

### Discord 알림

**방법 A — 규칙 임시 완화 (권장):**

1. `monitoring/prometheus/alerts.yml`에서 테스트할 규칙의 `for`를 `0m`으로 변경
2. Prometheus 설정 reload: `docker exec saksak-prometheus wget -qO- --post-data='' http://localhost:9090/-/reload`
3. Discord 채널에 알림 수신 확인
4. `for` 값을 원래대로 복구 후 다시 reload

**방법 B — 앱 중지:**

```bash
docker stop saksak-back
# AppDown 알림 (for: 3m) 대기 후 Discord 확인
docker start saksak-back
```

**방법 C — Alertmanager 테스트 알림** (UI는 비공개이므로 컨테이너 내부 curl 등으로 전송).

검증 후 알림 규칙·앱 상태를 **반드시 원복**합니다.

## 보안 체크리스트

| 항목 | 확인 |
|------|------|
| 인터넷에서 `/metrics` 직접 접근 불가 | NPM에 `/metrics` location 없음, 앱 8000은 API용만 NPM 경유 |
| Prometheus UI (`:9090`) 비공개 | compose에 host port 없음, NPM 미등록 |
| Alertmanager UI (`:9093`) 비공개 | compose에 host port 없음, NPM 미등록 |
| Grafana HTTPS + 강한 admin 비밀번호 | NPM SSL + `GF_SECURITY_ADMIN_PASSWORD` |
| 루트 `.env` / Discord 웹훅 git 미커밋 | `.gitignore`에 `.env` 포함 |
| Jenkins 배포 파이프라인 무변경 | Jenkinsfile 수정 없음, stage 8 헬스체크 유지 |

외부에서 Prometheus/Grafana/metrics 포트에 접속 시도해 차단되는지 한 번 더 확인합니다.

## 중지 / 업데이트 (Stop / Update)

### 모니터링 이미지 업데이트

```bash
docker compose -f docker-compose.monitoring.yml pull
docker compose -f docker-compose.monitoring.yml up -d
```

설정 파일(`monitoring/prometheus/*.yml` 등) 변경 후 Prometheus reload:

```bash
docker exec saksak-prometheus wget -qO- --post-data='' http://localhost:9090/-/reload
```

Grafana provisioning / 대시보드 JSON 변경 시:

```bash
docker compose -f docker-compose.monitoring.yml restart grafana
```

### 모니터링 중지

```bash
docker compose -f docker-compose.monitoring.yml down
```

볼륨(`prometheus_data`, `grafana_data`)을 유지하면 TSDB·Grafana 설정이 보존됩니다. 완전 삭제 시 `docker compose -f docker-compose.monitoring.yml down -v` (주의: 메트릭·대시보드 커스터마이즈 손실).

### 앱 배포와의 관계

Jenkins 또는 수동 앱 배포:

```bash
docker compose up -d app
```

앱 compose만 재기동하며 **모니터링 컨테이너는 재시작되지 않습니다**. 모니터링 스택은 별도 compose로 한 번 기동해 두면 앱 배포와 독립적으로 동작합니다.

## 참고

- 설계 스펙: `docs/superpowers/specs/2026-07-26-runtime-monitoring-design.md`
- Prometheus retention: 15일 (`--storage.tsdb.retention.time=15d`)
- Jenkins Discord(배포 알림)와 Alertmanager Discord(런타임 알림)는 역할이 다릅니다. 같은 웹훅 URL을 써도 됩니다.
