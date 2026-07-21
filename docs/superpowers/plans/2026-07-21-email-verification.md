# 이메일 인증 (회원가입 · 비밀번호 찾기) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이메일 가입에 6자리 코드 인증을 넣고, 미인증 로그인을 막으며, 동일 코드 방식으로 비밀번호 찾기를 추가한다.

**Architecture:** SMTP(또는 console)로 코드를 발송하고, Redis에 해시·쿨다운·시도 횟수를 저장한다. 가입 시 계정만 만들고 토큰은 발급하지 않으며, verify 성공 시 JWT를 발급한다. 카카오 가입은 `is_email_verified=True`로 생성한다.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, redis.asyncio, fakeredis, aiosmtplib(또는 stdlib `smtplib` + `asyncio.to_thread`), pytest

**Spec:** `docs/superpowers/specs/2026-07-21-email-verification-design.md`

## Global Constraints

- 인증 코드: 6자리 숫자, TTL 10분, 재발송 쿨다운 60초, 실패 5회 시 코드 무효화
- Redis key: `email_code:{purpose}:{email}`, cooldown: `email_code_cooldown:{purpose}:{email}` (`purpose` = `signup` | `password_reset`)
- Redis에는 코드 해시만 저장 (평문은 메일에만)
- 이메일 가입: `is_email_verified=False` → verify 전 로그인 불가 (`EMAIL_NOT_VERIFIED`)
- 카카오 가입: `is_email_verified=True`, 이메일 인증 생략
- password reset request: 계정 존재 여부 숨김 (항상 동일 성공 응답)
- 프론트엔드(앱) UI는 범위 밖 (백엔드만)
- 커밋 메시지: `Feat:` / `Test:` / `Docs:` / `Fix:`
- 작업 디렉터리: `/Users/jeong-yeonghun/Desktop/saksak/back`

---

## File Structure

| Path | Responsibility |
|------|----------------|
| `src/core/exception/codes.py` | `EMAIL_NOT_VERIFIED`, `INVALID_VERIFICATION_CODE`, `VERIFICATION_COOLDOWN`, `EMAIL_ALREADY_VERIFIED` |
| `src/domains/user/model.py` | `is_email_verified: bool` |
| `alembic/versions/f6a7b8c9d0e1_add_is_email_verified.py` | 컬럼 추가 + 기존 유저 `True` 백필 |
| `src/core/config.py` | `EMAIL_BACKEND`, SMTP_* 설정 |
| `src/domains/auth/verification_store.py` | Redis 코드 발급·검증·쿨다운 |
| `src/domains/auth/email_service.py` | console/SMTP 메일 발송 |
| `src/domains/auth/schemas.py` | verify/resend/reset request·confirm 스키마 |
| `src/domains/user/schemas.py` | `SignUpResponse` → `{ email, message }` |
| `src/domains/user/service.py` | signup 시 `is_email_verified=False` |
| `src/domains/auth/service.py` | login 가드, verify/resend/reset, kakao complete 시 verified |
| `src/api/deps.py` | VerificationCodeStore / EmailService DI |
| `src/api/v1/endpoints/user.py` | signup: 토큰 제거 + 코드 발송 |
| `src/api/v1/endpoints/auth.py` | verify / resend / password reset |
| `tests/unit/test_verification_store.py` | 코드 저장소 단위 |
| `tests/unit/test_email_service.py` | console 백엔드 |
| `tests/unit/test_auth_service.py` | verify/login/reset |
| `tests/unit/test_user_service.py` | signup verified=False |
| `tests/api/test_auth_api.py` | API E2E (코드 생성 mock) |

---

### Task 1: ErrorCode + User 모델 + 마이그레이션

**Files:**
- Modify: `src/core/exception/codes.py`
- Modify: `src/domains/user/model.py`
- Create: `alembic/versions/f6a7b8c9d0e1_add_is_email_verified.py`
- Modify: `tests/unit/test_user_service.py`

**Interfaces:**
- Produces: `User.is_email_verified: bool` (default `False` in model; migration backfills existing to `True`)
- Produces: `ErrorCode.EMAIL_NOT_VERIFIED`, `INVALID_VERIFICATION_CODE`, `VERIFICATION_COOLDOWN`, `EMAIL_ALREADY_VERIFIED`

- [ ] **Step 1: ErrorCode 추가**

`src/core/exception/codes.py` 회원 관련 섹션에:

```python
EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
INVALID_VERIFICATION_CODE = "INVALID_VERIFICATION_CODE"
VERIFICATION_COOLDOWN = "VERIFICATION_COOLDOWN"
EMAIL_ALREADY_VERIFIED = "EMAIL_ALREADY_VERIFIED"
```

- [ ] **Step 2: User 모델 필드 추가**

`src/domains/user/model.py`에:

```python
from sqlalchemy import Boolean, String, DateTime, func, Index
# ...
is_email_verified: Mapped[bool] = mapped_column(
    Boolean, nullable=False, default=False, server_default="false"
)
```

- [ ] **Step 3: Alembic 마이그레이션**

`down_revision = "e5f6a7b8c9d0"` (현재 head).

```python
"""add_is_email_verified

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute("UPDATE users SET is_email_verified = true")
    op.alter_column("users", "is_email_verified", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_email_verified")
```

- [ ] **Step 4: signup 단위 테스트에 verified=False 검증 추가**

`tests/unit/test_user_service.py`의 `test_sign_up_creates_user`에:

```python
assert user.is_email_verified is False
```

아직 `sign_up`이 필드를 안 넣어도 SQLAlchemy default로 `False`가 될 수 있음. 명시적으로 `User(..., is_email_verified=False)`를 `sign_up`에 넣는 것은 Task 4에서 처리. 이 Task에서는 모델·마이그레이션만.

- [ ] **Step 5: Commit**

```bash
git add src/core/exception/codes.py src/domains/user/model.py alembic/versions/f6a7b8c9d0e1_add_is_email_verified.py
git commit -m "$(cat <<'EOF'
Feat: User.is_email_verified 및 이메일 인증 ErrorCode 추가

EOF
)"
```

---

### Task 2: VerificationCodeStore (Redis)

**Files:**
- Create: `src/domains/auth/verification_store.py`
- Create: `tests/unit/test_verification_store.py`

**Interfaces:**
- Produces:
  - `PURPOSE_SIGNUP = "signup"`, `PURPOSE_PASSWORD_RESET = "password_reset"`
  - `CODE_TTL_SECONDS = 600`, `COOLDOWN_SECONDS = 60`, `MAX_ATTEMPTS = 5`
  - `VerificationCodeStore.issue(purpose: str, email: str) -> str` — 쿨다운 중이면 `BadRequestException(VERIFICATION_COOLDOWN)`; 평문 6자리 반환
  - `VerificationCodeStore.verify(purpose: str, email: str, code: str) -> None` — 실패 시 `BadRequestException(INVALID_VERIFICATION_CODE)`; 성공 시 키 삭제
  - `hash_email_code(code: str) -> str` (sha256)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/test_verification_store.py`:

```python
import fakeredis.aioredis
import pytest

from core.exception.codes import ErrorCode
from core.exception.exceptions import BadRequestException
from domains.auth.verification_store import (
    PURPOSE_SIGNUP,
    VerificationCodeStore,
)


@pytest.fixture
async def store():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = VerificationCodeStore(redis)
    yield s
    await redis.aclose()


async def test_issue_and_verify_success(store: VerificationCodeStore):
    code = await store.issue(PURPOSE_SIGNUP, "a@example.com")
    assert len(code) == 6 and code.isdigit()
    await store.verify(PURPOSE_SIGNUP, "a@example.com", code)


async def test_verify_wrong_code_raises(store: VerificationCodeStore):
    await store.issue(PURPOSE_SIGNUP, "a@example.com")
    with pytest.raises(BadRequestException) as ei:
        await store.verify(PURPOSE_SIGNUP, "a@example.com", "000000")
    assert ei.value.code == ErrorCode.INVALID_VERIFICATION_CODE


async def test_cooldown_blocks_reissue(store: VerificationCodeStore):
    await store.issue(PURPOSE_SIGNUP, "a@example.com")
    with pytest.raises(BadRequestException) as ei:
        await store.issue(PURPOSE_SIGNUP, "a@example.com")
    assert ei.value.code == ErrorCode.VERIFICATION_COOLDOWN


async def test_five_failures_invalidate_code(store: VerificationCodeStore):
    await store.issue(PURPOSE_SIGNUP, "a@example.com")
    for _ in range(5):
        with pytest.raises(BadRequestException):
            await store.verify(PURPOSE_SIGNUP, "a@example.com", "000000")
    with pytest.raises(BadRequestException) as ei:
        await store.verify(PURPOSE_SIGNUP, "a@example.com", "000000")
    assert ei.value.code == ErrorCode.INVALID_VERIFICATION_CODE
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
uv run pytest tests/unit/test_verification_store.py -v
```

Expected: import/collection FAIL (`VerificationCodeStore` 없음)

- [ ] **Step 3: 구현**

`src/domains/auth/verification_store.py`:

```python
import hashlib
import json
import secrets

from redis.asyncio import Redis

from core.exception.codes import ErrorCode
from core.exception.exceptions import BadRequestException, ExternalServiceException

PURPOSE_SIGNUP = "signup"
PURPOSE_PASSWORD_RESET = "password_reset"
CODE_TTL_SECONDS = 600
COOLDOWN_SECONDS = 60
MAX_ATTEMPTS = 5


def hash_email_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def generate_email_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


class VerificationCodeStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _code_key(self, purpose: str, email: str) -> str:
        return f"email_code:{purpose}:{email.lower()}"

    def _cooldown_key(self, purpose: str, email: str) -> str:
        return f"email_code_cooldown:{purpose}:{email.lower()}"

    async def issue(self, purpose: str, email: str) -> str:
        email = email.lower()
        cooldown_key = self._cooldown_key(purpose, email)
        try:
            if await self._redis.exists(cooldown_key):
                raise BadRequestException(
                    code=ErrorCode.VERIFICATION_COOLDOWN,
                    detail="인증 코드 재발송은 잠시 후 다시 시도해 주세요.",
                )
            code = generate_email_code()
            payload = json.dumps(
                {"hash": hash_email_code(code), "attempts": 0}
            )
            pipe = self._redis.pipeline()
            pipe.set(self._code_key(purpose, email), payload, ex=CODE_TTL_SECONDS)
            pipe.set(cooldown_key, "1", ex=COOLDOWN_SECONDS)
            await pipe.execute()
            return code
        except BadRequestException:
            raise
        except Exception as exc:
            raise ExternalServiceException("인증 코드 저장에 실패했습니다.") from exc

    async def verify(self, purpose: str, email: str, code: str) -> None:
        email = email.lower()
        key = self._code_key(purpose, email)
        try:
            raw = await self._redis.get(key)
            if raw is None:
                raise BadRequestException(
                    code=ErrorCode.INVALID_VERIFICATION_CODE,
                    detail="인증 코드가 올바르지 않거나 만료되었습니다.",
                )
            data = json.loads(raw)
            if data["hash"] != hash_email_code(code):
                attempts = int(data.get("attempts", 0)) + 1
                if attempts >= MAX_ATTEMPTS:
                    await self._redis.delete(key)
                else:
                    data["attempts"] = attempts
                    ttl = await self._redis.ttl(key)
                    ex = ttl if ttl and ttl > 0 else CODE_TTL_SECONDS
                    await self._redis.set(key, json.dumps(data), ex=ex)
                raise BadRequestException(
                    code=ErrorCode.INVALID_VERIFICATION_CODE,
                    detail="인증 코드가 올바르지 않거나 만료되었습니다.",
                )
            await self._redis.delete(key)
        except BadRequestException:
            raise
        except Exception as exc:
            raise ExternalServiceException("인증 코드 검증에 실패했습니다.") from exc
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/unit/test_verification_store.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domains/auth/verification_store.py tests/unit/test_verification_store.py
git commit -m "$(cat <<'EOF'
Feat: Redis 이메일 인증 코드 저장소 추가

EOF
)"
```

---

### Task 3: Settings + EmailService

**Files:**
- Modify: `src/core/config.py`
- Create: `src/domains/auth/email_service.py`
- Create: `tests/unit/test_email_service.py`

**Interfaces:**
- Produces: `Settings.EMAIL_BACKEND: str = "console"` (`smtp` | `console`)
- Produces: `SMTP_HOST`, `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME="삭삭"`, `SMTP_USE_TLS=True` (모두 Optional/기본값 가능 — console만 쓸 때 불필요)
- Produces: `EmailService.send_verification_code(to_email: str, code: str, purpose: str) -> None`

- [ ] **Step 1: 실패하는 테스트**

```python
import logging

import pytest

from domains.auth.email_service import EmailService
from domains.auth.verification_store import PURPOSE_SIGNUP


def test_console_backend_logs_code(caplog: pytest.LogCaptureFixture):
    svc = EmailService(backend="console")
    with caplog.at_level(logging.INFO):
        # sync wrapper or asyncio.run depending on impl — prefer async
        import asyncio

        asyncio.run(
            svc.send_verification_code("a@example.com", "123456", PURPOSE_SIGNUP)
        )
    assert "123456" in caplog.text
    assert "a@example.com" in caplog.text
```

- [ ] **Step 2: Settings 확장**

```python
EMAIL_BACKEND: str = "console"  # console | smtp
SMTP_HOST: str | None = None
SMTP_PORT: int = 587
SMTP_USER: str | None = None
SMTP_PASSWORD: SecretStr | None = None
SMTP_FROM_EMAIL: str | None = None
SMTP_FROM_NAME: str = "삭삭"
SMTP_USE_TLS: bool = True
```

- [ ] **Step 3: EmailService 구현**

`src/domains/auth/email_service.py`:

- `backend=="console"`: loguru/logging으로 to/code/purpose 출력
- `backend=="smtp"`: `aiosmtplib` 또는 `smtplib`+`asyncio.to_thread`로 발송
  - 제목: purpose에 따라 `회원가입 인증 코드` / `비밀번호 재설정 인증 코드`
  - 본문: 코드 + "10분간 유효"
- SMTP 설정 누락 시 `ExternalServiceException`

의존성: `aiosmtplib`가 없으면 stdlib `smtplib` + `email.message.EmailMessage` + `asyncio.to_thread`로 충분 (새 패키지 최소화).

- [ ] **Step 4: 테스트 통과 + Commit**

```bash
uv run pytest tests/unit/test_email_service.py -v
git add src/core/config.py src/domains/auth/email_service.py tests/unit/test_email_service.py
git commit -m "$(cat <<'EOF'
Feat: SMTP/console 이메일 발송 서비스 추가

EOF
)"
```

---

### Task 4: Auth/User 서비스 — signup·verify·resend·login 가드·kakao

**Files:**
- Modify: `src/domains/user/schemas.py` (`SignUpResponse`)
- Modify: `src/domains/auth/schemas.py` (요청/응답 스키마)
- Modify: `src/domains/user/service.py`
- Modify: `src/domains/auth/service.py`
- Modify: `tests/unit/test_user_service.py`
- Modify: `tests/unit/test_auth_service.py`

**Interfaces:**
- Consumes: `VerificationCodeStore`, `EmailService`
- Produces:
  - `SignUpResponse(email: EmailStr, message: str)` — `message="verification_code_sent"`
  - `EmailVerifyRequest(email, code)`, `EmailResendRequest(email)`
  - `AuthService.verify_email(request) -> LogInResponse`
  - `AuthService.resend_verification(request) -> dict`
  - `AuthService.login`: 미인증 시 `UnAuthorizedException(EMAIL_NOT_VERIFIED)`
  - `complete_kakao_signup`: `User(..., is_email_verified=True)`
  - `UserService.sign_up`: `is_email_verified=False`
  - `AuthService.send_signup_code(email: str) -> None` (issue + send)

- [ ] **Step 1: 스키마**

`SignUpResponse`:

```python
class SignUpResponse(BaseModel):
    email: EmailStr
    message: str = "verification_code_sent"
```

`domains/auth/schemas.py`에:

```python
class EmailVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class EmailResendRequest(BaseModel):
    email: EmailStr
```

- [ ] **Step 2: UserService.sign_up에 `is_email_verified=False` 명시**

```python
user = User(
    email=str(request.email),
    password=hashed_password,
    nickname=request.nickname,
    is_email_verified=False,
)
```

- [ ] **Step 3: AuthService 생성자·메서드**

```python
def __init__(
    self,
    user_repo: UserRepository,
    refresh_store: RefreshTokenStore,
    verification_store: VerificationCodeStore,
    email_service: EmailService,
) -> None:
    ...
```

`login`에 비밀번호 검증 후:

```python
if not user.is_email_verified:
    raise UnAuthorizedException(
        code=ErrorCode.EMAIL_NOT_VERIFIED,
        detail="이메일 인증이 필요합니다.",
    )
```

(`UnAuthorizedException`이 `code`를 받는지 확인 — 받으면 사용, 아니면 `BadRequestException`/`ForbiddenException` 중 스펙의 `EMAIL_NOT_VERIFIED`를 담을 수 있는 예외 사용. 기존 `UnAuthorizedException(code=..., detail=...)` 시그니처를 `exceptions.py`에서 확인.)

`verify_email`:
1. user by email — 없으면 `UserNotFoundException`
2. 이미 verified → `BadRequestException(EMAIL_ALREADY_VERIFIED)`
3. `verification_store.verify(PURPOSE_SIGNUP, email, code)`
4. `user.is_email_verified = True`; save
5. issue tokens → LogInResponse

`resend_verification`:
1. user 없으면 `UserNotFoundException`
2. already verified → `EMAIL_ALREADY_VERIFIED`
3. `code = await verification_store.issue(...)`; `await email_service.send_verification_code(...)`
4. return `{"ok": True}`

`send_signup_code(email)`: issue + send (signup 엔드포인트용)

`complete_kakao_signup` User 생성 시 `is_email_verified=True`

- [ ] **Step 4: 단위 테스트**

`test_auth_service.py`에 (mock store/email):

- `test_login_rejects_unverified_email_user`
- `test_verify_email_issues_tokens`
- `test_complete_kakao_sets_verified_true` (기존 complete 테스트가 있으면 assertion 추가)

`test_user_service.py`: `assert user.is_email_verified is False`

- [ ] **Step 5: 테스트 통과 + Commit**

```bash
uv run pytest tests/unit/test_auth_service.py tests/unit/test_user_service.py -v
git add src/domains/user/schemas.py src/domains/auth/schemas.py \
  src/domains/user/service.py src/domains/auth/service.py \
  tests/unit/test_auth_service.py tests/unit/test_user_service.py
git commit -m "$(cat <<'EOF'
Feat: 이메일 인증 verify/resend 및 미인증 로그인 차단

EOF
)"
```

---

### Task 5: 비밀번호 찾기 (reset request / confirm)

**Files:**
- Modify: `src/domains/auth/schemas.py`
- Modify: `src/domains/auth/service.py`
- Modify: `tests/unit/test_auth_service.py`

**Interfaces:**
- Produces:
  - `PasswordResetRequest(email: EmailStr)`
  - `PasswordResetConfirmRequest(email, code, password, checked_password)` — password 규칙은 SignUp과 동일(8~20, match validator)
  - `AuthService.request_password_reset(email) -> dict` — 항상 `{"ok": True, "message": "password_reset_email_sent"}`
  - `AuthService.confirm_password_reset(request) -> dict` — 성공 시 `{"ok": True}`

- [ ] **Step 1: 스키마 + 실패 테스트**

```python
async def test_request_password_reset_always_ok_even_if_missing(
    auth_service, user_repo
):
    user_repo.get_user_by_email.return_value = None
    result = await auth_service.request_password_reset("no@example.com")
    assert result["ok"] is True
    # email_service.send NOT called


async def test_confirm_password_reset_updates_password(
    auth_service, user_repo, verification_store
):
    # arrange verified email user with password
    # issue code via store, confirm with new password
    # assert hash changed / verify_password works
```

- [ ] **Step 2: 구현**

`request_password_reset`:
- user 조회
- 없거나 `password is None`(카카오 전용)이면 발송 스킵, 그래도 동일 응답
- 있으면 `issue(PURPOSE_PASSWORD_RESET)` + `send_verification_code`

`confirm_password_reset`:
- password == checked_password 검증 (스키마 validator 또는 BadRequest PASSWORD_MISMATCH)
- user 없으면 `INVALID_VERIFICATION_CODE` 또는 `USER_NOT_FOUND` — 존재 여부가 드러나지 않게 **코드 검증과 동일하게** `INVALID_VERIFICATION_CODE`로 통일 권장
- `password is None` → 동일하게 invalid
- `verification_store.verify(PURPOSE_PASSWORD_RESET, ...)`
- `user.password = hash_password(...)`; save
- return `{"ok": True}`

- [ ] **Step 3: 테스트 통과 + Commit**

```bash
uv run pytest tests/unit/test_auth_service.py -v -k password_reset
git add src/domains/auth/schemas.py src/domains/auth/service.py tests/unit/test_auth_service.py
git commit -m "$(cat <<'EOF'
Feat: 비밀번호 찾기 코드 발송·확인 서비스 추가

EOF
)"
```

---

### Task 6: DI + API 엔드포인트

**Files:**
- Modify: `src/api/deps.py`
- Modify: `src/api/v1/endpoints/user.py`
- Modify: `src/api/v1/endpoints/auth.py`

**Interfaces:**
- Produces endpoints:
  - `POST /api/v1/users/signup` → `SignUpResponse` (토큰 없음, 코드 발송)
  - `POST /api/v1/auth/email/verify`
  - `POST /api/v1/auth/email/resend`
  - `POST /api/v1/auth/password/reset/request`
  - `POST /api/v1/auth/password/reset/confirm`

- [ ] **Step 1: deps**

```python
def get_verification_store() -> VerificationCodeStore:
    return VerificationCodeStore(get_redis())


def get_email_service() -> EmailService:
    return EmailService.from_settings(settings)  # 또는 EmailService(...)


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repo),
    refresh_store: RefreshTokenStore = Depends(get_refresh_store),
    verification_store: VerificationCodeStore = Depends(get_verification_store),
    email_service: EmailService = Depends(get_email_service),
) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        refresh_store=refresh_store,
        verification_store=verification_store,
        email_service=email_service,
    )
```

- [ ] **Step 2: signup 엔드포인트**

```python
@router.post("/signup", status_code=201, response_model=SignUpResponse)
async def signup(
    request: SignUpRequest,
    user_service: UserService = Depends(get_user_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> SignUpResponse:
    user = await user_service.sign_up(request)
    await auth_service.send_signup_code(user.email)
    return SignUpResponse(email=user.email, message="verification_code_sent")
```

- [ ] **Step 3: auth 엔드포인트 4개 추가**

`verify` → `LogInResponse`  
`resend` / `reset/request` / `reset/confirm` → 각 서비스 반환

- [ ] **Step 4: Commit**

```bash
git add src/api/deps.py src/api/v1/endpoints/user.py src/api/v1/endpoints/auth.py
git commit -m "$(cat <<'EOF'
Feat: 이메일 인증·비밀번호 찾기 API 엔드포인트 연결

EOF
)"
```

---

### Task 7: API 테스트 업데이트 + E2E

**Files:**
- Modify: `tests/api/test_auth_api.py`
- Modify: `tests/conftest.py` (필요 시 AuthService 생성자 변경에 맞춘 override)
- Modify: 기타 signup→login을 가정하는 API 테스트 (`test_user_me_api.py` 등)

**Helper 패턴:** `generate_email_code`를 monkeypatch하여 `"123456"` 고정.

```python
@pytest.fixture
def fixed_email_code(monkeypatch):
    monkeypatch.setattr(
        "domains.auth.verification_store.generate_email_code",
        lambda: "123456",
    )
```

- [ ] **Step 1: signup 테스트 수정**

```python
async def test_signup_sends_code_without_tokens(client, fixed_email_code):
    response = await client.post("/api/v1/users/signup", json={...})
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "signup@example.com"
    assert body["message"] == "verification_code_sent"
    assert "access_token" not in body
```

- [ ] **Step 2: verify → login / 미인증 login 거부**

```python
async def test_login_rejects_unverified(client, fixed_email_code):
    await client.post("/api/v1/users/signup", json={...})
    r = await client.post("/api/v1/auth/login", json={...})
    assert r.status_code == 401
    assert r.json()["code"] == ErrorCode.EMAIL_NOT_VERIFIED


async def test_verify_then_login(client, fixed_email_code):
    await client.post("/api/v1/users/signup", json={...})
    v = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": "...", "code": "123456"},
    )
    assert v.status_code == 200
    assert v.json()["access_token"]
```

- [ ] **Step 3: password reset E2E**

signup → verify → reset/request → reset/confirm(code=123456, new pw) → login with new pw

존재하지 않는 이메일 reset/request → 200 + 동일 메시지

- [ ] **Step 4: 기존 테스트 일괄 수정**

signup 직후 토큰을 쓰던 모든 API 테스트에 verify 단계 추가하거나, 테스트용으로 DB에 `is_email_verified=True`를 세팅하는 헬퍼 사용.

검색:

```bash
rg -n "users/signup" tests/
```

- [ ] **Step 5: 전체 관련 테스트 통과**

```bash
uv run pytest tests/api/test_auth_api.py tests/api/test_user_me_api.py tests/unit/test_auth_service.py tests/unit/test_verification_store.py tests/unit/test_email_service.py -v
```

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "$(cat <<'EOF'
Test: 이메일 인증·비밀번호 찾기 API 테스트 추가

EOF
)"
```

---

## Verification (전체)

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv run pytest tests/unit/test_verification_store.py tests/unit/test_email_service.py tests/unit/test_auth_service.py tests/unit/test_user_service.py tests/api/test_auth_api.py tests/api/test_user_me_api.py -v
```

수동 스모크 (선택):
1. `EMAIL_BACKEND=console`로 서버 기동
2. signup → 로그에서 코드 확인 → verify → login
3. password reset request → 로그 코드 → confirm → login

---

## Spec Coverage Checklist

| Spec 요구 | Task |
|-----------|------|
| 6자리 코드 + Redis TTL/쿨다운/5회 | Task 2 |
| SMTP/console | Task 3 |
| signup 토큰 미발급 + 코드 발송 | Task 4, 6 |
| verify 후 토큰 | Task 4, 6 |
| resend | Task 4, 6 |
| 미인증 login 거부 | Task 4, 7 |
| password reset request/confirm | Task 5, 6, 7 |
| 카카오 verified=True | Task 4 |
| 기존 유저 백필 True | Task 1 |
| 계정 존재 숨김 | Task 5, 7 |
| Error codes | Task 1 |
