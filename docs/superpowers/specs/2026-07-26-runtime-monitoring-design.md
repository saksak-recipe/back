# Saksak Backend Runtime Monitoring Design

**Date:** 2026-07-26  
**Status:** Approved  
**Scope:** Mini PC self-hosted Prometheus / Grafana / Alertmanager + Discord runtime alerts (not deploy-time)

## Goal

미니 PC에서 삭삭 백엔드의 **상시 런타임** 상태를 사람이 Grafana로 보고, 이상 임계치면 Discord로 알린다. Jenkins 배포 파이프라인의 헬스체크·배포 Discord와 역할을 분리한다.

## Constraints (decided)

| Topic | Decision |
|---|---|
| Host | 기존 미니 PC (Docker + Nginx Proxy Manager + Jenkins 유지) |
| Stack | Prometheus + Grafana + Alertmanager |
| Compose layout | **별도** `docker-compose.monitoring.yml` (앱 compose와 수명주기 분리) |
| App metrics | FastAPI에 `/metrics` 추가 (`prometheus-fastapi-instrumentator`) |
| `/metrics` exposure | **내부 Docker 네트워크만** — NPM 공개 금지 |
| Grafana exposure | NPM으로만 (기본 인증). Prometheus/Alertmanager는 비공개 |
| Notify | Alertmanager → Discord 웹훅 (기존 Jenkins credential 재사용 가능) |
| Judgment | 사람이 대시보드·알림을 보고 판단·대응 (자동 치유/롤백 없음) |
| Out of scope | 롤백, 백업, AWS/IaC, Lambda, Jenkins 대수술, 로그 집 bulk(ELK 등) |

## Relationship to Jenkins

| | Jenkins (기존) | 이번 모니터링 |
|--|----------------|----------------|
| When | 배포할 때만 | 24시간 |
| What | 빌드/테스트/배포 + 컨테이너 `/` 헬스 | 업타임 + 리소스 + 5xx·지연·DB/Redis |
| Discord | 파이프라인 성공/실패 | 런타임 임계치 초과 |

Jenkins stage 8 헬스체크는 유지한다. 대체하지 않는다.

## Architecture

```
[Mini PC]

saksak compose                    monitoring compose (분리)
├ app (saksak-back)               ├ prometheus          (scrape)
│   /metrics — 내부만  ◄──────────┤
├ postgresql (saksak-db)  ◄───────┤ postgres-exporter
├ redis (saksak-redis)    ◄───────┤ redis-exporter
│                                 ├ node-exporter       (host CPU/mem/disk)
│                                 ├ cadvisor            (container resources)
│                                 ├ grafana             (사람용 대시보드)
│                                 └ alertmanager ──► Discord webhook

NPM: Grafana만 프록시 (인증 필수)
     /metrics, :9090, :9093 공개하지 않음
```

네트워크: monitoring 스택이 `saksak-network`(또는 공유 external)에 붙어 app/DB/Redis를 scrape한다. `npm-network`에는 Grafana만 필요 시 연결.

## Components

### 1. App (`/metrics`)

- 의존성: `prometheus-fastapi-instrumentator` (또는 동등)
- `src/main.py`에서 instrument → `GET /metrics` (Prometheus text format)
- 수집: 요청수, 상태코드, 지연(histogram) 등 기본 HTTP 메트릭
- 인증 없음 (내부망 전제). NPM에 `/metrics` location 추가하지 않음
- `GET /` 헬스는 Jenkins·외부 프로브용으로 유지

### 2. Monitoring compose services

| Service | Role |
|---------|------|
| prometheus | scrape + 규칙 평가 |
| alertmanager | 라우팅 → Discord |
| grafana | 대시보드 |
| node-exporter | 호스트 CPU/메모리/디스크 |
| cadvisor | 컨테이너 CPU/메모리 |
| postgres-exporter | Postgres up / 기본 DB 메트릭 |
| redis-exporter | Redis up / 기본 Redis 메트릭 |

설정·대시보드 JSON은 레포의 `monitoring/` (가칭) 아래에 버전 관리한다.  
기동은 서버에서 `docker compose -f docker-compose.monitoring.yml up -d` (Jenkins 배포 경로에 자동 포함하지 않음).

### 3. Scrape targets (초안)

- `saksak-back:8000/metrics`
- `node-exporter:9100`
- `cadvisor:8080` (이미지 기본 포트에 맞춤)
- `postgres-exporter:9187`
- `redis-exporter:9121`

### 4. Grafana dashboards (초안)

- App: RPS, p95 latency, 5xx rate, target up
- Host: CPU, memory, disk
- Containers: app / postgres / redis 리소스
- Dependencies: Postgres/Redis exporter up

### 5. Alert rules → Discord

초기 규칙 (숫자는 Grafana/Prometheus에서 조정 가능):

| Alert | Condition (초안) |
|-------|------------------|
| AppDown | app `/metrics` 또는 타겟 down ≥ 3m |
| High5xx | 5xx rate 5m avg > 5% |
| HighLatency | HTTP p95 > 2s (5m) |
| PostgresDown | postgres-exporter/타겟 down ≥ 1m |
| RedisDown | redis-exporter/타겟 down ≥ 1m |
| DiskHigh | 디스크 사용률 > 85% |
| MemoryHigh | 메모리 사용률 > 90% |

Discord 메시지: 알림 이름 + 요약 + (가능하면) Grafana 링크.  
배포용 Jenkins Discord와 같은 웹훅을 써도 되고, 채널 분리는 운영 선택사항이다.

## Security

- `/metrics`, Prometheus, Alertmanager: 호스트 포트 바인딩 최소화 또는 localhost/내부 전용. NPM에 올리지 않음
- Grafana: 강한 admin 비밀번호 + NPM HTTPS. 익명 접근 비활성
- Discord 웹훅 URL: 환경변수/시크릿 파일로만 (git에 커밋 금지)
- DB exporter 계정: 가능하면 읽기 전용 모니터링 유저 (구현 계획에서 확정)

## Ops notes

- 모니터링 compose는 앱 배포와 독립. 앱 `docker compose up -d app`이 모니터링을 재시작하지 않음
- 디스크: Prometheus retention 기본 짧게 (예: 15d) — 미니 PC 용량 고려
- 알림 폭주 시: Alertmanager group/inhibit로 묶고, 임계치는 실제 트래픽 보고 완화

## Non-goals (this change)

- 자동 롤백 / blue-green
- DB 백업·복구
- AWS·Terraform·Lambda
- 중앙 로그 스택 (Loki/ELK) — 필요 시 별도 스펙
- Jenkinsfile에 모니터링 스택 배포 자동화 (수동 기동으로 충분)

## Success criteria

1. Grafana에서 앱·호스트·DB/Redis 상태를 한눈에 볼 수 있다
2. 위 알림 규칙이 Discord로 전달된다 (테스트 알림 또는 의도적 down으로 검증)
3. 인터넷에서 `/metrics`·Prometheus UI에 접근할 수 없다
4. 기존 Jenkins 배포·헬스체크·배포 Discord가 깨지지 않는다
