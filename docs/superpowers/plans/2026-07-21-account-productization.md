# 계정·제품화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/users/me` 조회·수정, 카카오→비밀번호 설정, soft-delete 탈퇴(7일 복구·purge), `GET /a` 제거를 백엔드에 추가한다.

**Architecture:** `User`에 `deleted_at`을 두고 UserService가 프로필·비밀번호·탈퇴·purge를 담당한다. AuthService는 login/kakao에서 유예 내 복구, `get_current_user`/refresh에서는 soft-deleted를 401로 차단한다. Redis 세션 인덱스는 변경하지 않는다.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Argon2 (`core.security`), pytest + httpx + fakeredis + aiosqlite

**Spec:** `docs/superpowers/specs/2026-07-21-account-productization-design.md`

## Global Constraints

- 연동 방향: 카카오 전용 → 비밀번호 설정만 (이메일→카카오·자동 병합 없음)
- 탈퇴: `deleted_at` soft delete, 유예 **7일**, 기간 내 login/kakao로 복구
- `/users/me`: GET + PATCH(nickname) + PATCH password. **이메일 변경 없음**
- Purge: 서비스 메서드 + 스크립트. 인앱 스케줄러 없음
- `GET /a` 제거
- access 블랙리스트 / refresh 유저별 일괄 삭제 인덱스 없음
- 커밋 메시지 스타일: `Feat:` / `Fix:` / `Docs:` / `Test:`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/domains/user/model.py` | `deleted_at` 컬럼 |
| `alembic/versions/c3d4e5f6a7b8_add_users_deleted_at.py` | 마이그레이션 + partial index |
| `src/core/config.py` | `WITHDRAWAL_GRACE_DAYS: int = 7` |
| `src/domains/user/schemas.py` | `UserInfoResponse` 확장, `UpdateMeRequest`, `UpdatePasswordRequest`, `from_user` |
| `src/domains/user/repository.py` | save/flush, delete, list expired withdrawn |
| `src/domains/user/service.py` | me / password / withdraw / purge |
| `src/domains/auth/service.py` | soft-delete 게이트 + 로그인 복구 |
| `src/api/v1/endpoints/user.py` | `/me`, `/me/password`, `DELETE /me` |
| `src/api/deps.py` | (필요 시) `get_current_user`는 AuthService 경유 유지 |
| `src/main.py` | `GET /a` 제거 |
| `scripts/purge_withdrawn_users.py` | purge 실행 엔트리 |
| `tests/unit/test_user_service.py` | 프로필·비밀번호·탈퇴·purge |
| `tests/unit/test_auth_service.py` | 게이트·복구 |
| `tests/api/test_user_me_api.py` | `/users/me` API |
| `tests/api/test_auth_api.py` | 복구·차단 시나리오 보강 |

---

### Task 1: `deleted_at` 모델 + 마이그레이션 + grace 설정

**Files:**
- Modify: `src/domains/user/model.py`
- Modify: `src/core/config.py`
- Create: `alembic/versions/c3d4e5f6a7b8_add_users_deleted_at.py`

**Interfaces:**
- Produces: `User.deleted_at: datetime | None`, `Settings.WITHDRAWAL_GRACE_DAYS == 7`
- Migration `down_revision = "b2c3d4e5f6a7"`

- [ ] **Step 1: 모델에 `deleted_at` 추가**

`src/domains/user/model.py` — `created_at` 아래에:

```python
deleted_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True, default=None
)
```

`__table_args__`에 일반 인덱스 추가 (partial은 Alembic에서만 — SQLite 테스트 `create_all` 호환):

```python
Index("ix_users_deleted_at", deleted_at),
```

- [ ] **Step 2: 설정 상수**

`src/core/config.py` `Settings`에:

```python
WITHDRAWAL_GRACE_DAYS: int = 7
```

- [ ] **Step 3: Alembic revision**

```python
"""add_users_deleted_at

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-21 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_users_deleted_at",
        "users",
        ["deleted_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_column("users", "deleted_at")
```

- [ ] **Step 4: Commit**

```bash
git add src/domains/user/model.py src/core/config.py alembic/versions/c3d4e5f6a7b8_add_users_deleted_at.py
git commit -m "$(cat <<'EOF'
Feat: users.deleted_at 및 탈퇴 유예일 설정 추가

EOF
)"
```

---

### Task 2: 스키마 확장 + `UserInfoResponse.from_user`

**Files:**
- Modify: `src/domains/user/schemas.py`
- Modify: `src/domains/user/service.py` (`get_user_info` → `from_user`)
- Modify: `src/domains/auth/service.py` (`_to_auth_response`, `_to_kakao_auth_response`)
- Modify: `src/api/v1/endpoints/user.py` (signup 응답)

**Interfaces:**
- Produces:
  - `UserInfoResponse.from_user(user: User) -> UserInfoResponse`
  - fields: `id`, `email`, `nickname`, `has_password: bool`, `has_kakao: bool`, `deleted_at: datetime | None`
  - `UpdateMeRequest(nickname: str | None = None)` — nickname만, 2~20
  - `UpdatePasswordRequest(new_password, checked_password, current_password: str | None = None)`

- [ ] **Step 1: 스키마 작성**

`src/domains/user/schemas.py` — `UserInfoResponse`를 교체하고 요청 스키마 추가:

```python
from datetime import datetime
from typing import Self

from domains.user.model import User  # 순환 import 시 TYPE_CHECKING + 런타임 import in from_user


class UserInfoResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    nickname: str
    has_password: bool
    has_kakao: bool
    deleted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(
            id=user.id,
            email=user.email,
            nickname=user.nickname,
            has_password=user.password is not None,
            has_kakao=user.kakao_id is not None,
            deleted_at=user.deleted_at,
        )


class UpdateMeRequest(BaseModel):
    nickname: str | None = Field(
        default=None, min_length=2, max_length=20, description="닉네임 (2~20자)"
    )


class UpdatePasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=20)
    checked_password: str = Field(..., min_length=8, max_length=20)
    current_password: str | None = Field(default=None, min_length=8, max_length=20)

    @model_validator(mode="after")
    def verify_password_match(self):
        if self.new_password != self.checked_password:
            raise ValueError("비밀번호 확인이 일치하지 않습니다.")
        return self
```

순환 import가 나면 `from_user` 안에서 `from domains.user.model import User`를 쓰거나 schemas에 model import를 피하고 service에서 매핑한다. **권장:** schemas에 `from_user`를 두고 model을 import (현재 `schemas`↔`model` 단방향이면 OK).

- [ ] **Step 2: 모든 `UserInfoResponse.model_validate(user)` → `from_user(user)`**

대상:
- `src/domains/user/service.py`
- `src/domains/auth/service.py` (2곳)
- `src/api/v1/endpoints/user.py`

- [ ] **Step 3: 기존 테스트가 깨지지 않는지 확인**

Run: `uv run pytest tests/api/test_auth_api.py tests/unit/test_user_service.py tests/unit/test_auth_service.py -v`

Expected: PASS (응답에 `has_password`/`has_kakao`가 추가되어도 기존 assert가 필드를 전부 요구하지 않으면 통과). 실패하면 assert에 새 필드를 맞춘다.

- [ ] **Step 4: Commit**

```bash
git add src/domains/user/schemas.py src/domains/user/service.py src/domains/auth/service.py src/api/v1/endpoints/user.py
git commit -m "$(cat <<'EOF'
Feat: UserInfoResponse 연동 상태 필드 및 me/password 스키마 추가

EOF
)"
```

---

### Task 3: UserRepository 저장·삭제·purge 조회

**Files:**
- Modify: `src/domains/user/repository.py`
- Test: (Task 4 unit에서 간접 검증; 별도 repo 테스트 불필요)

**Interfaces:**
- Produces:
  - `async def save(self, user: User) -> User` — `flush` 후 return
  - `async def delete_user(self, user: User) -> None` — `session.delete` + `flush`
  - `async def list_withdrawn_before(self, cutoff: datetime) -> list[User]` — `deleted_at.is_not(None) & deleted_at < cutoff`

- [ ] **Step 1: repository 메서드 추가**

```python
from datetime import datetime
from sqlalchemy import select, func, delete  # delete unused if using session.delete

async def save(self, user: User) -> User:
    try:
        self.session.add(user)
        await self.session.flush()
        return user
    except SQLAlchemyError as e:
        raise DatabaseException(detail="사용자 저장 중 DB 오류가 발생했습니다.") from e

async def delete_user(self, user: User) -> None:
    try:
        await self.session.delete(user)
        await self.session.flush()
    except SQLAlchemyError as e:
        raise DatabaseException(detail="사용자 삭제 중 DB 오류가 발생했습니다.") from e

async def list_withdrawn_before(self, cutoff: datetime) -> list[User]:
    try:
        stmt = select(User).where(
            User.deleted_at.is_not(None),
            User.deleted_at < cutoff,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    except SQLAlchemyError as e:
        raise DatabaseException(detail="탈퇴 사용자 조회 중 DB 오류가 발생했습니다.") from e
```

SQLAlchemy 2: `await self.session.delete(user)`가 버전에서 미지원이면 `await self.session.delete(user)` 대신 `await self.session.delete(user)` — 프로젝트 SA 버전에 맞게 `self.session.delete(user)` + `flush` 사용.

- [ ] **Step 2: Commit**

```bash
git add src/domains/user/repository.py
git commit -m "$(cat <<'EOF'
Feat: UserRepository에 save/delete/탈퇴 만료 조회 추가

EOF
)"
```

---

### Task 4: UserService — me / password / withdraw / purge (TDD)

**Files:**
- Modify: `src/domains/user/service.py`
- Modify: `tests/unit/test_user_service.py`

**Interfaces:**
- Consumes: `UserRepository.save/delete_user/list_withdrawn_before`, `settings.WITHDRAWAL_GRACE_DAYS`, `security.hash_password` / `verify_password`
- Produces:
  - `async def get_user_info(self, user_id: UUID) -> UserInfoResponse`
  - `async def update_me(self, user: User, request: UpdateMeRequest) -> UserInfoResponse`
  - `async def update_password(self, user: User, request: UpdatePasswordRequest) -> UserInfoResponse`
  - `async def withdraw(self, user: User) -> None`
  - `async def purge_expired_withdrawn_users(self, now: datetime | None = None) -> int`

- [ ] **Step 1: 실패하는 단위 테스트 추가**

`tests/unit/test_user_service.py`에 추가:

```python
from datetime import datetime, timedelta, timezone
from core import security
from core.exception.exceptions import BadRequestException, UnAuthorizedException
from domains.user.schemas import UpdateMeRequest, UpdatePasswordRequest
from core.config import settings


async def test_get_user_info_includes_link_flags(user_service, user_repo):
    user = User(
        id=uuid6.uuid7(),
        email="k@example.com",
        password=None,
        kakao_id="123",
        nickname="kakao",
    )
    user_repo.get_user_by_id.return_value = user
    info = await user_service.get_user_info(user.id)
    assert info.has_password is False
    assert info.has_kakao is True


async def test_update_me_changes_nickname(user_service, user_repo):
    user = User(email="a@example.com", password="h", nickname="old")
    user_repo.get_user_by_nickname.return_value = None
    user_repo.save.side_effect = lambda u: u
    info = await user_service.update_me(user, UpdateMeRequest(nickname="newname"))
    assert info.nickname == "newname"
    user_repo.save.assert_awaited_once()


async def test_update_password_sets_for_kakao_user(user_service, user_repo):
    user = User(email="k@example.com", password=None, kakao_id="1", nickname="k")
    user_repo.save.side_effect = lambda u: u
    req = UpdatePasswordRequest(
        new_password="password123",
        checked_password="password123",
        current_password=None,
    )
    info = await user_service.update_password(user, req)
    assert info.has_password is True
    assert user.password is not None
    assert security.verify_password("password123", user.password)


async def test_update_password_requires_current_when_has_password(user_service, user_repo):
    user = User(
        email="a@example.com",
        password=security.hash_password("password123"),
        nickname="a",
    )
    req = UpdatePasswordRequest(
        new_password="newpass123",
        checked_password="newpass123",
        current_password=None,
    )
    with pytest.raises(BadRequestException):
        await user_service.update_password(user, req)


async def test_update_password_rejects_wrong_current(user_service, user_repo):
    user = User(
        email="a@example.com",
        password=security.hash_password("password123"),
        nickname="a",
    )
    req = UpdatePasswordRequest(
        new_password="newpass123",
        checked_password="newpass123",
        current_password="wrongpass1",
    )
    with pytest.raises(UnAuthorizedException):
        await user_service.update_password(user, req)


async def test_withdraw_sets_deleted_at(user_service, user_repo):
    user = User(email="a@example.com", password="h", nickname="a")
    user_repo.save.side_effect = lambda u: u
    await user_service.withdraw(user)
    assert user.deleted_at is not None
    user_repo.save.assert_awaited_once()


async def test_purge_deletes_expired_only(user_service, user_repo):
    old = User(email="old@example.com", password="h", nickname="old")
    old.deleted_at = datetime.now(timezone.utc) - timedelta(days=8)
    user_repo.list_withdrawn_before.return_value = [old]
    user_repo.delete_user = AsyncMock()
    deleted = await user_service.purge_expired_withdrawn_users()
    assert deleted == 1
    user_repo.delete_user.assert_awaited_once_with(old)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/unit/test_user_service.py -v`

Expected: FAIL (`update_me` / `update_password` 등 AttributeError)

- [ ] **Step 3: UserService 구현**

```python
from datetime import datetime, timezone

from core.config import settings
from core.exception.exceptions import UnAuthorizedException
from domains.user.schemas import UpdateMeRequest, UpdatePasswordRequest


def _to_info(self, user: User) -> UserInfoResponse:
    return UserInfoResponse.from_user(user)

async def get_user_info(self, user_id: UUID) -> UserInfoResponse:
    user = await self.user_repo.get_user_by_id(user_id)
    if not user:
        raise UserNotFoundException()
    return UserInfoResponse.from_user(user)

async def update_me(self, user: User, request: UpdateMeRequest) -> UserInfoResponse:
    if request.nickname is not None:
        existing = await self.user_repo.get_user_by_nickname(request.nickname)
        if existing and existing.id != user.id:
            raise ConflictException(
                code=ErrorCode.NICKNAME_CONFLICT,
                detail="이미 사용 중인 닉네임 입니다.(대소문자 구별)",
            )
        user.nickname = request.nickname
    await self.user_repo.save(user)
    return UserInfoResponse.from_user(user)

async def update_password(
    self, user: User, request: UpdatePasswordRequest
) -> UserInfoResponse:
    if user.password is None:
        # 카카오 전용: current_password 무시하고 설정
        user.password = security.hash_password(request.new_password)
    else:
        if not request.current_password:
            raise BadRequestException(
                code=ErrorCode.BAD_REQUEST,  # 프로젝트에 맞는 code 사용
                detail="현재 비밀번호가 필요합니다.",
            )
        if not security.verify_password(request.current_password, user.password):
            raise UnAuthorizedException(detail="현재 비밀번호가 올바르지 않습니다.")
        user.password = security.hash_password(request.new_password)
    await self.user_repo.save(user)
    return UserInfoResponse.from_user(user)

async def withdraw(self, user: User) -> None:
    user.deleted_at = datetime.now(timezone.utc)
    await self.user_repo.save(user)

async def purge_expired_withdrawn_users(
    self, now: datetime | None = None
) -> int:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.WITHDRAWAL_GRACE_DAYS)
    users = await self.user_repo.list_withdrawn_before(cutoff)
    for u in users:
        await self.user_repo.delete_user(u)
    return len(users)
```

`ErrorCode.BAD_REQUEST`가 없으면 기존 `BadRequestException` 생성 패턴(`codes.py`)을 따른다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/unit/test_user_service.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domains/user/service.py tests/unit/test_user_service.py
git commit -m "$(cat <<'EOF'
Feat: UserService에 me/비밀번호/탈퇴/purge 추가

EOF
)"
```

---

### Task 5: AuthService soft-delete 게이트 + 복구 (TDD)

**Files:**
- Modify: `src/domains/auth/service.py`
- Modify: `tests/unit/test_auth_service.py`

**Interfaces:**
- Consumes: `User.deleted_at`, `settings.WITHDRAWAL_GRACE_DAYS`, `UserRepository.save`
- Produces:
  - `async def _restore_if_within_grace(self, user: User) -> User` — 유예 내면 `deleted_at=None` 후 save, 만료면 `UnAuthorizedException`
  - `login` / `login_with_kakao`(기존 유저): 인증 성공 후 restore 시도
  - `get_user_by_token` / `refresh`: `deleted_at is not None`이면 즉시 401 (복구 없음)
  - `complete_kakao_signup`: 복구 로직 추가하지 않음

- [ ] **Step 1: 실패하는 단위 테스트**

```python
from datetime import datetime, timedelta, timezone


async def test_login_restores_soft_deleted_within_grace(auth_service, user_repo):
    user = User(
        email="a@example.com",
        password=security.hash_password("password123"),
        nickname="a",
    )
    user.deleted_at = datetime.now(timezone.utc) - timedelta(days=3)
    user_repo.get_user_by_email.return_value = user
    user_repo.save.side_effect = lambda u: u
    # refresh_store.save mock already in fixture
    result = await auth_service.login(
        LogInRequest(email="a@example.com", password="password123")
    )
    assert user.deleted_at is None
    assert result.access_token


async def test_login_rejects_soft_deleted_after_grace(auth_service, user_repo):
    user = User(
        email="a@example.com",
        password=security.hash_password("password123"),
        nickname="a",
    )
    user.deleted_at = datetime.now(timezone.utc) - timedelta(days=8)
    user_repo.get_user_by_email.return_value = user
    with pytest.raises(UnAuthorizedException):
        await auth_service.login(
            LogInRequest(email="a@example.com", password="password123")
        )


async def test_get_user_by_token_rejects_soft_deleted(auth_service, user_repo, monkeypatch):
    user = User(email="a@example.com", password="h", nickname="a")
    user.id = uuid6.uuid7()
    user.deleted_at = datetime.now(timezone.utc)
    user_repo.get_user_by_id.return_value = user
    token = security.create_jwt(user.id)
    with pytest.raises(UnAuthorizedException):
        await auth_service.get_user_by_token(token)


async def test_kakao_login_restores_within_grace(auth_service, user_repo, monkeypatch):
    user = User(email="k@example.com", password=None, kakao_id="99", nickname="k")
    user.deleted_at = datetime.now(timezone.utc) - timedelta(days=1)
    user_repo.get_user_by_kakao_id.return_value = user
    user_repo.save.side_effect = lambda u: u
    monkeypatch.setattr(
        "domains.auth.service.kakao_client.fetch_kakao_user_id",
        AsyncMock(return_value="99"),
    )
    result = await auth_service.login_with_kakao("kakao-token")
    assert user.deleted_at is None
    assert getattr(result, "access_token", None)
```

기존 `test_auth_service.py` fixture·import 스타일에 맞출 것.

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/unit/test_auth_service.py -k "soft_deleted or restores" -v`

Expected: FAIL

- [ ] **Step 3: AuthService 구현**

```python
from datetime import datetime, timedelta, timezone
from core.config import settings


def _is_within_grace(self, deleted_at: datetime, now: datetime) -> bool:
    if deleted_at.tzinfo is None:
        deleted_at = deleted_at.replace(tzinfo=timezone.utc)
    return now - deleted_at <= timedelta(days=settings.WITHDRAWAL_GRACE_DAYS)


async def _reject_if_withdrawn(self, user: User) -> None:
    if user.deleted_at is not None:
        raise UnAuthorizedException(detail="사용자를 찾을 수 없습니다.")


async def _restore_if_within_grace(self, user: User) -> User:
    if user.deleted_at is None:
        return user
    now = datetime.now(timezone.utc)
    if self._is_within_grace(user.deleted_at, now):
        user.deleted_at = None
        await self.user_repo.save(user)
        return user
    raise UnAuthorizedException(
        detail="이메일 또는 비밀번호가 올바르지 않습니다."
    )
```

적용 위치:
- `login`: 비밀번호 검증 **성공 후** `_restore_if_within_grace(user)` 호출 뒤 `issue_tokens`
- `login_with_kakao`: 기존 유저 분기에서 restore 후 토큰
- `get_user_by_token`: 유저 로드 후 `_reject_if_withdrawn`
- `refresh`: 유저 로드 후 `_reject_if_withdrawn` (복구 없음). 메시지는 기존 InvalidToken 톤 유지 가능:

```python
if user.deleted_at is not None:
    raise InvalidTokenException(detail="유효하지 않은 리프레시 토큰입니다.")
```

카카오 복구 실패 메시지도 열거 완화를 위해 일반 실패 톤:

```python
raise UnAuthorizedException(detail="카카오 로그인에 실패했습니다.")
```

또는 login과 동일하게 모호한 메시지. **스펙:** 일반 실패와 동일 톤 → login은 `"이메일 또는 비밀번호가 올바르지 않습니다."`, kakao는 기존 kakao 에러 메시지 패턴을 유지하되 “탈퇴됨”을 넣지 않는다.

- [ ] **Step 4: 테스트 통과**

Run: `uv run pytest tests/unit/test_auth_service.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domains/auth/service.py tests/unit/test_auth_service.py
git commit -m "$(cat <<'EOF'
Feat: 탈퇴 유저 차단 및 유예 기간 로그인 복구

EOF
)"
```

---

### Task 6: HTTP 엔드포인트 + `GET /a` 제거 + API 테스트

**Files:**
- Modify: `src/api/v1/endpoints/user.py`
- Modify: `src/main.py`
- Create: `tests/api/test_user_me_api.py`
- Modify: `tests/api/test_auth_api.py` (복구·차단 1~2케이스)
- Modify: `tests/conftest.py` (필요 시 `kakao_user` fixture)

**Interfaces:**
- Produces routes:
  - `GET /api/v1/users/me` → `UserInfoResponse`
  - `PATCH /api/v1/users/me` → `UserInfoResponse`
  - `PATCH /api/v1/users/me/password` → `UserInfoResponse`
  - `DELETE /api/v1/users/me` → `204`
- Removes: `GET /a`

- [ ] **Step 1: API 실패 테스트 작성**

`tests/api/test_user_me_api.py`:

```python
async def test_get_me(client, auth_headers, test_user):
    r = await client.get("/api/v1/users/me", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == test_user.email
    assert body["has_password"] is True
    assert body["has_kakao"] is False


async def test_patch_me_nickname(client, auth_headers):
    r = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers,
        json={"nickname": "newnick"},
    )
    assert r.status_code == 200
    assert r.json()["nickname"] == "newnick"


async def test_patch_me_rejects_email_field(client, auth_headers):
    r = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers,
        json={"email": "other@example.com", "nickname": "newnick2"},
    )
    # UpdateMeRequest에 email 없음 → extra ignore 시 200이어도 이메일은 불변
    assert r.status_code in (200, 422)
    me = await client.get("/api/v1/users/me", headers=auth_headers)
    assert me.status_code == 200
    assert me.json()["email"] == "test@example.com"


async def test_set_password_for_kakao_user_then_email_login(client, db_session):
    from domains.user.model import User
    from core import security
    user = User(email="kakao@example.com", password=None, kakao_id="k1", nickname="kakao1")
    db_session.add(user)
    await db_session.flush()
    headers = {"Authorization": f"Bearer {security.create_jwt(user.id)}"}
    r = await client.patch(
        "/api/v1/users/me/password",
        headers=headers,
        json={
            "new_password": "password123",
            "checked_password": "password123",
        },
    )
    assert r.status_code == 200
    assert r.json()["has_password"] is True
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "kakao@example.com", "password": "password123"},
    )
    assert login.status_code == 200


async def test_withdraw_blocks_me(client, auth_headers):
    r = await client.delete("/api/v1/users/me", headers=auth_headers)
    assert r.status_code == 204
    me = await client.get("/api/v1/users/me", headers=auth_headers)
    assert me.status_code == 401


async def test_login_restores_within_grace(client, auth_headers, test_user, db_session):
    await client.delete("/api/v1/users/me", headers=auth_headers)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    assert login.json()["info"]["deleted_at"] is None


async def test_get_a_removed(client):
    r = await client.get("/a")
    assert r.status_code == 404
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/api/test_user_me_api.py -v`

Expected: FAIL (404 on `/users/me`)

- [ ] **Step 3: 엔드포인트 구현**

`src/api/v1/endpoints/user.py`:

```python
from api.deps import get_user_service, get_auth_service, get_current_user
from domains.user.schemas import (
    SignUpResponse,
    SignUpRequest,
    UserInfoResponse,
    UpdateMeRequest,
    UpdatePasswordRequest,
)
from domains.user.model import User

@router.get("/me", response_model=UserInfoResponse)
async def get_me(user: User = Depends(get_current_user)) -> UserInfoResponse:
    return UserInfoResponse.from_user(user)

@router.patch("/me", response_model=UserInfoResponse)
async def update_me(
    request: UpdateMeRequest,
    user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserInfoResponse:
    return await user_service.update_me(user, request)

@router.patch("/me/password", response_model=UserInfoResponse)
async def update_password(
    request: UpdatePasswordRequest,
    user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserInfoResponse:
    return await user_service.update_password(user, request)

@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw(
    user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> None:
    await user_service.withdraw(user)
```

`src/main.py`에서 `GET /a` 핸들러 전체 삭제.

- [ ] **Step 4: API 테스트 통과**

Run: `uv run pytest tests/api/test_user_me_api.py tests/api/test_auth_api.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/v1/endpoints/user.py src/main.py tests/api/test_user_me_api.py tests/api/test_auth_api.py tests/conftest.py
git commit -m "$(cat <<'EOF'
Feat: /users/me API 추가 및 디버그 /a 엔드포인트 제거

EOF
)"
```

---

### Task 7: Purge 스크립트

**Files:**
- Create: `scripts/purge_withdrawn_users.py`

**Interfaces:**
- Consumes: `UserService.purge_expired_withdrawn_users`
- Produces: CLI exit 0, stdout에 삭제 건수

- [ ] **Step 1: 스크립트 작성**

```python
"""유예 기간이 지난 soft-deleted 사용자를 물리 삭제한다.

Usage (repo root, PYTHONPATH=src):
  uv run python scripts/purge_withdrawn_users.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.database import async_session_factory
from domains.user.repository import UserRepository
from domains.user.service import UserService


async def main() -> None:
    async with async_session_factory() as session:
        service = UserService(UserRepository(session))
        count = await service.purge_expired_withdrawn_users()
        await session.commit()
        print(f"purged {count} user(s)")


if __name__ == "__main__":
    asyncio.run(main())
```

`core.database.async_session_factory`를 그대로 사용한다. **새 DB 추상화를 만들지 말 것.**

- [ ] **Step 2: import 스모크 (DB 없이도 모듈 로드 가능하면)**

Run: `cd /Users/jeong-yeonghun/Desktop/saksak/back && PYTHONPATH=src uv run python -c "import ast; ast.parse(open('scripts/purge_withdrawn_users.py').read())"`

Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add scripts/purge_withdrawn_users.py
git commit -m "$(cat <<'EOF'
Feat: 탈퇴 유예 만료 사용자 purge 스크립트 추가

EOF
)"
```

---

## Verification (전체)

```bash
uv run pytest tests/unit/test_user_service.py tests/unit/test_auth_service.py tests/api/test_user_me_api.py tests/api/test_auth_api.py -v
```

Expected: 전부 PASS

수동 체크리스트:
- [ ] `GET /users/me`에 `has_password` / `has_kakao` 포함
- [ ] 카카오 유저 비밀번호 설정 후 이메일 로그인
- [ ] 탈퇴 후 보호 API 401, 7일 내 로그인 복구
- [ ] `GET /a` → 404
- [ ] purge 스크립트가 `purge_expired_withdrawn_users` 호출

---

## Spec Coverage (self-review)

| Spec 항목 | Task |
|-----------|------|
| `deleted_at` + index | Task 1 |
| `UserInfoResponse` 확장 | Task 2 |
| `UpdateMe` / `UpdatePassword` | Task 2, 4, 6 |
| GET/PATCH/DELETE `/users/me`, PATCH password | Task 6 |
| 카카오→비밀번호 설정 | Task 4, 6 |
| soft-delete + 7일 복구 | Task 5, 6 |
| purge 서비스 + 스크립트 | Task 4, 7 |
| `GET /a` 제거 | Task 6 |
| Auth 게이트 (me/refresh) | Task 5 |
| 이메일 변경 없음 | Task 2 (`UpdateMeRequest`에 email 없음), Task 6 테스트 |

Placeholder/모순 없음. `from_user` 도입으로 signup/login 응답도 동일 필드를 반환한다.
