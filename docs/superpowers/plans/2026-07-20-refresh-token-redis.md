# Refresh Token + Redis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opaque refresh token(Redis) + access 15분으로 세션을 유지하고, 레시피 상세 캐시도 Redis로 이전하며, 앱에서 silent refresh/logout을 지원한다.

**Architecture:** `docker-compose`에 Redis를 추가하고 공유 `redis.asyncio` 클라이언트를 둔다. Auth는 `refresh:{sha256}`에 user_id를 저장하고 rotation/logout으로 폐기한다. RecipeDetailCache는 `recipe_detail:{key}` JSON + TTL 24h. 앱은 SecureStore에 이중 토큰을 두고 Axios가 `TOKEN_EXPIRED` 시 단일 flight refresh 후 재시도한다.

**Tech Stack:** FastAPI, redis (asyncio), pytest, fakeredis; Expo, Axios, Zustand, expo-secure-store

**Spec:** `docs/superpowers/specs/2026-07-20-refresh-token-redis-design.md`

## Global Constraints

- Access TTL: 15분 / Refresh TTL: 14일 / Recipe cache TTL: 24시간
- Refresh: opaque 랜덤, Redis에 SHA-256 해시만 저장, 사용 시마다 rotation(구 토큰 즉시 삭제)
- login / signup / refresh 응답: 동일 `AuthResponse` (`info` + `access_token` + `refresh_token`)
- Auth Redis 장애: 5xx (`ExternalServiceException`). 발급/검증을 스킵하거나 “없는 척” 금지
- Recipe Redis 장애: get → miss 폴백(크롤), set 실패 → 로그만
- Postgres `refresh_tokens` 테이블·전 기기 로그아웃·refresh JWT·grace period 금지
- 커밋 메시지 스타일: `Feat:` / `Test:` / `Docs:` / `Fix:` (기존 저장소)
- 백엔드 작업 디렉터리: `/Users/jeong-yeonghun/Desktop/saksak/back`
- 앱 작업 디렉터리: `/Users/jeong-yeonghun/Desktop/saksak/app`

## File Structure

### Backend (`/Users/jeong-yeonghun/Desktop/saksak/back`)

| Path | Responsibility |
|------|----------------|
| `docker-compose.yml` | Redis 서비스 + app depends_on/env |
| `src/core/config.py` | `REDIS_URL` |
| `src/core/redis.py` | 공유 async Redis 수명·DI |
| `src/core/security.py` | access TTL 15분, refresh 생성/해시 헬퍼 |
| `src/main.py` | FastAPI lifespan으로 Redis connect/close |
| `src/domains/auth/refresh_store.py` | Redis refresh CRUD |
| `src/domains/auth/service.py` | issue/refresh/logout |
| `src/domains/user/schemas.py` | `refresh_token` 필드, Auth 요청 스키마 |
| `src/api/deps.py` | Redis/RefreshStore/Auth DI, Recipe cache Redis |
| `src/api/v1/endpoints/auth.py` | `/refresh`, `/logout` |
| `src/api/v1/endpoints/user.py` | signup이 TokenPair 사용 |
| `src/domains/recipe_detail/cache.py` | async Redis 캐시 |
| `src/domains/recipe_detail/service.py` | await cache get/set |
| `tests/conftest.py` | `REDIS_URL` env + fake Redis override |
| `tests/unit/test_refresh_store.py` | refresh store 단위 |
| `tests/unit/test_auth_service.py` | login/refresh/logout |
| `tests/api/test_auth_api.py` | refresh/logout API |
| `tests/unit/test_recipe_detail_cache.py` | Redis 캐시 |
| `tests/unit/test_recipe_detail_service.py` | async cache 호환 |
| `pyproject.toml` / `uv.lock` | `redis`, `fakeredis` |

### Frontend (`/Users/jeong-yeonghun/Desktop/saksak/app`)

| Path | Responsibility |
|------|----------------|
| `src/types/api.ts` | `refresh_token` |
| `src/stores/authStore.ts` | refresh SecureStore + setSession 시그니처 |
| `src/api/auth.ts` | `refresh`, `logout` |
| `src/api/client.ts` | silent refresh + 단일 flight |
| `src/app/(auth)/login.tsx` | setSession에 refresh 전달 |
| `src/app/(auth)/signup.tsx` | setSession에 refresh 전달 |
| `src/app/(main)/index.tsx` | 서버 logout 후 clearSession |
| `src/app/_layout.tsx` | 401 핸들러는 refresh 실패 시에만 clear (인터셉터가 담당) |

---

### Task 1: Redis 인프라 + 공유 클라이언트

**Files:**
- Modify: `docker-compose.yml`
- Modify: `src/core/config.py`
- Create: `src/core/redis.py`
- Modify: `src/main.py`
- Modify: `tests/conftest.py`
- Modify: `pyproject.toml` (via `uv add`)

**Interfaces:**
- Produces:
  - `Settings.REDIS_URL: str`
  - `async def init_redis() -> None`
  - `async def close_redis() -> None`
  - `def get_redis() -> Redis` (미초기화 시 RuntimeError)
  - compose 서비스명 `saksak-redis`, URL `redis://saksak-redis:6379/0`

- [ ] **Step 1: Add dependencies**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv add redis
uv add --dev fakeredis
```

- [ ] **Step 2: Add `REDIS_URL` to settings**

`src/core/config.py`의 `Settings`에 추가:

```python
REDIS_URL: str = "redis://localhost:6379/0"
```

- [ ] **Step 3: Create `src/core/redis.py`**

```python
from redis.asyncio import Redis

from core.config import settings

_redis: Redis | None = None


async def init_redis() -> None:
    global _redis
    _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    await _redis.ping()


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis is not initialized")
    return _redis
```

- [ ] **Step 4: Wire lifespan in `src/main.py`**

```python
from contextlib import asynccontextmanager

from core.redis import close_redis, init_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    yield
    await close_redis()


app = FastAPI(lifespan=lifespan)
```

(기존 `app = FastAPI()`를 lifespan 버전으로 교체. 예외 핸들러·라우터 등록은 그대로.)

- [ ] **Step 5: Update `docker-compose.yml`**

`postgresql`과 같은 레벨에:

```yaml
  redis:
    image: redis:7-alpine
    container_name: saksak-redis
    ports:
      - "6379:6379"
    networks:
      - saksak-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
```

`app.depends_on`에 redis health 추가, `environment`에:

```yaml
      - REDIS_URL=redis://saksak-redis:6379/0
```

- [ ] **Step 6: Update `tests/conftest.py`**

상단 env에:

```python
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
```

`client` fixture에서 fakeredis로 override (Task 2 DI가 생기기 전이면, Task 2에서 `get_redis` override를 완성한다). 지금은:

```python
import fakeredis.aioredis
from core import redis as redis_module

@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    redis_module._redis = fake
    # ... existing get_db override ...
    try:
        async with AsyncClient(...) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        await fake.aclose()
        redis_module._redis = None
```

- [ ] **Step 7: Smoke-check import**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv run python -c "from core.redis import get_redis; print('ok')"
```

Expected: `ok` (get_redis는 호출하지 말 것 — 미초기화 RuntimeError)

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml src/core/config.py src/core/redis.py src/main.py tests/conftest.py pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
Feat: Redis 인프라 및 공유 클라이언트 추가

EOF
)"
```

---

### Task 2: Refresh token helpers + RefreshTokenStore

**Files:**
- Modify: `src/core/security.py`
- Create: `src/domains/auth/refresh_store.py`
- Create: `tests/unit/test_refresh_store.py`

**Interfaces:**
- Consumes: `get_redis()` / injected `Redis`
- Produces:
  - `ACCESS_TOKEN_EXPIRE_MINUTES = 15`
  - `REFRESH_TOKEN_EXPIRE_SECONDS = 14 * 24 * 60 * 60`
  - `create_refresh_token() -> str`
  - `hash_refresh_token(raw: str) -> str`
  - `RefreshTokenStore.save(raw_token: str, user_id: UUID) -> None`
  - `RefreshTokenStore.pop_user_id(raw_token: str) -> UUID | None` (get+delete atomic 목적: get 후 delete)
  - `RefreshTokenStore.delete(raw_token: str) -> None`
  - Redis key: `refresh:{hash}`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_refresh_store.py`:

```python
import uuid

import fakeredis.aioredis
import pytest

from domains.auth.refresh_store import RefreshTokenStore


@pytest.fixture
async def store():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = RefreshTokenStore(redis, ttl_seconds=60)
    yield s
    await redis.aclose()


async def test_save_and_pop_returns_user_id(store: RefreshTokenStore):
    user_id = uuid.uuid4()
    raw = "raw-refresh-token-value"
    await store.save(raw, user_id)
    got = await store.pop_user_id(raw)
    assert got == user_id
    assert await store.pop_user_id(raw) is None


async def test_delete_makes_token_invalid(store: RefreshTokenStore):
    user_id = uuid.uuid4()
    raw = "to-delete"
    await store.save(raw, user_id)
    await store.delete(raw)
    assert await store.pop_user_id(raw) is None
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv run pytest tests/unit/test_refresh_store.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: Update `src/core/security.py` constants + helpers**

```python
import hashlib
import secrets

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_SECONDS = 14 * 24 * 60 * 60


def create_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
```

(기존 JWT/password 코드는 유지. `ACCESS_TOKEN_EXPIRE_MINUTES`만 30→15.)

- [ ] **Step 4: Implement `src/domains/auth/refresh_store.py`**

```python
from uuid import UUID

from redis.asyncio import Redis

from core.exception.exceptions import ExternalServiceException
from core.security import hash_refresh_token


class RefreshTokenStore:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    def _key(self, raw_token: str) -> str:
        return f"refresh:{hash_refresh_token(raw_token)}"

    async def save(self, raw_token: str, user_id: UUID) -> None:
        try:
            await self._redis.set(self._key(raw_token), str(user_id), ex=self._ttl)
        except Exception as exc:
            raise ExternalServiceException("세션 저장에 실패했습니다.") from exc

    async def pop_user_id(self, raw_token: str) -> UUID | None:
        key = self._key(raw_token)
        try:
            user_id = await self._redis.get(key)
            if user_id is None:
                return None
            await self._redis.delete(key)
            return UUID(user_id)
        except Exception as exc:
            raise ExternalServiceException("세션 조회에 실패했습니다.") from exc

    async def delete(self, raw_token: str) -> None:
        try:
            await self._redis.delete(self._key(raw_token))
        except Exception as exc:
            raise ExternalServiceException("세션 삭제에 실패했습니다.") from exc
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
uv run pytest tests/unit/test_refresh_store.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/core/security.py src/domains/auth/refresh_store.py tests/unit/test_refresh_store.py
git commit -m "$(cat <<'EOF'
Feat: refresh token Redis store 및 TTL 헬퍼 추가

EOF
)"
```

---

### Task 3: AuthService issue / refresh / logout + 스키마

**Files:**
- Modify: `src/domains/user/schemas.py`
- Modify: `src/domains/auth/service.py`
- Modify: `src/api/deps.py`
- Modify: `tests/unit/test_auth_service.py`

**Interfaces:**
- Consumes: `RefreshTokenStore`, `UserRepository`, `create_jwt`, `create_refresh_token`
- Produces:
  - `@dataclass TokenPair: access_token: str; refresh_token: str`
  - `AuthService.issue_tokens(user) -> TokenPair`
  - `AuthService.refresh(refresh_token: str) -> LogInResponse`
  - `AuthService.logout(refresh_token: str) -> None`
  - `LogInResponse` / `SignUpResponse`에 `refresh_token: str` 필수
  - `RefreshRequest(refresh_token: str)`
  - `get_auth_service`가 `RefreshTokenStore(get_redis(), REFRESH_TOKEN_EXPIRE_SECONDS)` 주입

- [ ] **Step 1: Extend failing unit tests**

`tests/unit/test_auth_service.py`를 다음처럼 갱신/추가:

```python
from unittest.mock import AsyncMock
import pytest
import uuid6

from core import security
from core.exception.exceptions import InvalidTokenException, UnAuthorizedException
from domains.auth.service import AuthService
from domains.user.model import User
from domains.user.schemas import LogInRequest


@pytest.fixture
def user_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def refresh_store() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def auth_service(user_repo: AsyncMock, refresh_store: AsyncMock) -> AuthService:
    return AuthService(user_repo=user_repo, refresh_store=refresh_store)


@pytest.fixture
def existing_user() -> User:
    return User(
        id=uuid6.uuid7(),
        email="test@example.com",
        password=security.hash_password("password123"),
        nickname="testuser",
    )


async def test_login_returns_access_and_refresh(
    auth_service: AuthService,
    user_repo: AsyncMock,
    refresh_store: AsyncMock,
    existing_user: User,
):
    user_repo.get_user_by_email.return_value = existing_user

    response = await auth_service.login(
        LogInRequest(email="test@example.com", password="password123")
    )

    assert response.access_token
    assert response.refresh_token
    assert response.info.email == "test@example.com"
    refresh_store.save.assert_awaited_once()


async def test_refresh_rotates_tokens(
    auth_service: AuthService,
    user_repo: AsyncMock,
    refresh_store: AsyncMock,
    existing_user: User,
):
    refresh_store.pop_user_id.return_value = existing_user.id
    user_repo.get_user_by_id.return_value = existing_user

    old = "old-refresh"
    response = await auth_service.refresh(old)

    assert response.access_token
    assert response.refresh_token
    assert response.refresh_token != old
    assert response.info.id == existing_user.id
    refresh_store.save.assert_awaited_once()


async def test_refresh_rejects_unknown_token(
    auth_service: AuthService, refresh_store: AsyncMock
):
    refresh_store.pop_user_id.return_value = None
    with pytest.raises(InvalidTokenException):
        await auth_service.refresh("missing")


async def test_logout_deletes_refresh(
    auth_service: AuthService, refresh_store: AsyncMock
):
    await auth_service.logout("some-refresh")
    refresh_store.delete.assert_awaited_once_with("some-refresh")
```

기존 `test_login_raises_*`, `test_get_user_by_token_*`도 `refresh_store` fixture를 쓰도록 시그니처 맞춘다.

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_auth_service.py -v
```

Expected: FAIL (AuthService 시그니처/필드 없음)

- [ ] **Step 3: Update schemas**

`src/domains/user/schemas.py`:

```python
class SignUpResponse(BaseModel):
    info: UserInfoResponse
    access_token: str
    refresh_token: str


class LogInResponse(BaseModel):
    info: UserInfoResponse
    access_token: str = Field(..., description="인증을 위한 액세스 토큰")
    refresh_token: str = Field(..., description="액세스 토큰 갱신용 리프레시 토큰")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., description="리프레시 토큰")
```

- [ ] **Step 4: Implement AuthService**

`src/domains/auth/service.py`:

```python
from dataclasses import dataclass
from uuid import UUID

from core import security
from core.exception.exceptions import InvalidTokenException, UnAuthorizedException
from core.security import REFRESH_TOKEN_EXPIRE_SECONDS
from domains.auth.refresh_store import RefreshTokenStore
from domains.user.model import User
from domains.user.repository import UserRepository
from domains.user.schemas import LogInRequest, LogInResponse, UserInfoResponse


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(
        self, user_repo: UserRepository, refresh_store: RefreshTokenStore
    ) -> None:
        self.user_repo = user_repo
        self.refresh_store = refresh_store

    async def issue_tokens(self, user: User) -> TokenPair:
        access_token = security.create_jwt(user.id)
        refresh_token = security.create_refresh_token()
        await self.refresh_store.save(refresh_token, user.id)
        return TokenPair(access_token=access_token, refresh_token=refresh_token)

    async def login(self, request: LogInRequest) -> LogInResponse:
        user = await self.user_repo.get_user_by_email(str(request.email))
        if not user or not user.password:
            raise UnAuthorizedException(
                detail="이메일 또는 비밀번호가 올바르지 않습니다."
            )
        if not security.verify_password(request.password, user.password):
            raise UnAuthorizedException(
                detail="이메일 또는 비밀번호가 올바르지 않습니다."
            )
        tokens = await self.issue_tokens(user)
        return LogInResponse(
            info=UserInfoResponse.model_validate(user),
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        )

    async def refresh(self, refresh_token: str) -> LogInResponse:
        user_id = await self.refresh_store.pop_user_id(refresh_token)
        if user_id is None:
            raise InvalidTokenException(detail="유효하지 않은 리프레시 토큰입니다.")
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            raise InvalidTokenException(detail="유효하지 않은 리프레시 토큰입니다.")
        tokens = await self.issue_tokens(user)
        return LogInResponse(
            info=UserInfoResponse.model_validate(user),
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        )

    async def logout(self, refresh_token: str) -> None:
        await self.refresh_store.delete(refresh_token)

    async def get_user_by_token(self, access_token: str) -> User:
        user_id = UUID(security.decode_jwt(access_token))
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            raise UnAuthorizedException(detail="사용자를 찾을 수 없습니다.")
        return user
```

- [ ] **Step 5: Wire DI in `src/api/deps.py`**

```python
from core.redis import get_redis
from core.security import REFRESH_TOKEN_EXPIRE_SECONDS
from domains.auth.refresh_store import RefreshTokenStore


def get_refresh_store() -> RefreshTokenStore:
    return RefreshTokenStore(get_redis(), ttl_seconds=REFRESH_TOKEN_EXPIRE_SECONDS)


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repo),
    refresh_store: RefreshTokenStore = Depends(get_refresh_store),
) -> AuthService:
    return AuthService(user_repo=user_repo, refresh_store=refresh_store)
```

- [ ] **Step 6: Run unit tests — PASS**

```bash
uv run pytest tests/unit/test_auth_service.py tests/unit/test_refresh_store.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/domains/user/schemas.py src/domains/auth/service.py src/api/deps.py tests/unit/test_auth_service.py
git commit -m "$(cat <<'EOF'
Feat: AuthService refresh/logout 및 토큰 페어 발급

EOF
)"
```

---

### Task 4: Auth API endpoints + signup 응답 + API 테스트

**Files:**
- Modify: `src/api/v1/endpoints/auth.py`
- Modify: `src/api/v1/endpoints/user.py`
- Modify: `tests/api/test_auth_api.py`

**Interfaces:**
- Consumes: `AuthService.refresh`, `AuthService.logout`, `AuthService.issue_tokens -> TokenPair`
- Produces:
  - `POST /api/v1/auth/refresh` → `LogInResponse`
  - `POST /api/v1/auth/logout` → 200 empty/`{"ok": true}` (본문 없어도 됨; 빈 200)
  - signup/login body에 `refresh_token` 포함

- [ ] **Step 1: Write/extend API tests**

`tests/api/test_auth_api.py`에 추가하고 기존 assert에 `refresh_token` 포함:

```python
async def test_login_returns_refresh_token(client: AsyncClient):
    await client.post(
        "/api/v1/users/signup",
        json={
            "email": "login@example.com",
            "password": "password123",
            "checked_password": "password123",
            "nickname": "loginuser",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]


async def test_refresh_rotates_and_rejects_reuse(client: AsyncClient):
    signup = await client.post(
        "/api/v1/users/signup",
        json={
            "email": "refresh@example.com",
            "password": "password123",
            "checked_password": "password123",
            "nickname": "refreshuser",
        },
    )
    old_refresh = signup.json()["refresh_token"]

    first = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert first.status_code == 200
    new_refresh = first.json()["refresh_token"]
    assert new_refresh != old_refresh

    reuse = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert reuse.status_code == 401
    assert reuse.json()["code"] == ErrorCode.INVALID_TOKEN


async def test_logout_invalidates_refresh(client: AsyncClient):
    signup = await client.post(
        "/api/v1/users/signup",
        json={
            "email": "logout@example.com",
            "password": "password123",
            "checked_password": "password123",
            "nickname": "logoutuser",
        },
    )
    refresh = signup.json()["refresh_token"]
    logout = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": refresh}
    )
    assert logout.status_code == 200

    again = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh}
    )
    assert again.status_code == 401
```

기존 `test_signup_returns_user_and_token`에도 `assert body["refresh_token"]` 추가.

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/api/test_auth_api.py -v
```

Expected: FAIL (404 on refresh/logout or missing refresh_token)

- [ ] **Step 3: Update auth endpoints**

`src/api/v1/endpoints/auth.py`:

```python
from fastapi import APIRouter, status, Depends

from api.deps import get_auth_service
from domains.auth.service import AuthService
from domains.user.schemas import LogInRequest, LogInResponse, RefreshRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", status_code=status.HTTP_200_OK, response_model=LogInResponse)
async def log_in(
    request: LogInRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> LogInResponse:
    return await auth_service.login(request)


@router.post("/refresh", status_code=status.HTTP_200_OK, response_model=LogInResponse)
async def refresh(
    request: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> LogInResponse:
    return await auth_service.refresh(request.refresh_token)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, bool]:
    await auth_service.logout(request.refresh_token)
    return {"ok": True}
```

- [ ] **Step 4: Update signup endpoint**

`src/api/v1/endpoints/user.py`:

```python
    user = await user_service.sign_up(request)
    tokens = await auth_service.issue_tokens(user)
    return SignUpResponse(
        info=UserInfoResponse.model_validate(user),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
    )
```

- [ ] **Step 5: Run API tests — PASS**

```bash
uv run pytest tests/api/test_auth_api.py -v
```

Expected: PASS (conftest fake Redis 동작 확인)

- [ ] **Step 6: Commit**

```bash
git add src/api/v1/endpoints/auth.py src/api/v1/endpoints/user.py tests/api/test_auth_api.py
git commit -m "$(cat <<'EOF'
Feat: auth refresh/logout API 및 signup refresh 응답

EOF
)"
```

---

### Task 5: RecipeDetailCache → Redis

**Files:**
- Modify: `src/domains/recipe_detail/cache.py`
- Modify: `src/domains/recipe_detail/service.py`
- Modify: `src/api/deps.py`
- Modify: `tests/unit/test_recipe_detail_cache.py`
- Modify: `tests/unit/test_recipe_detail_service.py`

**Interfaces:**
- Consumes: injected `Redis`
- Produces:
  - `async def RecipeDetailCache.get(key: str) -> RecipeDetailResponse | None`
  - `async def RecipeDetailCache.set(key: str, value: RecipeDetailResponse) -> None`
  - Redis key `recipe_detail:{key}`, TTL 86400
  - get 실패 → `None`; set 실패 → loguru warning, swallow
  - `get_recipe_detail_service`가 `RecipeDetailCache(get_redis(), ttl_seconds=86400)` 사용 (모듈 전역 싱글톤 제거)

- [ ] **Step 1: Rewrite failing cache tests (async)**

`tests/unit/test_recipe_detail_cache.py`:

```python
import fakeredis.aioredis
import pytest

from domains.recipe_detail.cache import RecipeDetailCache, cache_key
from domains.recipe_detail.schemas import RecipeDetailResponse


def _sample(**kwargs) -> RecipeDetailResponse:
    base = dict(
        board_name="제목",
        author_name="작성자",
        recipe_name="요리",
        source_url="https://www.10000recipe.com/recipe/1",
        cached=False,
    )
    base.update(kwargs)
    return RecipeDetailResponse(**base)


@pytest.fixture
async def cache():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    c = RecipeDetailCache(redis, ttl_seconds=60)
    yield c
    await redis.aclose()


def test_cache_key_normalizes():
    assert cache_key(" A ", "B") == cache_key("a", "b")


async def test_cache_hit_and_miss(cache: RecipeDetailCache):
    key = cache_key("제목", "작성자")
    assert await cache.get(key) is None
    await cache.set(key, _sample())
    hit = await cache.get(key)
    assert hit is not None
    assert hit.recipe_name == "요리"
    assert hit.cached is True


async def test_cache_get_failure_returns_none():
    class BoomRedis:
        async def get(self, key):
            raise RuntimeError("down")

    cache = RecipeDetailCache(BoomRedis(), ttl_seconds=60)  # type: ignore[arg-type]
    assert await cache.get("x") is None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_recipe_detail_cache.py -v
```

Expected: FAIL (sync API / 시그니처)

- [ ] **Step 3: Implement Redis cache**

`src/domains/recipe_detail/cache.py`:

```python
import hashlib

from loguru import logger
from redis.asyncio import Redis

from domains.recipe_detail.normalize import normalize_text
from domains.recipe_detail.schemas import RecipeDetailResponse


def cache_key(board_name: str, author_name: str) -> str:
    raw = f"{normalize_text(board_name)}|{normalize_text(author_name)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RecipeDetailCache:
    def __init__(self, redis: Redis, ttl_seconds: int = 86400) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    def _redis_key(self, key: str) -> str:
        return f"recipe_detail:{key}"

    async def get(self, key: str) -> RecipeDetailResponse | None:
        try:
            raw = await self._redis.get(self._redis_key(key))
        except Exception:
            logger.warning("recipe detail cache get failed")
            return None
        if raw is None:
            return None
        try:
            value = RecipeDetailResponse.model_validate_json(raw)
        except Exception:
            logger.warning("recipe detail cache decode failed")
            return None
        return value.model_copy(update={"cached": True})

    async def set(self, key: str, value: RecipeDetailResponse) -> None:
        stored = value.model_copy(update={"cached": False})
        try:
            await self._redis.set(
                self._redis_key(key),
                stored.model_dump_json(),
                ex=self._ttl,
            )
        except Exception:
            logger.warning("recipe detail cache set failed")
```

- [ ] **Step 4: Update service to await cache**

`src/domains/recipe_detail/service.py`:

```python
        cached = await self._cache.get(key)
        if cached is not None:
            return cached
        # ... crawl ...
        await self._cache.set(key, response)
        return response
```

- [ ] **Step 5: Update deps — no module singleton**

`src/api/deps.py`:

```python
_recipe_crawler = RecipeCrawler()
# remove _recipe_detail_cache = RecipeDetailCache(...)


def get_recipe_detail_service(
    user: User = Depends(get_current_user),
) -> RecipeDetailService:
    cache = RecipeDetailCache(get_redis(), ttl_seconds=86400)
    return RecipeDetailService(crawler=_recipe_crawler, cache=cache)
```

(`get_redis` import 추가)

- [ ] **Step 6: Fix service unit tests**

`tests/unit/test_recipe_detail_service.py` fixture:

```python
@pytest.fixture
async def service(crawler: AsyncMock):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    svc = RecipeDetailService(
        crawler=crawler,
        cache=RecipeDetailCache(redis, ttl_seconds=60),
    )
    yield svc
    await redis.aclose()
```

- [ ] **Step 7: Run related tests — PASS**

```bash
uv run pytest tests/unit/test_recipe_detail_cache.py tests/unit/test_recipe_detail_service.py tests/api/test_recipe_detail_api.py -v
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/domains/recipe_detail/cache.py src/domains/recipe_detail/service.py src/api/deps.py tests/unit/test_recipe_detail_cache.py tests/unit/test_recipe_detail_service.py
git commit -m "$(cat <<'EOF'
Feat: 레시피 상세 캐시를 Redis로 이전

EOF
)"
```

---

### Task 6: 앱 — 타입 / SecureStore / auth API

**Files:**
- Modify: `/Users/jeong-yeonghun/Desktop/saksak/app/src/types/api.ts`
- Modify: `/Users/jeong-yeonghun/Desktop/saksak/app/src/stores/authStore.ts`
- Modify: `/Users/jeong-yeonghun/Desktop/saksak/app/src/api/auth.ts`
- Modify: `/Users/jeong-yeonghun/Desktop/saksak/app/src/app/(auth)/login.tsx`
- Modify: `/Users/jeong-yeonghun/Desktop/saksak/app/src/app/(auth)/signup.tsx`

**Interfaces:**
- Produces:
  - `AuthResponse.refresh_token: string`
  - `setSession(accessToken, refreshToken, user)`
  - `getRefreshToken(): Promise<string | null>` (store 내부 또는 client용 export)
  - `refresh(refreshToken): Promise<AuthResponse>`
  - `logout(refreshToken): Promise<void>`
  - SecureStore key `saksak_refresh_token`

- [ ] **Step 1: Update types**

```typescript
export type AuthResponse = {
  info: UserInfo;
  access_token: string;
  refresh_token: string;
};
```

- [ ] **Step 2: Update authStore**

```typescript
const TOKEN_KEY = 'saksak_access_token';
const REFRESH_KEY = 'saksak_refresh_token';
const USER_KEY = 'saksak_user_info';

type AuthState = {
  token: string | null;
  refreshToken: string | null;
  user: UserInfo | null;
  isHydrated: boolean;
  hydrate: () => Promise<void>;
  setSession: (
    accessToken: string,
    refreshToken: string,
    user: UserInfo,
  ) => Promise<void>;
  clearSession: () => Promise<void>;
};
```

`hydrate` / `setSession` / `clearSession`에서 refresh도 SecureStore 읽고/쓰고/삭제. `setAuthToken(access)`는 기존대로 access만.

- [ ] **Step 3: Update auth API**

```typescript
export async function refreshTokens(
  refreshToken: string,
): Promise<AuthResponse> {
  const { data } = await apiClient.post<AuthResponse>('/auth/refresh', {
    refresh_token: refreshToken,
  });
  return data;
}

export async function logout(refreshToken: string): Promise<void> {
  await apiClient.post('/auth/logout', { refresh_token: refreshToken });
}
```

- [ ] **Step 4: Update login/signup screens**

```typescript
await setSession(data.access_token, data.refresh_token, data.info);
```

- [ ] **Step 5: Typecheck**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/app
npx tsc --noEmit
```

Expected: `client.ts`/logout 관련 에러가 남을 수 있음 → Task 7·8에서 해소. 이 Task에서 바꾼 파일 기준으로 `setSession` 호출부 에러만 없어야 함.

- [ ] **Step 6: Commit (app repo)**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/app
git add src/types/api.ts src/stores/authStore.ts src/api/auth.ts src/app/\(auth\)/login.tsx src/app/\(auth\)/signup.tsx
git commit -m "$(cat <<'EOF'
Feat: refresh token 타입·SecureStore·auth API 추가

EOF
)"
```

---

### Task 7: 앱 — Axios silent refresh (단일 flight)

**Files:**
- Modify: `/Users/jeong-yeonghun/Desktop/saksak/app/src/api/client.ts`
- Modify: `/Users/jeong-yeonghun/Desktop/saksak/app/src/app/_layout.tsx` (필요 시)

**Interfaces:**
- Consumes: `refreshTokens`, SecureStore refresh, `setSession`/`clearSession`
- Produces:
  - `TOKEN_EXPIRED` → refresh 1회 → 원요청 재시도
  - `INVALID_TOKEN` / refresh 실패 → `onUnauthorized()`
  - 동시 401: 하나의 refresh Promise 공유
  - `/auth/refresh`·`/auth/login`·`/auth/logout`·`/users/signup` 요청은 refresh 루프 제외

- [ ] **Step 1: Implement interceptor (순환 import 방지용 핸들러 포함)**

`src/api/client.ts`:

```typescript
import axios, { AxiosError, isAxiosError } from 'axios';
import type { ApiErrorBody, UserInfo } from '@/types/api';
import { refreshTokens } from '@/api/auth';

const baseURL = `${process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'}/api/v1`;

export const apiClient = axios.create({
  baseURL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

let authToken: string | null = null;
let onUnauthorized: (() => void) | null = null;
let onTokensRefreshed:
  | ((access: string, refresh: string, user: UserInfo) => Promise<void>)
  | null = null;
let refreshPromise: Promise<string | null> | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

export function setTokensRefreshedHandler(
  handler: typeof onTokensRefreshed,
): void {
  onTokensRefreshed = handler;
}

function isAuthUrl(url?: string): boolean {
  if (!url) return false;
  return (
    url.includes('/auth/login') ||
    url.includes('/auth/refresh') ||
    url.includes('/auth/logout') ||
    url.includes('/users/signup')
  );
}

async function rotateAccessToken(): Promise<string | null> {
  const { useAuthStore } = await import('@/stores/authStore');
  const refreshToken = useAuthStore.getState().refreshToken;
  if (!refreshToken) return null;
  const data = await refreshTokens(refreshToken);
  if (onTokensRefreshed) {
    await onTokensRefreshed(
      data.access_token,
      data.refresh_token,
      data.info,
    );
  } else {
    setAuthToken(data.access_token);
  }
  return data.access_token;
}

apiClient.interceptors.request.use((config) => {
  if (authToken) {
    config.headers.Authorization = `Bearer ${authToken}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorBody>) => {
    const status = error.response?.status;
    const code = error.response?.data?.code;
    const original = error.config as
      | (NonNullable<typeof error.config> & { _retry?: boolean })
      | undefined;

    if (
      status === 401 &&
      code === 'TOKEN_EXPIRED' &&
      original &&
      !isAuthUrl(original.url) &&
      !original._retry
    ) {
      original._retry = true;
      try {
        if (!refreshPromise) {
          refreshPromise = rotateAccessToken().finally(() => {
            refreshPromise = null;
          });
        }
        const newToken = await refreshPromise;
        if (!newToken) {
          onUnauthorized?.();
          return Promise.reject(error);
        }
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return apiClient.request(original);
      } catch {
        onUnauthorized?.();
        return Promise.reject(error);
      }
    }

    if (
      status === 401 &&
      (code === 'INVALID_TOKEN' || code === 'UNAUTHORIZED')
    ) {
      onUnauthorized?.();
    }

    return Promise.reject(error);
  },
);

// getErrorMessage — 기존 구현 유지
```

`_layout.tsx`에서:

```typescript
setTokensRefreshedHandler((access, refresh, user) =>
  useAuthStore.getState().setSession(access, refresh, user),
);
```

참고: `auth.ts`의 `refreshTokens`가 `apiClient`를 import하므로, refresh 요청 URL은 `isAuthUrl`로 재진입을 막는다.

- [ ] **Step 2: Manual verify checklist**

1. 로그인 후 SecureStore에 access+refresh 존재
2. access만 만료 시뮬레이션(백엔드 TTL을 임시 1분으로 낮추거나 과거 토큰) → API가 재로그인 없이 성공
3. refresh 재사용/삭제 후 → 로그인 화면

- [ ] **Step 3: Commit (app)**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/app
git add src/api/client.ts src/app/_layout.tsx
git commit -m "$(cat <<'EOF'
Feat: Axios silent refresh 및 단일 flight 처리

EOF
)"
```

---

### Task 8: 앱 — 서버 logout 연동

**Files:**
- Modify: `/Users/jeong-yeonghun/Desktop/saksak/app/src/app/(main)/index.tsx`

**Interfaces:**
- Consumes: `logout(refreshToken)`, `clearSession`
- Produces: 로그아웃 시 서버 revoke 후 로컬 clear (서버 실패해도 로컬 clear)

- [ ] **Step 1: Update onLogout**

```typescript
import { logout as logoutApi } from '@/api/auth';

const onLogout = () => {
  Alert.alert('로그아웃', '정말 로그아웃할까요?', [
    { text: '취소', style: 'cancel' },
    {
      text: '로그아웃',
      style: 'destructive',
      onPress: () => {
        void (async () => {
          const refresh = useAuthStore.getState().refreshToken;
          try {
            if (refresh) {
              await logoutApi(refresh);
            }
          } catch {
            // 서버 실패해도 로컬 세션은 지운다
          }
          await clearSession();
          router.replace('/(auth)/login');
        })();
      },
    },
  ]);
};
```

- [ ] **Step 2: Commit (app)**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/app
git add src/app/\(main\)/index.tsx
git commit -m "$(cat <<'EOF'
Feat: 로그아웃 시 서버 refresh 폐기 호출

EOF
)"
```

- [ ] **Step 3: Backend full regression**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv run pytest -v
```

Expected: PASS

---

## Spec coverage checklist

| Spec item | Task |
|-----------|------|
| docker-compose Redis + REDIS_URL | 1 |
| 공유 redis client + lifespan | 1 |
| opaque refresh SHA-256 in Redis | 2 |
| access 15m / refresh 14d | 2–3 |
| rotation on refresh | 3–4 |
| login/signup/refresh same AuthResponse | 3–4 |
| POST /auth/refresh, /auth/logout | 4 |
| Auth Redis failure → 5xx | 2 (`ExternalServiceException`) |
| Recipe cache Redis + TTL 24h | 5 |
| Recipe Redis failure → miss/log | 5 |
| App SecureStore dual tokens | 6 |
| Silent refresh + single flight | 7 |
| Logout server revoke | 8 |
