# Jenkinsfile CI/CD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Declarative `Jenkinsfile`로 `main` 푸시 시 빌드 → pytest → Docker Hub 푸시 → alembic → compose app 재기동 → 헬스체크 → Discord 성공/실패 알림을 수행한다.

**Architecture:** 배포 서버와 동일 머신의 Jenkins agent에서 로컬 `docker`/`docker compose`를 실행한다. 이미지는 `augustzer0/saksak:latest`만 사용한다. 배포용 `.env`는 `DEPLOY_PATH`에 호스트가 유지하고, 워크스페이스 `.env`는 Secret File로 만든 뒤 `post`에서 삭제한다.

**Tech Stack:** Jenkins Declarative Pipeline, Docker, Docker Compose, uv/pytest (이미지 내부), Discord Incoming Webhook, Alembic

**Spec:** `docs/superpowers/specs/2026-07-22-jenkinsfile-ci-cd-design.md`

## Global Constraints

- Pipeline style: **기존 Declarative `Jenkinsfile` 보강** (단일 파일)
- Trigger 전제: **`main` 푸시마다 자동** (Jenkins Job 트리거는 운영 설정; 코드는 `main` checkout)
- Jenkins ↔ deploy: **동일 머신** (`dir(DEPLOY_PATH)`)
- CI: **`pytest` only** (`ruff` 없음)
- Image tag: **`augustzer0/saksak:latest` only**
- Rollback: **자동 롤백 없음**
- Migrate: **`alembic upgrade head` before `up -d app`**
- Discord: **성공·실패 모두**; 실패 시 **빌드 URL + console 링크 + 짧은 요약** (전체 로그 첨부 금지)
- Webhook URL: Credential `discord-webhook-url`만 사용, **로그에 출력 금지**
- `DEPLOY_PATH`의 `.env`를 파이프라인이 **덮어쓰지 않음**
- Dockerfile multi-stage 변경 **없음**
- 커밋은 유저 요청 시에만 (스텝에 있어도 요청 전 skip)

---

## File Structure

| 동작 | 경로 | 책임 |
|------|------|------|
| Create/Replace | `Jenkinsfile` | 전체 CI/CD 파이프라인 |
| Unchanged | `Dockerfile` | prod `uv sync --frozen` 유지 |
| Unchanged (host) | `$DEPLOY_PATH/docker-compose.yml` | 서버에만 존재; app/postgres/redis |
| Ops (manual) | Jenkins Credentials | `discord-webhook-url` Secret text 신규 등록 |

---

### Task 1: Jenkinsfile skeleton — env, checkout, workspace .env, always cleanup

**Files:**
- Create/Replace: `Jenkinsfile`

**Interfaces:**
- Produces env keys: `GIT_URL`, `DOCKER_IMAGE`, `GIT_CRED_ID`, `DOCKER_CRED_ID`, `ENV_CRED_ID`, `DISCORD_CRED_ID`, `DEPLOY_PATH`
- Produces stages: `1. Checkout`, `2. Create .env File`
- Produces `post.always` → `rm -f .env`

- [ ] **Step 1: Write `Jenkinsfile` with skeleton only** (later stages as placeholders that `error` so incomplete pipeline cannot silently “succeed”)

```groovy
pipeline {
    agent any

    environment {
        GIT_URL = 'https://github.com/saksak-recipe/back.git'
        DOCKER_IMAGE = 'augustzer0/saksak'
        GIT_CRED_ID = 'github-login'
        DOCKER_CRED_ID = 'dockerhub-login'
        ENV_CRED_ID = 'saksak-env-file'
        DISCORD_CRED_ID = 'discord-webhook-url'
        DEPLOY_PATH = '/home/augustzer0/zer0/saksak'
    }

    stages {
        stage('1. Checkout') {
            steps {
                echo 'Checkout saksak-recipe/back main'
                git branch: 'main', credentialsId: "${GIT_CRED_ID}", url: "${GIT_URL}"
            }
        }

        stage('2. Create .env File') {
            steps {
                script {
                    echo 'Materialize workspace .env from Secret File (not DEPLOY_PATH)'
                    withCredentials([file(credentialsId: "${ENV_CRED_ID}", variable: 'SECRET_ENV')]) {
                        sh 'cp "$SECRET_ENV" .env'
                    }
                }
            }
        }

        stage('3. Build Image') {
            steps { error('TODO Task 2: Build Image') }
        }
    }

    post {
        always {
            echo 'Remove workspace .env'
            sh 'rm -f .env'
        }
    }
}
```

- [ ] **Step 2: Spec checklist (partial)**

Confirm in `Jenkinsfile`:
- [ ] `DISCORD_CRED_ID = 'discord-webhook-url'`
- [ ] `DEPLOY_PATH = '/home/augustzer0/zer0/saksak'`
- [ ] Checkout uses `main` + `github-login`
- [ ] Workspace `.env` only; no `cp` into `DEPLOY_PATH`
- [ ] `post.always` deletes `.env`

- [ ] **Step 3: Commit** (유저 요청 시에만)

```bash
git add Jenkinsfile
git commit -m "$(cat <<'EOF'
feat: add Jenkinsfile skeleton for CI/CD

EOF
)"
```

---

### Task 2: Build + pytest stages

**Files:**
- Modify: `Jenkinsfile` — replace placeholder stage 3; add stage 4

**Interfaces:**
- Consumes: `DOCKER_IMAGE`
- Produces: local image `augustzer0/saksak:latest`
- Produces: pytest must pass before later stages run

- [ ] **Step 1: Replace Build + Test stages**

Remove `error('TODO Task 2...')` and insert:

```groovy
        stage('3. Build Image') {
            steps {
                echo "Build ${DOCKER_IMAGE}:latest"
                sh "docker build -t ${DOCKER_IMAGE}:latest ."
            }
        }

        stage('4. Test (pytest)') {
            steps {
                echo 'Run pytest inside ephemeral container (dev group)'
                sh """
                    docker run --rm ${DOCKER_IMAGE}:latest \
                      sh -c "uv sync --frozen --group dev --no-cache && uv run pytest"
                """
            }
        }

        stage('5. Push to Docker Hub') {
            steps { error('TODO Task 3: Push') }
        }
```

Notes:
- Do **not** use `--env-file .env` for pytest (`conftest` sets test env; in-memory SQLite + fakeredis).
- Do **not** add `ruff`.
- No `try/catch` that swallows failures — let `sh` fail the stage.

- [ ] **Step 2: Local sanity (optional, on machine with Docker)**

```bash
docker build -t augustzer0/saksak:latest .
docker run --rm augustzer0/saksak:latest \
  sh -c "uv sync --frozen --group dev --no-cache && uv run pytest"
```

Expected: pytest exit 0 (or known test failures fixed separately — pipeline must still wire the command exactly as above).

- [ ] **Step 3: Commit** (유저 요청 시에만)

```bash
git add Jenkinsfile
git commit -m "$(cat <<'EOF'
feat: add Docker build and pytest stages to Jenkinsfile

EOF
)"
```

---

### Task 3: Push, migrate, deploy, health check

**Files:**
- Modify: `Jenkinsfile` — stages 5–8

**Interfaces:**
- Consumes: `DOCKER_CRED_ID`, `DOCKER_IMAGE`, `DEPLOY_PATH`
- Produces: Hub `:latest` updated
- Produces: `alembic upgrade head` then `compose up -d app`
- Produces: health check via `docker exec saksak-back`

- [ ] **Step 1: Replace Push/Migrate/Deploy/Health stages**

```groovy
        stage('5. Push to Docker Hub') {
            steps {
                script {
                    echo "Push ${DOCKER_IMAGE}:latest"
                    withCredentials([usernamePassword(
                        credentialsId: "${DOCKER_CRED_ID}",
                        usernameVariable: 'DOCKER_USER',
                        passwordVariable: 'DOCKER_PW'
                    )]) {
                        sh 'echo "$DOCKER_PW" | docker login -u "$DOCKER_USER" --password-stdin'
                        sh "docker push ${DOCKER_IMAGE}:latest"
                    }
                }
            }
        }

        stage('6. Migrate (alembic)') {
            steps {
                dir("${DEPLOY_PATH}") {
                    echo 'Pull app image and run alembic upgrade head'
                    sh 'docker compose pull app'
                    sh 'docker compose run --rm app uv run alembic upgrade head'
                }
            }
        }

        stage('7. Deploy (compose app)') {
            steps {
                dir("${DEPLOY_PATH}") {
                    echo 'Recreate app service only'
                    sh 'docker compose up -d app'
                    sh 'docker image prune -f'
                }
            }
        }

        stage('8. Health Check') {
            steps {
                script {
                    echo 'Wait then probe FastAPI inside saksak-back'
                    sleep 10
                    sh '''
                        docker exec saksak-back python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"
                    '''
                }
            }
        }
```

Order is mandatory: **pull → migrate → up -d**. Migrate failure must not reach stage 7.

- [ ] **Step 2: Spec checklist (deploy path)**

- [ ] No auto-rollback on health failure
- [ ] Only `app` service updated
- [ ] Health uses container name `saksak-back`
- [ ] Tag is `:latest` only

- [ ] **Step 3: Commit** (유저 요청 시에만)

```bash
git add Jenkinsfile
git commit -m "$(cat <<'EOF'
feat: add push, migrate, deploy, and health stages

EOF
)"
```

---

### Task 4: Discord notify + docker logout cleanup

**Files:**
- Modify: `Jenkinsfile` — `post { success / failure / always }`

**Interfaces:**
- Consumes: `DISCORD_CRED_ID` → Secret text webhook URL
- Produces: Discord message on success and failure
- Failure message includes `${BUILD_URL}` and `${BUILD_URL}console`
- Never `echo` webhook URL

- [ ] **Step 1: Add helper logic in `post` blocks**

Replace/extend `post` as follows. Use `writeFile` + `curl` so webhook stays in env and JSON is not hand-escaped badly. Delete payload files in `always`.

```groovy
    post {
        always {
            script {
                echo 'Remove workspace secrets and local docker login session'
                sh 'rm -f .env discord-payload.json'
                sh 'docker logout || true'
            }
        }
        success {
            script {
                notifyDiscord(
                    title: 'saksak-backend deploy success',
                    color: 5763719,
                    description: "Build #${env.BUILD_NUMBER} succeeded.\n${env.BUILD_URL}"
                )
            }
        }
        failure {
            script {
                notifyDiscord(
                    title: 'saksak-backend deploy FAILED',
                    color: 15548997,
                    description: "Build #${env.BUILD_NUMBER} failed.\nSummary: check console for failed stage.\nBuild: ${env.BUILD_URL}\nConsole: ${env.BUILD_URL}console"
                )
            }
        }
    }
}

// Top-level helper (same Jenkinsfile, after pipeline block is INVALID).
// Instead, define a local closure inside each post OR use a shared script block.
```

Declarative Pipeline does **not** allow methods after the `pipeline` block to be called from `post` unless defined via shared library. Keep helper **inline** in each post, or use a single `script` function defined via:

Put this **inside** the pipeline using a reusable pattern — duplicate the curl block in success/failure (YAGNI over shared lib):

```groovy
        success {
            script {
                withCredentials([string(credentialsId: "${DISCORD_CRED_ID}", variable: 'DISCORD_WEBHOOK')]) {
                    writeFile file: 'discord-payload.json', text: """{
  "embeds": [{
    "title": "saksak-backend deploy success",
    "color": 5763719,
    "description": "Build #${env.BUILD_NUMBER} succeeded.\\n${env.BUILD_URL}"
  }]
}"""
                    sh 'curl -sS -X POST -H "Content-Type: application/json" -d @discord-payload.json "$DISCORD_WEBHOOK"'
                }
            }
        }
        failure {
            script {
                withCredentials([string(credentialsId: "${DISCORD_CRED_ID}", variable: 'DISCORD_WEBHOOK')]) {
                    writeFile file: 'discord-payload.json', text: """{
  "embeds": [{
    "title": "saksak-backend deploy FAILED",
    "color": 15548997,
    "description": "Build #${env.BUILD_NUMBER} failed.\\nSummary: check console for failed stage.\\nBuild: ${env.BUILD_URL}\\nConsole: ${env.BUILD_URL}console"
  }]
}"""
                    sh 'curl -sS -X POST -H "Content-Type: application/json" -d @discord-payload.json "$DISCORD_WEBHOOK"'
                }
            }
        }
```

Rules:
- Do **not** `echo "$DISCORD_WEBHOOK"`
- Do **not** paste full console log into the embed
- `always` still runs `rm -f .env discord-payload.json` and `docker logout || true`

- [ ] **Step 2: Ops note (manual, not code)**

Jenkins → Credentials → Add Secret text:
- ID: `discord-webhook-url`
- Secret: Discord Incoming Webhook URL

- [ ] **Step 3: Commit** (유저 요청 시에만)

```bash
git add Jenkinsfile
git commit -m "$(cat <<'EOF'
feat: notify Discord on Jenkins success and failure

EOF
)"
```

---

### Task 5: Final assembled Jenkinsfile + spec coverage gate

**Files:**
- Modify: `Jenkinsfile` — ensure one coherent file (no `TODO` / `error('TODO`) left)

**Interfaces:**
- Produces: complete pipeline matching the spec success criteria

- [ ] **Step 1: Write the full final `Jenkinsfile`** (single replace — source of truth)

```groovy
pipeline {
    agent any

    environment {
        GIT_URL = 'https://github.com/saksak-recipe/back.git'
        DOCKER_IMAGE = 'augustzer0/saksak'
        GIT_CRED_ID = 'github-login'
        DOCKER_CRED_ID = 'dockerhub-login'
        ENV_CRED_ID = 'saksak-env-file'
        DISCORD_CRED_ID = 'discord-webhook-url'
        DEPLOY_PATH = '/home/augustzer0/zer0/saksak'
    }

    stages {
        stage('1. Checkout') {
            steps {
                echo 'Checkout saksak-recipe/back main'
                git branch: 'main', credentialsId: "${GIT_CRED_ID}", url: "${GIT_URL}"
            }
        }

        stage('2. Create .env File') {
            steps {
                script {
                    echo 'Materialize workspace .env from Secret File (not DEPLOY_PATH)'
                    withCredentials([file(credentialsId: "${ENV_CRED_ID}", variable: 'SECRET_ENV')]) {
                        sh 'cp "$SECRET_ENV" .env'
                    }
                }
            }
        }

        stage('3. Build Image') {
            steps {
                echo "Build ${DOCKER_IMAGE}:latest"
                sh "docker build -t ${DOCKER_IMAGE}:latest ."
            }
        }

        stage('4. Test (pytest)') {
            steps {
                echo 'Run pytest inside ephemeral container (dev group)'
                sh """
                    docker run --rm ${DOCKER_IMAGE}:latest \
                      sh -c "uv sync --frozen --group dev --no-cache && uv run pytest"
                """
            }
        }

        stage('5. Push to Docker Hub') {
            steps {
                script {
                    echo "Push ${DOCKER_IMAGE}:latest"
                    withCredentials([usernamePassword(
                        credentialsId: "${DOCKER_CRED_ID}",
                        usernameVariable: 'DOCKER_USER',
                        passwordVariable: 'DOCKER_PW'
                    )]) {
                        sh 'echo "$DOCKER_PW" | docker login -u "$DOCKER_USER" --password-stdin'
                        sh "docker push ${DOCKER_IMAGE}:latest"
                    }
                }
            }
        }

        stage('6. Migrate (alembic)') {
            steps {
                dir("${DEPLOY_PATH}") {
                    echo 'Pull app image and run alembic upgrade head'
                    sh 'docker compose pull app'
                    sh 'docker compose run --rm app uv run alembic upgrade head'
                }
            }
        }

        stage('7. Deploy (compose app)') {
            steps {
                dir("${DEPLOY_PATH}") {
                    echo 'Recreate app service only'
                    sh 'docker compose up -d app'
                    sh 'docker image prune -f'
                }
            }
        }

        stage('8. Health Check') {
            steps {
                script {
                    echo 'Wait then probe FastAPI inside saksak-back'
                    sleep 10
                    sh '''
                        docker exec saksak-back python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"
                    '''
                }
            }
        }
    }

    post {
        always {
            echo 'Remove workspace secrets and local docker login session'
            sh 'rm -f .env discord-payload.json'
            sh 'docker logout || true'
        }
        success {
            script {
                withCredentials([string(credentialsId: "${DISCORD_CRED_ID}", variable: 'DISCORD_WEBHOOK')]) {
                    writeFile file: 'discord-payload.json', text: """{
  "embeds": [{
    "title": "saksak-backend deploy success",
    "color": 5763719,
    "description": "Build #${env.BUILD_NUMBER} succeeded.\\n${env.BUILD_URL}"
  }]
}"""
                    sh 'curl -sS -X POST -H "Content-Type: application/json" -d @discord-payload.json "$DISCORD_WEBHOOK"'
                }
            }
        }
        failure {
            script {
                withCredentials([string(credentialsId: "${DISCORD_CRED_ID}", variable: 'DISCORD_WEBHOOK')]) {
                    writeFile file: 'discord-payload.json', text: """{
  "embeds": [{
    "title": "saksak-backend deploy FAILED",
    "color": 15548997,
    "description": "Build #${env.BUILD_NUMBER} failed.\\nSummary: check console for failed stage.\\nBuild: ${env.BUILD_URL}\\nConsole: ${env.BUILD_URL}console"
  }]
}"""
                    sh 'curl -sS -X POST -H "Content-Type: application/json" -d @discord-payload.json "$DISCORD_WEBHOOK"'
                }
            }
        }
    }
}
```

- [ ] **Step 2: Spec coverage gate** (must all pass before done)

| Spec requirement | Verified in |
|---|---|
| main checkout + github-login | stage 1 |
| workspace .env from saksak-env-file; not DEPLOY_PATH | stage 2 + post |
| docker build :latest | stage 3 |
| pytest via `uv sync --group dev` | stage 4 |
| Hub push dockerhub-login | stage 5 |
| pull → alembic → up -d app | stages 6–7 |
| health saksak-back :8000 | stage 8 |
| Discord success + failure + console link | post |
| no webhook echo / no full log dump | post |
| docker logout + rm .env | post.always |
| no ruff / no SHA tags / no auto-rollback | absence |

- [ ] **Step 3: Grep for leftovers**

```bash
rg -n "TODO|ruff|rollback|docker-compose.yml" Jenkinsfile || true
```

Expected: no `TODO`; no `ruff`; no auto-rollback logic.

- [ ] **Step 4: Final commit** (유저 요청 시에만)

```bash
git add Jenkinsfile
git commit -m "$(cat <<'EOF'
feat: complete Jenkins CI/CD pipeline with Discord notify

EOF
)"
```

---

## Self-Review (plan author)

1. **Spec coverage:** All decided constraints and stages 1–8 + Discord + cleanup mapped to Tasks 1–5; Task 5 final file is the merge of 1–4.
2. **Placeholders:** No TBD; Task 1–3 temporary `error('TODO...')` are intentional intermediate gates removed in Task 5.
3. **Consistency:** Credential IDs and `DEPLOY_PATH` match the spec exactly; migrate-before-deploy order preserved.

## Ops prerequisites (outside repo)

1. Jenkins credential `discord-webhook-url` (Secret text)
2. Existing `github-login`, `dockerhub-login`, `saksak-env-file`
3. Host path `DEPLOY_PATH` with deploy `docker-compose.yml` + its own `.env`
4. Jenkins job: Pipeline from SCM, branch `main`, webhook/poll as desired
