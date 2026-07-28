# Auth · AI Rate Limits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로그인 5회 실패 잠금(비밀번호 재설정으로 해제), 인증 메일 발송 이메일당 하루 3회, OCR 3회/RAG 7회 일일 한도 + 응답 `quota`·429 에러 코드를 백엔드에 추가한다.

**Architecture:** Redis `DailyQuotaStore`(KST 일자 키)와 `LoginLockStore`를 둔다. AuthService가 로그인 잠금·메일 발송 한도를 적용하고, OcrService/RagService가 외부 호출 직전 consume 후 응답에 `quota`를 붙인다. 429는 `TooManyRequestsException`, 잠금은 `LOGIN_LOCKED`(401).

**Tech Stack:** FastAPI, redis.asyncio, fakeredis, pytest, Pydantic v2, zoneinfo(Asia/Seoul)

**Spec:** `docs/superpowers/specs/2026-07-28-auth-ai-rate-limits-design.md`

## Global Constraints

- 일자 경계: Asia/Seoul (KST) 자정
- email_send limit=3 / ocr limit=3 / rag limit=7
- 로그인 실패 5회(`>=5`) 이후 `LOGIN_LOCKED`; 해제는 `password/reset/confirm` 성공 시만
- password reset request: 실제 발송할 때만 차감; 미발송 시 `quota` 미포함(열거 방지)
- OCR/RAG: 클라이언트 검증 실패는 미차감; 외부 API 직전 consume; 외부 실패 시에도 차감 유지
- RAG 재료 없음(임베딩 미호출)은 미차감
- 앱(`saksak/app`) 수정 금지
- 커밋 메시지: `Feat:` / `Test:` / `Fix:` / `Docs:`
- 작업 디렉터리: `/Users/jeong-yeonghun/Desktop/saksak/back`

## File Structure

| Path | Responsibility |
|------|----------------|
| `src/core/exception/codes.py` | 신규 ErrorCode |
| `src/core/exception/exceptions.py` | `TooManyRequestsException`, Base에 `extra` |
| `src/core/exception/handlers.py` | `extra`를 JSON에 merge |
| `src/core/quota.py` | `QuotaInfo`, `DailyQuotaStore`, KST helpers |
| `src/domains/auth/login_lock_store.py` | 실패 횟수·잠금 |
| `src/domains/auth/service.py` | 잠금 + 메일 quota |
| `src/domains/user/schemas.py` | `SignUpResponse.quota` |
| `src/domains/auth/schemas.py` | resend/reset 응답 스키마(필요 시) |
| `src/domains/ocr/schemas.py` | `quota` 필드 |
| `src/domains/ocr/service.py` | OCR consume |
| `src/domains/rag/schemas.py` | `quota` 필드 |
| `src/domains/rag/service.py` | RAG consume |
| `src/api/deps.py` | store DI, OCR/RAG/Auth 주입 |
| `src/api/v1/endpoints/*` | 429 OpenAPI 등록(선택) |
| `tests/unit/test_daily_quota_store.py` | quota 단위 |
| `tests/unit/test_login_lock_store.py` | lock 단위 |
| `tests/unit/test_auth_service.py` | 잠금·메일 한도 |
| `tests/unit/test_ocr_service.py` | OCR 한도 |
| `tests/unit/test_rag_service.py` | RAG 한도 |
| `tests/api/test_auth_api.py` | 잠금·메일 API |

---

### Task 1: ErrorCode · 429 예외 · handler extra · DailyQuotaStore

**Files:**
- Modify: `src/core/exception/codes.py`
- Modify: `src/core/exception/exceptions.py`
- Modify: `src/core/exception/handlers.py`
- Create: `src/core/quota.py`
- Create: `tests/unit/test_daily_quota_store.py`

**Interfaces:**
- Produces:
  - `ErrorCode.LOGIN_LOCKED`, `EMAIL_SEND_LIMIT_EXCEEDED`, `OCR_DAILY_LIMIT_EXCEEDED`, `RAG_DAILY_LIMIT_EXCEEDED`
  - `BaseCustomException(..., extra: dict | None = None)` — `self.extra: dict`
  - `class TooManyRequestsException(BaseCustomException)` — status 429
  - `class QuotaInfo(BaseModel): limit: int; used: int; remaining: int; reset_at: datetime`
  - `EMAIL_SEND_DAILY_LIMIT = 3`, `OCR_DAILY_LIMIT = 3`, `RAG_DAILY_LIMIT = 7`
  - `KIND_EMAIL_SEND = "email_send"`, `KIND_OCR = "ocr"`, `KIND_RAG = "rag"`
  - `def kst_today_yyyymmdd(now: datetime | None = None) -> str`
  - `def kst_next_midnight(now: datetime | None = None) -> datetime`
  - `class DailyQuotaStore`:
    - `__init__(self, redis: Redis) -> None`
    - `async def consume(self, kind: str, subject: str, limit: int) -> QuotaInfo` — 초과 시 `TooManyRequestsException`(code는 호출측에서 매핑하거나 kind별 기본 맵)
    - `async def peek(self, kind: str, subject: str, limit: int) -> QuotaInfo` — 미증가 조회(테스트/선택)

- [ ] **Step 1: Write failing tests for DailyQuotaStore**

`tests/unit/test_daily_quota_store.py`:

```python
import pytest
import fakeredis.aioredis
from datetime import datetime
from zoneinfo import ZoneInfo

from core.exception.exceptions import TooManyRequestsException
from core.quota import (
    DailyQuotaStore,
    EMAIL_SEND_DAILY_LIMIT,
    KIND_EMAIL_SEND,
    kst_next_midnight,
)


@pytest.fixture
async def store():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = DailyQuotaStore(redis)
    yield s
    await redis.aclose()


async def test_consume_increments_and_returns_quota(store: DailyQuotaStore):
    q = await store.consume(KIND_EMAIL_SEND, "a@example.com", EMAIL_SEND_DAILY_LIMIT)
    assert q.limit == 3
    assert q.used == 1
    assert q.remaining == 2
    assert q.reset_at.tzinfo is not None


async def test_consume_over_limit_raises_and_does_not_keep_extra(
    store: DailyQuotaStore,
):
    for _ in range(3):
        await store.consume(KIND_EMAIL_SEND, "a@example.com", 3)
    with pytest.raises(TooManyRequestsException) as ei:
        await store.consume(KIND_EMAIL_SEND, "a@example.com", 3)
    assert ei.value.status_code == 429
    peek = await store.peek(KIND_EMAIL_SEND, "a@example.com", 3)
    assert peek.used == 3
    assert peek.remaining == 0


async def test_subjects_are_independent(store: DailyQuotaStore):
    await store.consume(KIND_EMAIL_SEND, "a@example.com", 3)
    q = await store.consume(KIND_EMAIL_SEND, "b@example.com", 3)
    assert q.used == 1
```

- [ ] **Step 2: Run tests — expect FAIL (module missing)**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv run pytest tests/unit/test_daily_quota_store.py -v
```

Expected: FAIL import / not found

- [ ] **Step 3: Add ErrorCodes**

`src/core/exception/codes.py` 회원 섹션에:

```python
LOGIN_LOCKED = "LOGIN_LOCKED"
EMAIL_SEND_LIMIT_EXCEEDED = "EMAIL_SEND_LIMIT_EXCEEDED"
OCR_DAILY_LIMIT_EXCEEDED = "OCR_DAILY_LIMIT_EXCEEDED"
RAG_DAILY_LIMIT_EXCEEDED = "RAG_DAILY_LIMIT_EXCEEDED"
```

- [ ] **Step 4: Extend BaseCustomException + TooManyRequestsException**

`src/core/exception/exceptions.py`:

```python
class BaseCustomException(Exception):
    def __init__(
        self,
        status_code: int,
        code: str | ErrorCode,
        detail: str,
        *,
        extra: dict | None = None,
    ):
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.extra = extra or {}
        super().__init__(detail)


class TooManyRequestsException(BaseCustomException):
    def __init__(
        self,
        code: str | ErrorCode,
        detail: str,
        *,
        extra: dict | None = None,
    ):
        super().__init__(status_code=429, code=code, detail=detail, extra=extra)
```

모든 기존 `super().__init__(status_code=..., code=..., detail=...)` 호출은 그대로 동작(키워드 `extra` 기본 None).

- [ ] **Step 5: Merge extra in handler**

`src/core/exception/handlers.py`의 `custom_exception_handler`:

```python
content = {
    "status_code": exc.status_code,
    "code": exc.code,
    "detail": exc.detail,
}
if getattr(exc, "extra", None):
    content.update(exc.extra)
return JSONResponse(status_code=exc.status_code, content=content)
```

- [ ] **Step 6: Implement `src/core/quota.py`**

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from redis.asyncio import Redis

from core.exception.codes import ErrorCode
from core.exception.exceptions import TooManyRequestsException

KST = ZoneInfo("Asia/Seoul")

EMAIL_SEND_DAILY_LIMIT = 3
OCR_DAILY_LIMIT = 3
RAG_DAILY_LIMIT = 7

KIND_EMAIL_SEND = "email_send"
KIND_OCR = "ocr"
KIND_RAG = "rag"

_KIND_ERROR = {
    KIND_EMAIL_SEND: (
        ErrorCode.EMAIL_SEND_LIMIT_EXCEEDED,
        "인증 메일 발송 한도를 초과했습니다. 내일 다시 시도해 주세요.",
    ),
    KIND_OCR: (
        ErrorCode.OCR_DAILY_LIMIT_EXCEEDED,
        "OCR 일일 사용 한도를 초과했습니다.",
    ),
    KIND_RAG: (
        ErrorCode.RAG_DAILY_LIMIT_EXCEEDED,
        "레시피 추천 일일 사용 한도를 초과했습니다.",
    ),
}


class QuotaInfo(BaseModel):
    limit: int
    used: int
    remaining: int
    reset_at: datetime


def kst_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(KST)
    if now.tzinfo is None:
        return now.replace(tzinfo=KST)
    return now.astimezone(KST)


def kst_today_yyyymmdd(now: datetime | None = None) -> str:
    return kst_now(now).strftime("%Y%m%d")


def kst_next_midnight(now: datetime | None = None) -> datetime:
    local = kst_now(now)
    tomorrow = (local.date() + timedelta(days=1))
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=KST)


def _ttl_seconds_until_reset(now: datetime | None = None) -> int:
    local = kst_now(now)
    reset = kst_next_midnight(local)
    return max(int((reset - local).total_seconds()), 1)


class DailyQuotaStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, kind: str, subject: str) -> str:
        return f"quota:{kind}:{subject.lower()}:{kst_today_yyyymmdd()}"

    def _snapshot(self, used: int, limit: int) -> QuotaInfo:
        used = max(0, used)
        return QuotaInfo(
            limit=limit,
            used=used,
            remaining=max(0, limit - used),
            reset_at=kst_next_midnight(),
        )

    async def peek(self, kind: str, subject: str, limit: int) -> QuotaInfo:
        raw = await self._redis.get(self._key(kind, subject))
        used = int(raw) if raw is not None else 0
        return self._snapshot(used, limit)

    async def consume(self, kind: str, subject: str, limit: int) -> QuotaInfo:
        key = self._key(kind, subject)
        used = await self._redis.incr(key)
        if used == 1:
            await self._redis.expire(key, _ttl_seconds_until_reset())
        if used > limit:
            await self._redis.decr(key)
            code, detail = _KIND_ERROR[kind]
            snap = self._snapshot(limit, limit)
            raise TooManyRequestsException(
                code=code,
                detail=detail,
                extra={
                    "limit": snap.limit,
                    "remaining": 0,
                    "reset_at": snap.reset_at.isoformat(),
                },
            )
        return self._snapshot(used, limit)
```

- [ ] **Step 7: Run tests — expect PASS**

```bash
uv run pytest tests/unit/test_daily_quota_store.py -v
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/core/exception/codes.py src/core/exception/exceptions.py \
  src/core/exception/handlers.py src/core/quota.py \
  tests/unit/test_daily_quota_store.py
git commit -m "$(cat <<'EOF'
Feat: DailyQuotaStore와 429·한도 ErrorCode 추가

EOF
)"
```

---

### Task 2: LoginLockStore

**Files:**
- Create: `src/domains/auth/login_lock_store.py`
- Create: `tests/unit/test_login_lock_store.py`

**Interfaces:**
- Consumes: Redis
- Produces:
  - `LOGIN_FAIL_LIMIT = 5`
  - `class LoginLockStore`:
    - `__init__(self, redis: Redis) -> None`
    - `async def is_locked(self, email: str) -> bool`
    - `async def record_failure(self, email: str) -> int` — 증가 후 현재 횟수 반환; 키 TTL 24h(미잠금 자연 소멸)
    - `async def clear(self, email: str) -> None`

- [ ] **Step 1: Write failing tests**

```python
import pytest
import fakeredis.aioredis

from domains.auth.login_lock_store import LOGIN_FAIL_LIMIT, LoginLockStore


@pytest.fixture
async def store():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = LoginLockStore(redis)
    yield s
    await redis.aclose()


async def test_not_locked_initially(store: LoginLockStore):
    assert await store.is_locked("a@example.com") is False


async def test_locked_after_five_failures(store: LoginLockStore):
    for i in range(LOGIN_FAIL_LIMIT):
        n = await store.record_failure("a@example.com")
        assert n == i + 1
    assert await store.is_locked("a@example.com") is True


async def test_clear_removes_lock(store: LoginLockStore):
    for _ in range(LOGIN_FAIL_LIMIT):
        await store.record_failure("a@example.com")
    await store.clear("a@example.com")
    assert await store.is_locked("a@example.com") is False
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_login_lock_store.py -v
```

- [ ] **Step 3: Implement**

`src/domains/auth/login_lock_store.py`:

```python
from redis.asyncio import Redis

LOGIN_FAIL_LIMIT = 5
_FAIL_TTL_SECONDS = 24 * 60 * 60


class LoginLockStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, email: str) -> str:
        return f"login_fail:{email.lower()}"

    async def is_locked(self, email: str) -> bool:
        raw = await self._redis.get(self._key(email))
        if raw is None:
            return False
        return int(raw) >= LOGIN_FAIL_LIMIT

    async def record_failure(self, email: str) -> int:
        key = self._key(email)
        n = await self._redis.incr(key)
        if n == 1:
            await self._redis.expire(key, _FAIL_TTL_SECONDS)
        return int(n)

    async def clear(self, email: str) -> None:
        await self._redis.delete(self._key(email))
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/test_login_lock_store.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/domains/auth/login_lock_store.py tests/unit/test_login_lock_store.py
git commit -m "$(cat <<'EOF'
Feat: LoginLockStore로 비밀번호 실패 잠금 카운터 추가

EOF
)"
```

---

### Task 3: AuthService 로그인 잠금 + reset confirm clear

**Files:**
- Modify: `src/domains/auth/service.py`
- Modify: `src/api/deps.py`
- Modify: `tests/unit/test_auth_service.py`

**Interfaces:**
- Consumes: `LoginLockStore`, `DailyQuotaStore`(다음 태스크에서 메일용 — 이번 태스크는 lock만 생성자에 추가하되 quota는 Optional/동시 추가 가능). **이번 태스크에서 `login_lock_store`와 `daily_quota_store`를 둘 다 생성자에 넣고**, 메일 consume은 Task 4.
- Produces: `login` / `confirm_password_reset` 동작 변경

- [ ] **Step 1: Add failing auth_service tests**

`tests/unit/test_auth_service.py` fixture에 `login_lock_store=AsyncMock()`, `daily_quota_store=AsyncMock()` 추가하고 `AuthService(...)`에 전달.

```python
async def test_login_locks_after_five_failures(
    auth_service, user_repo, login_lock_store, existing_user
):
    user_repo.get_user_by_email.return_value = existing_user
    login_lock_store.is_locked = AsyncMock(side_effect=[False] * 5 + [True])
    login_lock_store.record_failure = AsyncMock(side_effect=[1, 2, 3, 4, 5])

    for _ in range(5):
        with pytest.raises(UnAuthorizedException) as ei:
            await auth_service.login(
                LogInRequest(email=existing_user.email, password="wrong-password")
            )
        assert ei.value.code != ErrorCode.LOGIN_LOCKED

    with pytest.raises(UnAuthorizedException) as ei:
        await auth_service.login(
            LogInRequest(email=existing_user.email, password="password123")
        )
    assert ei.value.code == ErrorCode.LOGIN_LOCKED


async def test_login_success_clears_failures(
    auth_service, user_repo, login_lock_store, refresh_store, existing_user
):
    user_repo.get_user_by_email.return_value = existing_user
    login_lock_store.is_locked = AsyncMock(return_value=False)
    login_lock_store.clear = AsyncMock()
    refresh_store.save = AsyncMock()

    await auth_service.login(
        LogInRequest(email=existing_user.email, password="password123")
    )
    login_lock_store.clear.assert_awaited_once()


async def test_password_reset_confirm_clears_lock(
    auth_service, user_repo, verification_store, login_lock_store, existing_user
):
    user_repo.get_user_by_email.return_value = existing_user
    verification_store.verify = AsyncMock()
    login_lock_store.clear = AsyncMock()
    user_repo.save = AsyncMock(side_effect=lambda u: u)

    await auth_service.confirm_password_reset(
        PasswordResetConfirmRequest(
            email=existing_user.email,
            code="123456",
            password="newpass12",
            checked_password="newpass12",
        )
    )
    login_lock_store.clear.assert_awaited_once_with(existing_user.email)
```

(기존 fixture의 `AuthService(...)` 생성자에 `login_lock_store`, `daily_quota_store` 인자 추가. `daily_quota_store.consume`은 기본 AsyncMock.)

- [ ] **Step 2: Run focused tests — expect FAIL**

```bash
uv run pytest tests/unit/test_auth_service.py::test_login_locks_after_five_failures \
  tests/unit/test_auth_service.py::test_login_success_clears_failures \
  tests/unit/test_auth_service.py::test_password_reset_confirm_clears_lock -v
```

- [ ] **Step 3: Wire stores into AuthService + deps**

`AuthService.__init__`에:

```python
login_lock_store: LoginLockStore,
daily_quota_store: DailyQuotaStore,
```

`login` 로직 (기존 유저 조회 이후):

```python
if await self.login_lock_store.is_locked(str(request.email)):
    raise UnAuthorizedException(
        code=ErrorCode.LOGIN_LOCKED,
        detail=(
            "비밀번호를 여러 번 틀려 로그인이 잠겼습니다. "
            "비밀번호 재설정 후 다시 시도해 주세요."
        ),
    )
# password None → 기존
if not security.verify_password(...):
    await self.login_lock_store.record_failure(str(request.email))
    raise UnAuthorizedException(detail="이메일 또는 비밀번호가 올바르지 않습니다.")
# email not verified → 기존
await self.login_lock_store.clear(str(request.email))
# restore + tokens
```

`confirm_password_reset` 성공 경로 끝(save 후):

```python
await self.login_lock_store.clear(email)
```

`deps.get_login_lock_store` / `get_daily_quota_store` 추가 후 `get_auth_service`에 주입.

- [ ] **Step 4: Fix all AuthService constructions in tests**

`rg -n "AuthService\\(" tests` 로 찾아 `login_lock_store`·`daily_quota_store` mock 추가.

- [ ] **Step 5: Run auth unit tests — expect PASS**

```bash
uv run pytest tests/unit/test_auth_service.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/domains/auth/service.py src/api/deps.py tests/unit/test_auth_service.py
git commit -m "$(cat <<'EOF'
Feat: 비밀번호 5회 실패 시 로그인 잠금 및 재설정 해제

EOF
)"
```

---

### Task 4: 인증 메일 발송 일일 3회 + 응답 quota

**Files:**
- Modify: `src/domains/auth/service.py` — `signup`, `resend_verification`, `request_password_reset`
- Modify: `src/domains/user/schemas.py` — `SignUpResponse.quota: QuotaInfo | None = None`
- Modify: `src/domains/auth/schemas.py` — resend/reset 응답용 모델이 없으면 dict에 `quota` 키 추가(엔드포인트가 dict 반환 중이면 Pydantic 모델 추가 권장)
- Modify: `src/api/v1/endpoints/auth.py` — response_model 정리
- Modify: `tests/unit/test_auth_service.py`
- Modify: `tests/api/test_auth_api.py` (필요 시)

**Interfaces:**
- Consumes: `DailyQuotaStore.consume(KIND_EMAIL_SEND, email, EMAIL_SEND_DAILY_LIMIT) -> QuotaInfo`
- Produces: 발송 성공 응답에 `quota` dict/모델

- [ ] **Step 1: Failing unit tests**

```python
async def test_signup_consumes_email_quota(
    auth_service, user_repo, signup_pending_store, verification_store,
    email_service, daily_quota_store
):
    user_repo.get_user_by_email.return_value = None
    user_repo.get_user_by_nickname.return_value = None
    daily_quota_store.consume = AsyncMock(
        return_value=QuotaInfo(
            limit=3, used=1, remaining=2,
            reset_at=kst_next_midnight(),
        )
    )
    verification_store.issue = AsyncMock(return_value="123456")
    result = await auth_service.signup(SignUpRequest(
        email="new@example.com",
        password="password123",
        checked_password="password123",
        nickname="newbie",
    ))
    daily_quota_store.consume.assert_awaited_once()
    assert result["quota"]["remaining"] == 2


async def test_signup_blocks_when_email_quota_exceeded(
    auth_service, user_repo, daily_quota_store, verification_store
):
    user_repo.get_user_by_email.return_value = None
    user_repo.get_user_by_nickname.return_value = None
    daily_quota_store.consume = AsyncMock(
        side_effect=TooManyRequestsException(
            code=ErrorCode.EMAIL_SEND_LIMIT_EXCEEDED,
            detail="...",
        )
    )
    with pytest.raises(TooManyRequestsException):
        await auth_service.signup(...)
    verification_store.issue.assert_not_called()


async def test_password_reset_request_skips_quota_when_no_user(
    auth_service, user_repo, daily_quota_store, email_service
):
    user_repo.get_user_by_email.return_value = None
    result = await auth_service.request_password_reset("ghost@example.com")
    daily_quota_store.consume.assert_not_called()
    email_service.send_verification_code.assert_not_called()
    assert "quota" not in result
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_auth_service.py -k "email_quota or password_reset_request_skips" -v
```

- [ ] **Step 3: Implement consume-before-send**

공통 헬퍼:

```python
async def _consume_email_send(self, email: str) -> QuotaInfo:
    return await self.daily_quota_store.consume(
        KIND_EMAIL_SEND, email, EMAIL_SEND_DAILY_LIMIT
    )
```

`signup`: pending upsert 후, `issue` 전에 `_consume_email_send`; 응답에 `quota=q.model_dump(mode="json")` (또는 QuotaInfo 그대로 SignUpResponse가 받도록).

`resend_verification`: resend/issue 전에 consume; 반환 `{"ok": True, "expires_in_seconds": ..., "quota": ...}`.

`request_password_reset`: user 있고 password 있을 때만 consume → issue → send; 응답에 quota. 아니면 기존 `{"ok": True, "message": "..."}`만.

`SignUpResponse`:

```python
from core.quota import QuotaInfo

class SignUpResponse(BaseModel):
    email: EmailStr
    message: str = "verification_code_sent"
    expires_in_seconds: int = 180
    quota: QuotaInfo | None = None
```

엔드포인트 `SignUpResponse(**result)`가 quota를 포함하도록 signup 반환 키에 `expires_in_seconds`도 맞출 것(현재 service가 expires를 안 넣으면 스키마 기본값 180 사용 — `SignUpResponse(**result)` 시 email/message/quota만 있으면 OK).

- [ ] **Step 4: Run unit + auth API tests**

```bash
uv run pytest tests/unit/test_auth_service.py tests/api/test_auth_api.py -v
```

Expected: PASS (깨진 fixture/응답 assertion 수정)

- [ ] **Step 5: Commit**

```bash
git add src/domains/auth/service.py src/domains/user/schemas.py \
  src/domains/auth/schemas.py src/api/v1/endpoints/auth.py \
  tests/unit/test_auth_service.py tests/api/test_auth_api.py
git commit -m "$(cat <<'EOF'
Feat: 인증 메일 발송 일일 3회 한도 및 quota 응답

EOF
)"
```

---

### Task 5: OCR 일일 3회

**Files:**
- Modify: `src/domains/ocr/schemas.py`
- Modify: `src/domains/ocr/service.py`
- Modify: `src/api/deps.py` — `get_ocr_service(user, quota_store)`
- Modify: `tests/unit/test_ocr_service.py`

**Interfaces:**
- Consumes: `DailyQuotaStore.consume(KIND_OCR, str(user_id), OCR_DAILY_LIMIT)`
- Produces: `OcrReceiptResponse.quota: QuotaInfo`

- [ ] **Step 1: Failing tests**

```python
@pytest.mark.asyncio
async def test_parse_receipt_consumes_quota():
    extract = AsyncMock(return_value="계란")
    parse = AsyncMock(return_value=["계란"])
    quota = AsyncMock()
    quota.consume = AsyncMock(
        return_value=QuotaInfo(limit=3, used=1, remaining=2, reset_at=kst_next_midnight())
    )
    user_id = uuid6.uuid7()
    service = OcrService(
        api_url="https://ocr.test",
        secret_key="secret",
        openai_api_key="openai",
        llm_model="gpt-4o-mini",
        extract_text_fn=extract,
        parse_receipt_text_fn=parse,
        daily_quota_store=quota,
        user_id=user_id,
    )
    result = await service.parse_receipt(b"img", "image/jpeg", "a.jpg")
    quota.consume.assert_awaited_once_with(KIND_OCR, str(user_id), OCR_DAILY_LIMIT)
    assert result.quota is not None
    assert result.quota.remaining == 2
    extract.assert_awaited_once()


@pytest.mark.asyncio
async def test_parse_receipt_bad_request_skips_quota():
    quota = AsyncMock()
    service = OcrService(
        api_url="u", secret_key="s", openai_api_key="k", llm_model="m",
        extract_text_fn=AsyncMock(), parse_receipt_text_fn=AsyncMock(),
        daily_quota_store=quota, user_id=uuid6.uuid7(),
    )
    with pytest.raises(BadRequestException):
        await service.parse_receipt(b"", "image/jpeg", "a.jpg")
    quota.consume.assert_not_called()
```

기존 happy_path 테스트도 `daily_quota_store`·`user_id` 인자 추가.

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_ocr_service.py -v
```

- [ ] **Step 3: Implement**

```python
# OcrService.__init__ 추가
daily_quota_store: DailyQuotaStore,
user_id: UUID,

# parse_receipt: 검증 통과 후
quota = await self._daily_quota_store.consume(
    KIND_OCR, str(self._user_id), OCR_DAILY_LIMIT
)
# 그다음 extract / parse
return OcrReceiptResponse(ingredients=ingredients, quota=quota)
```

`get_ocr_service`:

```python
def get_ocr_service(
    user: User = Depends(get_current_user),
    quota_store: DailyQuotaStore = Depends(get_daily_quota_store),
) -> OcrService:
    return OcrService(
        ...,
        daily_quota_store=quota_store,
        user_id=user.id,
    )
```

`OcrReceiptResponse`에 `quota: QuotaInfo`.

- [ ] **Step 4: Run OCR unit + API**

```bash
uv run pytest tests/unit/test_ocr_service.py tests/api/test_ocr_api.py -v
```

API 테스트 mock이 `parse_receipt`만 쓰므로 대개 통과. 깨지면 override 유지.

- [ ] **Step 5: Commit**

```bash
git add src/domains/ocr/schemas.py src/domains/ocr/service.py src/api/deps.py \
  tests/unit/test_ocr_service.py
git commit -m "$(cat <<'EOF'
Feat: OCR 일일 3회 한도 및 quota 응답

EOF
)"
```

---

### Task 6: RAG 일일 7회

**Files:**
- Modify: `src/domains/rag/schemas.py`
- Modify: `src/domains/rag/service.py`
- Modify: `src/api/deps.py`
- Modify: `tests/unit/test_rag_service.py`

**Interfaces:**
- Consumes: `DailyQuotaStore.consume(KIND_RAG, str(user.id), RAG_DAILY_LIMIT)` — **retriever.search 직전**, 재료가 있을 때만
- Produces: `RecipeRecommendationResponse.quota: QuotaInfo | None` — 재료 없으면 `quota=None` 또는 미차감 스냅샷 없이 null

- [ ] **Step 1: Failing tests**

`rag_service` fixture에 `daily_quota_store=AsyncMock()` 추가.

```python
async def test_recommend_consumes_rag_quota(
    rag_service, scope_loader, retriever, user, daily_quota_store
):
    # 기존처럼 재료 1개 + docs 설정
    daily_quota_store.consume = AsyncMock(
        return_value=QuotaInfo(limit=7, used=1, remaining=6, reset_at=kst_next_midnight())
    )
    result = await rag_service.recommend_recipes()
    daily_quota_store.consume.assert_awaited_once_with(
        KIND_RAG, str(user.id), RAG_DAILY_LIMIT
    )
    assert result.quota.remaining == 6


async def test_recommend_empty_skips_quota(
    rag_service, scope_loader, retriever, daily_quota_store, user
):
    _set_personal_scope(scope_loader, user, [])
    result = await rag_service.recommend_recipes()
    daily_quota_store.consume.assert_not_called()
    assert result.quota is None
```

모든 `RagService(...)` 생성 위치에 `daily_quota_store` 전달.

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_rag_service.py -k "quota" -v
```

- [ ] **Step 3: Implement**

```python
class RagService:
    def __init__(..., daily_quota_store: DailyQuotaStore):
        ...
        self.daily_quota_store = daily_quota_store

    async def recommend_recipes(...):
        ...
        if not names:
            return RecipeRecommendationResponse(
                ingredients_used=[], recipes=[], quota=None
            )
        quota = await self.daily_quota_store.consume(
            KIND_RAG, str(self.user.id), RAG_DAILY_LIMIT
        )
        docs_with_scores = await asyncio.to_thread(...)
        ...
        return RecipeRecommendationResponse(
            ingredients_used=names, recipes=recipes, quota=quota
        )
```

`get_rag_service`에 `quota_store` 주입.

- [ ] **Step 4: Full related tests**

```bash
uv run pytest tests/unit/test_rag_service.py tests/unit/test_ocr_service.py \
  tests/unit/test_auth_service.py tests/unit/test_daily_quota_store.py \
  tests/unit/test_login_lock_store.py tests/api/test_auth_api.py \
  tests/api/test_ocr_api.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domains/rag/schemas.py src/domains/rag/service.py src/api/deps.py \
  tests/unit/test_rag_service.py
git commit -m "$(cat <<'EOF'
Feat: RAG 추천 일일 7회 한도 및 quota 응답

EOF
)"
```

---

### Task 7: API 회귀 · OpenAPI 429 · 최종 검증

**Files:**
- Modify: `src/api/v1/endpoints/auth.py` — `TooManyRequestsException` responses
- Modify: `src/api/v1/endpoints/ocr.py`, `rag.py` — 동일
- Modify: `tests/api/test_auth_api.py` — 로그인 잠금 E2E(가능하면 fakeredis 실스토어)

**Interfaces:**
- Produces: 통합 확인 완료

- [ ] **Step 1: Add API test for login lock (optional but recommended)**

`tests/api/test_auth_api.py`에 검증된 유저로 비번 5회 틀린 뒤 6번째(또는 올바른 비번)에 `LOGIN_LOCKED` 확인. 기존 `fixed_email_code`·signup/verify 플로우 재사용.

- [ ] **Step 2: Register OpenAPI error responses**

`create_error_response(..., TooManyRequestsException)`를 auth/ocr/rag 해당 라우트에 추가.

- [ ] **Step 3: Full test suite slice**

```bash
uv run pytest tests/unit/test_daily_quota_store.py tests/unit/test_login_lock_store.py \
  tests/unit/test_auth_service.py tests/unit/test_ocr_service.py \
  tests/unit/test_rag_service.py tests/api/test_auth_api.py \
  tests/api/test_ocr_api.py -v
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add src/api/v1/endpoints/auth.py src/api/v1/endpoints/ocr.py \
  src/api/v1/endpoints/rag.py tests/api/test_auth_api.py
git commit -m "$(cat <<'EOF'
Test: 로그인 잠금·한도 API 회귀 및 OpenAPI 429 등록

EOF
)"
```

---

## Spec Coverage Checklist

| Spec 요구 | Task |
|-----------|------|
| 비밀번호 5회 실패 잠금 | 2, 3 |
| reset confirm으로 해제 | 3 |
| LOGIN_LOCKED 401 | 1, 3 |
| 메일 발송 하루 3회 | 1, 4 |
| OCR 3 / RAG 7 | 5, 6 |
| 성공 응답 quota | 4, 5, 6 |
| 429 + extra limit/remaining/reset_at | 1 |
| reset request 미발송 시 quota 숨김 | 4 |
| 클라이언트 오류 미차감 | 5 |
| RAG 빈 재료 미차감 | 6 |
| KST 자정 | 1 |
| 앱 미수정 | Global |

## Placeholder / Consistency Notes

- `QuotaInfo.reset_at`은 timezone-aware; JSON은 ISO8601 (`model_dump(mode="json")` 또는 FastAPI 직렬화).
- `DailyQuotaStore.consume`이 kind별 ErrorCode를 직접 raise — 서비스는 별도 매핑 불필요.
- Task 3에서 `daily_quota_store`를 생성자에 미리 넣어 Task 4 fixture churn을 줄임.
