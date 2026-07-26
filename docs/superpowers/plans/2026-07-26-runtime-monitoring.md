# Runtime Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 미니 PC에서 Prometheus/Grafana/Alertmanager로 삭삭 백엔드 런타임을 관측하고, 임계치 초과 시 Discord로 알린다.

**Architecture:** 앱에 `/metrics`를 추가하고, 별도 `docker-compose.monitoring.yml`이 `saksak-network`에 붙어 scrape한다. Grafana만 NPM으로 노출하고 `/metrics`·Prometheus·Alertmanager는 비공개다. Jenkins 배포 파이프라인은 변경하지 않는다.

**Tech Stack:** FastAPI, `prometheus-fastapi-instrumentator`, Docker Compose, Prometheus, Grafana, Alertmanager (discord_configs), node-exporter, cAdvisor, postgres-exporter, redis-exporter

**Spec:** `docs/superpowers/specs/2026-07-26-runtime-monitoring-design.md`

## Global Constraints

- Host: **기존 미니 PC** (Docker + NPM + Jenkins 유지)
- Compose: **별도** `docker-compose.monitoring.yml` (앱 배포와 수명주기 분리)
- App metrics: **`prometheus-fastapi-instrumentator`** → `GET /metrics`
- `/metrics`: **내부 Docker 네트워크만** — NPM 공개 금지
- Grafana: NPM + 기본 인증; Prometheus/Alertmanager **비공개**
- Discord: Alertmanager → 웹훅 (URL은 git에 커밋 금지)
- Out of scope: 롤백, 백업, AWS/IaC, Jenkinsfile 변경, 로그 스택
- 커밋은 **유저 요청 시에만** (스텝에 있어도 요청 전 skip)

---

## File Structure

| 동작 | 경로 | 책임 |
|------|------|------|
| Modify | `pyproject.toml` / `uv.lock` | `prometheus-fastapi-instrumentator` 의존성 |
| Modify | `src/main.py` | Instrumentator로 `/metrics` 노출 |
| Create | `tests/api/test_metrics_endpoint.py` | `/metrics` 응답 검증 |
| Modify | `docker-compose.yml` | `saksak-network`에 고정 `name` (모니터링이 external로 join) |
| Create | `docker-compose.monitoring.yml` | 모니터링 스택 전체 |
| Create | `monitoring/prometheus/prometheus.yml` | scrape 설정 |
| Create | `monitoring/prometheus/alerts.yml` | 알림 규칙 |
| Create | `monitoring/alertmanager/alertmanager.yml` | Discord 라우팅 (웹훅은 파일로 주입) |
| Create | `monitoring/grafana/provisioning/datasources/datasource.yml` | Prometheus datasource |
| Create | `monitoring/grafana/provisioning/dashboards/dashboards.yml` | 대시보드 provider |
| Create | `monitoring/grafana/dashboards/saksak-overview.json` | 개요 대시보드 |
| Create | `monitoring/.env.example` | Grafana/Discord/DB DSN 키 목록 |
| Create | `docs/ops-runtime-monitoring.md` | 미니 PC 기동·NPM·검증 절차 |
| Modify | `.gitignore` | `monitoring/.env` 무시 |

---

### Task 1: FastAPI `/metrics` 엔드포인트

**Files:**
- Modify: `pyproject.toml` (dependency)
- Modify: `uv.lock` (via `uv add`)
- Modify: `src/main.py`
- Create: `tests/api/test_metrics_endpoint.py`

**Interfaces:**
- Produces: `GET /metrics` (Prometheus text exposition, `include_in_schema=False`)
- Produces metrics used by alerts: `http_requests_total`, `http_request_duration_seconds_bucket` (instrumentator defaults)
- Consumes: existing `app = FastAPI(lifespan=lifespan)` in `src/main.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_metrics_endpoint.py`:

```python
from httpx import AsyncClient


async def test_metrics_endpoint_exposes_prometheus_text(client: AsyncClient):
    # hit a known route so at least one request is recorded
    await client.get("/")
    response = await client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "http_requests_total" in body or "http_request" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/api/test_metrics_endpoint.py -v`

Expected: FAIL (404 on `/metrics` or missing metric names)

- [ ] **Step 3: Add dependency**

Run: `uv add prometheus-fastapi-instrumentator`

Expected: `pyproject.toml` / `uv.lock` updated

- [ ] **Step 4: Instrument the app**

In `src/main.py`, after `app = FastAPI(lifespan=lifespan)` (and after routers/handlers are attached is fine; instrumentator docs allow instrument+expose after app creation). Add:

```python
from prometheus_fastapi_instrumentator import Instrumentator

# ... existing app setup including routers/middleware ...

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
```

Place the `Instrumentator` call **after** `app.include_router(...)` and middleware registration so routes exist; expose still adds `/metrics` on the same app.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/api/test_metrics_endpoint.py -v`

Expected: PASS

Also run: `uv run pytest -q` — existing suite must still pass (Jenkins stage 4).

- [ ] **Step 6: Commit** (유저 요청 시에만)

```bash
git add pyproject.toml uv.lock src/main.py tests/api/test_metrics_endpoint.py
git commit -m "$(cat <<'EOF'
feat(monitoring): FastAPI /metrics 엔드포인트 추가

Prometheus scrape용 HTTP 메트릭을 내부 관측 경로로 노출한다.
EOF
)"
```

---

### Task 2: 공유 네트워크 이름 고정

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: Docker network name exactly `saksak-network` (no compose project prefix)
- Consumes: existing `saksak-network` / `npm-network` usage by `app` / `postgresql` / `redis`

- [ ] **Step 1: Set explicit network name**

In `docker-compose.yml`, change the networks section to:

```yaml
networks:
  saksak-network:
    name: saksak-network
  npm-network:
    external: true
```

Do **not** change service definitions, ports, volumes, or healthchecks.

- [ ] **Step 2: Spec checklist**

- [ ] App compose still defines `saksak-network` and `npm-network`
- [ ] Monitoring compose (Task 3) can `external: true` + `name: saksak-network`
- [ ] Jenkinsfile unchanged

- [ ] **Step 3: Commit** (유저 요청 시에만)

```bash
git add docker-compose.yml
git commit -m "$(cat <<'EOF'
chore(compose): saksak-network 고정 이름으로 모니터링 join 가능하게

EOF
)"
```

**Ops note (document in Task 5):** 이미 떠 있는 서버에서 네트워크 이름이 `saksak_saksak-network` 등이면, 최초 적용 시 `docker compose down` 없이 network rename이 안 될 수 있다. 다운타임 허용 시 `docker compose down` 후 `up -d`로 재생성하거나, 기존 네트워크를 `saksak-network`로 맞춘다.

---

### Task 3: Monitoring compose + Prometheus/Alertmanager 설정

**Files:**
- Create: `docker-compose.monitoring.yml`
- Create: `monitoring/prometheus/prometheus.yml`
- Create: `monitoring/prometheus/alerts.yml`
- Create: `monitoring/alertmanager/alertmanager.yml`
- Create: `monitoring/.env.example`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: containers `saksak-back:8000`, `saksak-db:5432`, `saksak-redis:6379` on `saksak-network`
- Consumes: env `DISCORD_WEBHOOK_URL`, `GF_SECURITY_ADMIN_PASSWORD`, `DATA_SOURCE_NAME` (postgres exporter)
- Produces: scrape of `/metrics`, host/container/DB/Redis exporters; Discord via Alertmanager `discord_configs` + `webhook_url_file`

- [ ] **Step 1: Add `monitoring/.env` to gitignore**

Append to `.gitignore` if not present:

```
monitoring/.env
```

- [ ] **Step 2: Create `monitoring/.env.example`**

```env
# Copy to monitoring/.env on the mini PC (do not commit)

GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=change-me-strong-password

# Same Discord webhook as Jenkins is fine
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/REPLACE/ME

# Postgres exporter (use existing app DB user for YAGNI; optional later: read-only monitor user)
# Format: postgresql://USER:PASSWORD@saksak-db:5432/saksak?sslmode=disable
DATA_SOURCE_NAME=postgresql://USER:PASSWORD@saksak-db:5432/saksak?sslmode=disable
```

- [ ] **Step 3: Create Prometheus config**

`monitoring/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - /etc/prometheus/alerts.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

scrape_configs:
  - job_name: saksak-app
    metrics_path: /metrics
    static_configs:
      - targets: ["saksak-back:8000"]

  - job_name: node
    static_configs:
      - targets: ["node-exporter:9100"]

  - job_name: cadvisor
    static_configs:
      - targets: ["cadvisor:8080"]

  - job_name: postgres
    static_configs:
      - targets: ["postgres-exporter:9187"]

  - job_name: redis
    static_configs:
      - targets: ["redis-exporter:9121"]
```

- [ ] **Step 4: Create alert rules**

`monitoring/prometheus/alerts.yml`:

```yaml
groups:
  - name: saksak-runtime
    rules:
      - alert: AppDown
        expr: up{job="saksak-app"} == 0
        for: 3m
        labels:
          severity: critical
        annotations:
          summary: "saksak app /metrics target down ≥ 3m"

      - alert: High5xx
        expr: |
          (
            sum(rate(http_requests_total{job="saksak-app",status=~"5.."}[5m]))
            /
            clamp_min(sum(rate(http_requests_total{job="saksak-app"}[5m])), 0.001)
          ) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "saksak 5xx rate > 5% (5m)"

      - alert: HighLatency
        expr: |
          histogram_quantile(
            0.95,
            sum(rate(http_request_duration_seconds_bucket{job="saksak-app"}[5m])) by (le)
          ) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "saksak HTTP p95 latency > 2s (5m)"

      - alert: PostgresDown
        expr: up{job="postgres"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "postgres-exporter target down ≥ 1m"

      - alert: RedisDown
        expr: up{job="redis"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "redis-exporter target down ≥ 1m"

      - alert: DiskHigh
        expr: |
          (
            1 - (
              node_filesystem_avail_bytes{fstype!~"tmpfs|overlay",mountpoint="/"}
              /
              node_filesystem_size_bytes{fstype!~"tmpfs|overlay",mountpoint="/"}
            )
          ) > 0.85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "host disk usage > 85%"

      - alert: MemoryHigh
        expr: |
          (
            1 - (
              node_memory_MemAvailable_bytes
              /
              node_memory_MemTotal_bytes
            )
          ) > 0.90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "host memory usage > 90%"
```

If instrumentator uses label `status_code` instead of `status`, adjust `High5xx` after first scrape inspection (`curl` `/metrics` once). Prefer matching whatever labels appear in Task 1 test output.

- [ ] **Step 5: Create Alertmanager config**

`monitoring/alertmanager/alertmanager.yml`:

```yaml
global:
  resolve_timeout: 5m

route:
  receiver: discord
  group_by: ["alertname"]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: discord
    discord_configs:
      - webhook_url_file: /etc/alertmanager/discord_webhook_url
        send_resolved: true
        title: '{{ template "discord.default.title" . }}'
        message: |
          {{ range .Alerts }}
          **{{ .Labels.alertname }}** ({{ .Labels.severity }})
          {{ .Annotations.summary }}
          {{ end }}

inhibit_rules:
  - source_matchers: [severity="critical"]
    target_matchers: [severity="warning"]
    equal: ["alertname"]
```

- [ ] **Step 6: Create `docker-compose.monitoring.yml`**

```yaml
services:
  prometheus:
    image: prom/prometheus:v2.54.1
    container_name: saksak-prometheus
    restart: unless-stopped
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.retention.time=15d
      - --web.enable-lifecycle
    volumes:
      - ./monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./monitoring/prometheus/alerts.yml:/etc/prometheus/alerts.yml:ro
      - prometheus_data:/prometheus
    networks:
      - saksak-network
    # no host ports — internal only

  alertmanager:
    image: prom/alertmanager:v0.27.0
    container_name: saksak-alertmanager
    restart: unless-stopped
    env_file:
      - ./monitoring/.env
    entrypoint: ["/bin/sh", "-c"]
    command:
      - |
        printf '%s' "$$DISCORD_WEBHOOK_URL" > /etc/alertmanager/discord_webhook_url
        exec /bin/alertmanager --config.file=/etc/alertmanager/alertmanager.yml
    volumes:
      - ./monitoring/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
    networks:
      - saksak-network

  grafana:
    image: grafana/grafana:11.2.0
    container_name: saksak-grafana
    restart: unless-stopped
    env_file:
      - ./monitoring/.env
    environment:
      GF_USERS_ALLOW_SIGN_UP: "false"
      GF_AUTH_ANONYMOUS_ENABLED: "false"
      GF_SERVER_ROOT_URL: "%(protocol)s://%(domain)s/"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards:ro
    networks:
      - saksak-network
      - npm-network
    # Prefer NPM proxy over publishing 3000 publicly.
    # Optional local debug only: "127.0.0.1:3000:3000"

  node-exporter:
    image: prom/node-exporter:v1.8.2
    container_name: saksak-node-exporter
    restart: unless-stopped
    pid: host
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - --path.procfs=/host/proc
      - --path.sysfs=/host/sys
      - --path.rootfs=/rootfs
      - --collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)
    networks:
      - saksak-network

  cadvisor:
    image: gcr.io/cadvisor/cadvisor:v0.49.1
    container_name: saksak-cadvisor
    restart: unless-stopped
    privileged: true
    devices:
      - /dev/kmsg:/dev/kmsg
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:ro
      - /sys:/sys:ro
      - /var/lib/docker/:/var/lib/docker:ro
    networks:
      - saksak-network

  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:v0.15.0
    container_name: saksak-postgres-exporter
    restart: unless-stopped
    env_file:
      - ./monitoring/.env
    networks:
      - saksak-network

  redis-exporter:
    image: oliver006/redis_exporter:v1.62.0
    container_name: saksak-redis-exporter
    restart: unless-stopped
    environment:
      REDIS_ADDR: redis://saksak-redis:6379
    networks:
      - saksak-network

networks:
  saksak-network:
    external: true
    name: saksak-network
  npm-network:
    external: true

volumes:
  prometheus_data:
  grafana_data:
```

- [ ] **Step 7: Validate compose file syntax locally**

Run: `docker compose -f docker-compose.monitoring.yml config`

Expected: rendered YAML without errors (may warn if `monitoring/.env` missing — create a throwaway local copy from `.env.example` for the check, do not commit secrets).

- [ ] **Step 8: Commit** (유저 요청 시에만)

```bash
git add docker-compose.monitoring.yml monitoring/ .gitignore
git commit -m "$(cat <<'EOF'
feat(monitoring): Prometheus/Grafana/Alertmanager compose 스택 추가

앱 배포와 분리된 런타임 관측·Discord 알림 기반을 둔다.
EOF
)"
```

---

### Task 4: Grafana datasource + 개요 대시보드

**Files:**
- Create: `monitoring/grafana/provisioning/datasources/datasource.yml`
- Create: `monitoring/grafana/provisioning/dashboards/dashboards.yml`
- Create: `monitoring/grafana/dashboards/saksak-overview.json`

**Interfaces:**
- Consumes: Prometheus at `http://prometheus:9090`
- Produces: provisioned dashboard "Saksak Overview" with app/host/dependency panels

- [ ] **Step 1: Datasource provisioning**

`monitoring/grafana/provisioning/datasources/datasource.yml`:

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

- [ ] **Step 2: Dashboard provider**

`monitoring/grafana/provisioning/dashboards/dashboards.yml`:

```yaml
apiVersion: 1
providers:
  - name: saksak
    orgId: 1
    folder: Saksak
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    options:
      path: /var/lib/grafana/dashboards
```

- [ ] **Step 3: Overview dashboard JSON**

Create `monitoring/grafana/dashboards/saksak-overview.json` as a Grafana 11-compatible dashboard with at least these panels (Prometheus queries):

| Panel | Query |
|-------|-------|
| App up | `up{job="saksak-app"}` |
| RPS | `sum(rate(http_requests_total{job="saksak-app"}[5m]))` |
| 5xx rate | `sum(rate(http_requests_total{job="saksak-app",status=~"5.."}[5m])) / clamp_min(sum(rate(http_requests_total{job="saksak-app"}[5m])), 0.001)` |
| p95 latency | `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="saksak-app"}[5m])) by (le))` |
| Postgres up | `up{job="postgres"}` |
| Redis up | `up{job="redis"}` |
| CPU % | `100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)` |
| Memory % | `(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100` |
| Disk % `/` | `(1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100` |

Minimal valid skeleton (expand panels to match table; keep `uid: saksak-overview`, `title: Saksak Overview`):

```json
{
  "uid": "saksak-overview",
  "title": "Saksak Overview",
  "timezone": "Asia/Seoul",
  "schemaVersion": 39,
  "version": 1,
  "refresh": "30s",
  "panels": [],
  "templating": { "list": [] },
  "annotations": { "list": [] },
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 1,
  "links": [],
  "liveNow": false,
  "weekStart": ""
}
```

Implementer must fill `panels` with real panel objects (timeseries/stat) using the queries above — empty `panels: []` is not acceptable for merge.

- [ ] **Step 4: Commit** (유저 요청 시에만)

```bash
git add monitoring/grafana/
git commit -m "$(cat <<'EOF'
feat(monitoring): Grafana 프로비저닝·개요 대시보드 추가

EOF
)"
```

---

### Task 5: 운영 문서 + 로컬/서버 검증 체크리스트

**Files:**
- Create: `docs/ops-runtime-monitoring.md`

**Interfaces:**
- Documents: network rename caveat (Task 2), `.env` setup, compose up, NPM Grafana proxy, Discord test, security checklist
- Does **not** change Jenkinsfile

- [ ] **Step 1: Write ops doc**

`docs/ops-runtime-monitoring.md` must include:

1. **Prep**
   - App stack running (`saksak-back`, `saksak-db`, `saksak-redis`)
   - `docker-compose.yml` with `name: saksak-network` applied
   - `cp monitoring/.env.example monitoring/.env` and fill secrets
2. **Start**
   - From repo/deploy path that contains both compose files:
     `docker compose -f docker-compose.monitoring.yml up -d`
3. **NPM**
   - Proxy host → `saksak-grafana:3000` (same `npm-network`)
   - HTTPS + strong Grafana password
   - Do **not** proxy Prometheus (`9090`), Alertmanager (`9093`), or app `/metrics`
4. **Verify**
   - Grafana login → Saksak Overview panels populate
   - `docker exec saksak-prometheus wget -qO- http://saksak-back:8000/metrics | head`
   - Discord: temporarily set an alert `for: 0m` / stop app 3+ minutes / or Alertmanager test — then restore rules
5. **Security checklist** (from spec success criteria)
   - Public internet cannot reach `/metrics` or Prometheus UI
   - Jenkins deploy still works unchanged
6. **Stop / update**
   - `docker compose -f docker-compose.monitoring.yml pull && up -d`
   - App deploy (`compose up -d app`) must not restart monitoring

- [ ] **Step 2: Commit** (유저 요청 시에만)

```bash
git add docs/ops-runtime-monitoring.md
git commit -m "$(cat <<'EOF'
docs: 런타임 모니터링 운영 절차 추가

EOF
)"
```

---

## Spec coverage (self-review)

| Spec requirement | Task |
|------------------|------|
| Separate monitoring compose | Task 3 |
| `/metrics` via instrumentator | Task 1 |
| Internal-only metrics | Task 3 (no ports) + Task 5 (NPM note) |
| Grafana via NPM + auth | Task 3 + Task 5 |
| Prometheus/Alertmanager private | Task 3 |
| Discord via Alertmanager | Task 3 |
| Exporters: node/cAdvisor/postgres/redis | Task 3 |
| Alert rules (AppDown, 5xx, latency, PG/Redis, disk, mem) | Task 3 |
| Retention 15d | Task 3 prometheus command |
| Dashboards | Task 4 |
| Ops / success criteria | Task 5 |
| Jenkins unchanged | Global + Task 5 |
| No AWS/rollback/backup | Global Constraints |

## Placeholder / consistency notes

- Metric label `status` vs `status_code`: verify against live `/metrics` in Task 1; align alerts + dashboard queries.
- Alertmanager image must support `discord_configs` (v0.27.0 does).
- `DATA_SOURCE_NAME` uses app DB user for YAGNI; read-only role is optional later, not required to ship.
