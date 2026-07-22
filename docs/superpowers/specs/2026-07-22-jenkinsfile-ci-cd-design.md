# Saksak Backend Jenkins CI/CD Design

**Date:** 2026-07-22  
**Status:** Approved  
**Scope:** Declarative `Jenkinsfile` for build, test, push, migrate, deploy, health check, Discord notify

## Goal

`main` 브랜치 푸시 시 Jenkins가 동일 배포 서버에서 Docker 이미지를 빌드·검증하고 Docker Hub에 푸시한 뒤, `docker compose`로 app만 재기동한다. 성공·실패를 Discord로 알린다.

## Constraints (decided)

| Topic | Decision |
|---|---|
| Pipeline style | 기존 Declarative `Jenkinsfile` 보강 |
| Trigger | `main` 푸시마다 자동 빌드·배포 |
| Jenkins ↔ deploy host | 동일 머신 (`dir(DEPLOY_PATH)` 로컬 compose) |
| CI checks | `pytest` only (`ruff` 제외) |
| Image tag | `augustzer0/saksak:latest` only |
| Rollback | 자동 롤백 없음 (헬스 실패 시 Failure + Discord) |
| DB migrate | 배포 전 `alembic upgrade head` 포함 |
| Notify | Discord 성공·실패 모두; 실패 시 빌드 URL/콘솔 링크·요약 |

## Architecture

```
GitHub main push
    → Jenkins (same host as prod)
        → Checkout
        → Materialize .env from Secret File
        → docker build :latest
        → docker run … pytest (ephemeral, --group dev)
        → docker push :latest
        → DEPLOY_PATH:
              compose pull app
              compose run --rm app alembic upgrade head
              compose up -d app
              image prune
        → Health check (saksak-back)
        → Discord notify
        → always: rm .env
```

배포용 compose는 서버의 `DEPLOY_PATH`에 두고 app만 갱신한다. Postgres/Redis는 유지한다 (`npm-network` external 등 기존 compose 전제 유지).

## Stages

### 1. Checkout
- Repo: `https://github.com/saksak-recipe/back.git`
- Branch: `main`
- Credential: `github-login`

### 2. Create .env
- Secret File credential `saksak-env-file` → **Jenkins workspace** `.env` (빌드 워크스페이스용; `post`에서 삭제)
- **배포용** `.env`는 `DEPLOY_PATH`에 호스트가 별도 유지한다. 파이프라인이 그 파일을 덮어쓰지 않는다. `compose run` / `up`은 항상 `DEPLOY_PATH`의 `.env`를 쓴다.
- pytest는 `conftest`가 테스트용 env를 기본 세팅하므로 실 DB/Redis·workspace `.env` 불필요

### 3. Build Image
- `docker build -t augustzer0/saksak:latest .`
- Dockerfile: `python:3.14-slim` + `uv sync --frozen` (prod deps)

### 4. Test (pytest)
- Prod 이미지에 dev deps가 없으므로 ephemeral 컨테이너에서만 설치:

```bash
docker run --rm augustzer0/saksak:latest \
  sh -c "uv sync --frozen --group dev --no-cache && uv run pytest"
```

- 실패 시 Push / Migrate / Deploy 중단
- Tests use in-memory SQLite + fakeredis (`tests/conftest.py`)

### 5. Push to Docker Hub
- Credential: `dockerhub-login` (username/password)
- `docker login` → `docker push augustzer0/saksak:latest`
- Prefer `docker logout` in post/cleanup path

### 6. Migrate
At `DEPLOY_PATH` (e.g. `/home/augustzer0/zer0/saksak`):

```bash
docker compose pull app
docker compose run --rm app uv run alembic upgrade head
```

- Relies on compose `depends_on` + Postgres/Redis healthchecks
- Migrate failure → do **not** run `up -d app`; mark Failure + Discord

### 7. Deploy
```bash
docker compose up -d app
docker image prune -f
```

- App service only; DB/Redis undisturbed

### 8. Health Check
- Short wait, then verify FastAPI inside `saksak-back` (e.g. HTTP to `localhost:8000`)
- Failure → pipeline Failure, no auto-rollback

## Discord notification

### Credential
- New Jenkins Secret text: `discord-webhook-url`
- Never echo webhook URL in logs

### Payload
- **Success:** job name, build number, duration, `BUILD_URL`
- **Failure:** same + short failure summary + console link (`${BUILD_URL}console`)
- Do **not** paste full console log into Discord (size + secret risk)

### Delivery
- `post { success }` / `post { failure }` via `curl` POST to webhook (JSON embed or content string)
- Implementation detail left to plan; keep Jenkinsfile self-contained (no shared library)

## Credentials summary

| Credential ID | Type | Purpose |
|---|---|---|
| `github-login` | existing | Git checkout |
| `dockerhub-login` | existing | Docker Hub push |
| `saksak-env-file` | existing Secret File | Workspace `.env` |
| `discord-webhook-url` | **new** Secret text | Discord webhook |

## Environment (Jenkinsfile)

```
GIT_URL          = https://github.com/saksak-recipe/back.git
DOCKER_IMAGE     = augustzer0/saksak
GIT_CRED_ID      = github-login
DOCKER_CRED_ID   = dockerhub-login
ENV_CRED_ID      = saksak-env-file
DISCORD_CRED_ID  = discord-webhook-url
DEPLOY_PATH      = /home/augustzer0/zer0/saksak
```

## Error handling & cleanup

| Event | Behavior |
|---|---|
| pytest fail | abort before push |
| migrate fail | abort before `up -d app` |
| health fail | Failure + Discord; leave current containers as-is (manual recovery) |
| always | `rm -f .env` in workspace |
| optional | `docker logout` after push path |

## Out of scope

- `ruff` in CI
- Image tags other than `:latest`
- Automatic rollback / blue-green
- Separate CI vs CD Jenkins jobs
- SSH remote deploy
- Changing `Dockerfile` multi-stage for test (ephemeral `uv sync --group dev` is enough)
- Committing server `docker-compose.yml` into git (remains deploy-host / gitignored concern)

## Success criteria

1. `main` push runs full pipeline on the deploy host Jenkins agent
2. pytest must pass before Hub push
3. alembic runs against prod DB before app recreate
4. app container healthy after deploy
5. Discord receives success and failure messages; failures include console link
6. Workspace `.env` is removed after every run
