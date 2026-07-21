# In-App Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 인앱 알림함 API로 받은 그룹 초대와 유통기한 임박/만료를 조회·읽음 처리할 수 있게 한다.

**Architecture:** `notifications` 테이블 + `domains/notification/`. 닉네임 초대 생성 시 수신자 알림 1건 insert. 알림 목록/미읽음 조회 시 개인·그룹 재료를 스캔해 `soon`/`expired`면 `reference_key` 기준으로 없으면 insert. 푸시·스케줄러 없음.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, pytest + httpx, uuid6

**Spec:** `docs/superpowers/specs/2026-07-21-in-app-notifications-design.md`

## Global Constraints

- 채널: 인앱만 (폴링). 푸시·스케줄러·삭제 API·알림 설정 없음
- 초대: 닉네임 `GroupInvite`만. 초대 코드 공유 알림 제외
- 유통기한: `compute_status` / `SOON_WITHIN_DAYS = 3` 재사용
- 중복: `(user_id, reference_key)` UNIQUE — 재료당 상태당 1회
- 그룹 재료: sync를 호출한 유저 본인에게만 생성 (멤버는 각자 조회 시 sync)
- 초대 수락/거절은 기존 group invite API 유지
- 목록 페이지네이션 없음 (전량 최신순)
- 에러: 없는/타인 알림 → `NOTIFICATION_NOT_FOUND` 404

## File Structure

| File | Responsibility |
|------|----------------|
| `src/core/exception/codes.py` | `NOTIFICATION_NOT_FOUND` |
| `src/core/exception/exceptions.py` | `NotificationNotFoundException` |
| `src/domains/notification/model.py` | `Notification` ORM |
| `src/domains/notification/schemas.py` | 응답 DTO |
| `src/domains/notification/repository.py` | CRUD / upsert-skip / mark read |
| `src/domains/notification/service.py` | invite 생성, expiry sync, list, unread, read |
| `src/api/v1/endpoints/notification.py` | HTTP 라우트 |
| `src/api/deps.py` | `get_notification_service` |
| `src/api/api.py` | 라우터 등록 |
| `src/domains/group/service.py` | 초대 생성 시 알림 insert |
| `src/api/deps.py` `get_group_service` | `NotificationRepository` 주입 |
| `src/domains/user/model.py` | `notifications` relationship |
| `alembic/versions/h8i9j0k1l2m3_add_notifications.py` | 테이블 마이그레이션 |
| `tests/conftest.py` | Notification 모델 import (metadata) |
| `tests/unit/test_notification_service.py` | 서비스 단위 테스트 |
| `tests/api/test_notification_api.py` | API 스모크 |
| `tests/unit/test_group_service.py` | `_service`에 notification_repo 추가 + 초대 알림 검증 |

---

### Task 1: Error code + NotificationNotFoundException

**Files:**
- Modify: `src/core/exception/codes.py`
- Modify: `src/core/exception/exceptions.py`
- Test: `tests/unit/test_notification_exception.py` (신규)

**Interfaces:**
- Produces: `ErrorCode.NOTIFICATION_NOT_FOUND = "NOTIFICATION_NOT_FOUND"`
- Produces: `class NotificationNotFoundException(NotFoundException)` default detail `"알림을 찾을 수 없습니다."`
- Consumes: existing `NotFoundException`, `ErrorCode`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_notification_exception.py`:

```python
from core.exception.codes import ErrorCode
from core.exception.exceptions import NotificationNotFoundException


def test_notification_not_found_defaults():
    exc = NotificationNotFoundException()
    assert exc.status_code == 404
    assert exc.code == ErrorCode.NOTIFICATION_NOT_FOUND
    assert "알림" in exc.detail
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/unit/test_notification_exception.py -v`

Expected: FAIL (`NotificationNotFoundException` / `NOTIFICATION_NOT_FOUND` import or AttributeError)

- [ ] **Step 3: Implement**

In `src/core/exception/codes.py`, after `SHOPPING_ITEM_NOT_FOUND`:

```python
    # ----------------------------------------
    # 6. 알림 관련
    # ----------------------------------------
    NOTIFICATION_NOT_FOUND = "NOTIFICATION_NOT_FOUND"
```

In `src/core/exception/exceptions.py`, after `ShoppingItemNotFoundException`:

```python
# ----------------------------------------
# 6. 알림 관련
# ----------------------------------------
class NotificationNotFoundException(NotFoundException):
    def __init__(self, detail: str = "알림을 찾을 수 없습니다."):
        super().__init__(code=ErrorCode.NOTIFICATION_NOT_FOUND, detail=detail)
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/unit/test_notification_exception.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/exception/codes.py src/core/exception/exceptions.py tests/unit/test_notification_exception.py
git commit -m "$(cat <<'EOF'
Feat: 알림 NOTIFICATION_NOT_FOUND 예외 추가

EOF
)"
```

---

### Task 2: Notification model + Alembic + conftest

**Files:**
- Create: `src/domains/notification/model.py`
- Create: `src/domains/notification/__init__.py` (빈 파일 또는 생략 가능 — 패키지로 인식되면 빈 `__init__.py`)
- Create: `alembic/versions/h8i9j0k1l2m3_add_notifications.py`
- Modify: `src/domains/user/model.py` — `notifications` relationship
- Modify: `tests/conftest.py` — import `Notification`

**Interfaces:**
- Produces: `class Notification(Base)` table `notifications` with fields per spec
- Produces: migration `revision="h8i9j0k1l2m3"`, `down_revision="g7h8i9j0k1l2"`
- Consumes: `Base`, `uuid6`, JSON/JSONB pattern from `SavedRecipe`

- [ ] **Step 1: Write model**

Create `src/domains/notification/__init__.py` (empty).

Create `src/domains/notification/model.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import uuid6
from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from core.database import Base

if TYPE_CHECKING:
    from domains.user.model import User


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    user_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(String(256), nullable=False)
    reference_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="notifications")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "reference_key",
            name="uq_notifications_user_reference_key",
        ),
    )
```

In `src/domains/user/model.py`, add TYPE_CHECKING import if needed and:

```python
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
```

(Follow existing `shopping_items` / `saved_recipes` style in the same file.)

- [ ] **Step 2: Write migration**

Create `alembic/versions/h8i9j0k1l2m3_add_notifications.py`:

```python
"""add_notifications

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-07-21 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, Sequence[str], None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=64), nullable=False),
        sa.Column("body", sa.String(length=256), nullable=False),
        sa.Column("reference_key", sa.String(length=128), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "is_read",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "reference_key",
            name="uq_notifications_user_reference_key",
        ),
    )
    op.create_index(
        op.f("ix_notifications_user_id"),
        "notifications",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_table("notifications")
```

- [ ] **Step 3: Update conftest**

In `tests/conftest.py`, add with other model imports:

```python
from domains.notification.model import Notification  # noqa: F401, E402
```

- [ ] **Step 4: Smoke — metadata create**

Run: `pytest tests/unit/test_notification_exception.py -v`

Expected: PASS (conftest imports Notification without error)

- [ ] **Step 5: Commit**

```bash
git add src/domains/notification/ src/domains/user/model.py alembic/versions/h8i9j0k1l2m3_add_notifications.py tests/conftest.py
git commit -m "$(cat <<'EOF'
Feat: notifications 테이블 모델 및 마이그레이션 추가

EOF
)"
```

---

### Task 3: Notification repository

**Files:**
- Create: `src/domains/notification/repository.py`
- Test: `tests/unit/test_notification_repository.py` (신규)

**Interfaces:**
- Produces:
  - `NotificationRepository(session)`
  - `async def create_if_absent(self, notification: Notification) -> Notification | None`
  - `async def list_by_user(self, user_id: UUID) -> list[Notification]` (newest first)
  - `async def count_unread(self, user_id: UUID) -> int`
  - `async def get_by_id_for_user(self, notification_id: UUID, user_id: UUID) -> Notification | None`
  - `async def mark_read(self, notification: Notification) -> Notification`
  - `async def mark_all_read(self, user_id: UUID) -> int`
- Consumes: `Notification` model; dialect-aware `on_conflict_do_nothing` like shopping

- [ ] **Step 1: Write failing repository test**

Create `tests/unit/test_notification_repository.py`:

```python
from uuid import uuid4

import pytest

from domains.notification.model import Notification
from domains.notification.repository import NotificationRepository


@pytest.mark.asyncio
async def test_create_if_absent_is_idempotent(db_session, test_user):
    repo = NotificationRepository(db_session)
    key = f"expiry_soon:1"
    first = await repo.create_if_absent(
        Notification(
            user_id=test_user.id,
            type="expiry_soon",
            title="유통기한 임박",
            body="양파 유통기한이 2026-07-24까지입니다",
            reference_key=key,
            payload={"ingredient_id": 1},
        )
    )
    second = await repo.create_if_absent(
        Notification(
            user_id=test_user.id,
            type="expiry_soon",
            title="유통기한 임박",
            body="양파 유통기한이 2026-07-24까지입니다",
            reference_key=key,
            payload={"ingredient_id": 1},
        )
    )
    assert first is not None
    assert second is None
    listed = await repo.list_by_user(test_user.id)
    assert len(listed) == 1


@pytest.mark.asyncio
async def test_mark_read_and_unread_count(db_session, test_user):
    repo = NotificationRepository(db_session)
    n = await repo.create_if_absent(
        Notification(
            user_id=test_user.id,
            type="group_invite",
            title="그룹 초대",
            body="누군가 초대",
            reference_key=f"group_invite:{uuid4()}",
            payload={},
        )
    )
    assert n is not None
    assert await repo.count_unread(test_user.id) == 1
    await repo.mark_read(n)
    assert await repo.count_unread(test_user.id) == 0
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/unit/test_notification_repository.py -v`

Expected: FAIL (import / missing repository)

- [ ] **Step 3: Implement repository**

Create `src/domains/notification/repository.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from core.exception.exceptions import DatabaseException
from domains.notification.model import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_if_absent(
        self, notification: Notification
    ) -> Notification | None:
        try:
            dialect_name = self.session.get_bind().dialect.name
            insert = sqlite_insert if dialect_name == "sqlite" else postgresql_insert
            stmt = (
                insert(Notification)
                .values(
                    id=notification.id or None,
                    user_id=notification.user_id,
                    type=notification.type,
                    title=notification.title,
                    body=notification.body,
                    reference_key=notification.reference_key,
                    payload=notification.payload,
                    is_read=notification.is_read,
                )
                .on_conflict_do_nothing(
                    index_elements=["user_id", "reference_key"],
                )
                .returning(Notification)
            )
            # uuid default: if id is None, set uuid7 before insert for dialects needing it
            result = await self.session.execute(stmt)
            row = result.scalar_one_or_none()
            return row
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="알림 저장 중 DB 오류가 발생했습니다."
            ) from e

    async def list_by_user(self, user_id: uuid.UUID) -> list[Notification]:
        try:
            stmt = (
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc())
            )
            result = await self.session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="알림 목록 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def count_unread(self, user_id: uuid.UUID) -> int:
        try:
            stmt = select(func.count()).select_from(Notification).where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            result = await self.session.execute(stmt)
            return int(result.scalar_one())
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="미읽음 알림 수 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def get_by_id_for_user(
        self, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> Notification | None:
        try:
            stmt = select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="알림 조회 중 DB 오류가 발생했습니다."
            ) from e

    async def mark_read(self, notification: Notification) -> Notification:
        try:
            notification.is_read = True
            await self.session.flush()
            return notification
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="알림 읽음 처리 중 DB 오류가 발생했습니다."
            ) from e

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        try:
            stmt = (
                update(Notification)
                .where(
                    Notification.user_id == user_id,
                    Notification.is_read.is_(False),
                )
                .values(is_read=True)
            )
            result = await self.session.execute(stmt)
            await self.session.flush()
            return int(result.rowcount or 0)
        except SQLAlchemyError as e:
            raise DatabaseException(
                detail="알림 전체 읽음 처리 중 DB 오류가 발생했습니다."
            ) from e
```

**Note on `id`:** Before `create_if_absent`, callers should set `id=uuid6.uuid7()` on the `Notification` instance (SQLite insert may not apply Python `default`). Prefer:

```python
notification.id = notification.id or uuid6.uuid7()
```

at the start of `create_if_absent`, and pass `id=notification.id` in `.values(...)`.

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/unit/test_notification_repository.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domains/notification/repository.py tests/unit/test_notification_repository.py
git commit -m "$(cat <<'EOF'
Feat: NotificationRepository 추가

EOF
)"
```

---

### Task 4: Notification schemas + service

**Files:**
- Create: `src/domains/notification/schemas.py`
- Create: `src/domains/notification/service.py`
- Test: `tests/unit/test_notification_service.py` (신규)

**Interfaces:**
- Produces schemas: `NotificationResponse`, `UnreadCountResponse`
- Produces `NotificationService`:
  - `__init__(self, user, notification_repo, ingredient_repo, group_repo)`
  - `async def create_group_invite_notification(self, *, invitee_id, invite_id, group_id, group_name, inviter_nickname) -> Notification | None` — uses invitee_id as recipient (not `self.user`)
  - `async def sync_expiry_notifications(self, today: date | None = None) -> None`
  - `async def list_notifications(self) -> list[NotificationResponse]` — sync then list
  - `async def unread_count(self) -> UnreadCountResponse` — sync then count
  - `async def mark_read(self, notification_id: UUID) -> NotificationResponse`
  - `async def mark_all_read(self) -> None`
- Consumes: `compute_status` from `domains.ingredient.service`, `IngredientRepository.get_ingredients` / `list_by_group`, `GroupRepository.get_membership`

**reference_key / copy (exact):**

| type | key | title | body |
|------|-----|-------|------|
| `group_invite` | `group_invite:{invite_id}` | `그룹 초대` | `"{inviter}님이 '{group}'에 초대했습니다"` |
| `expiry_soon` | `expiry_soon:{ingredient_id}` | `유통기한 임박` | `"{name} 유통기한이 {date}까지입니다"` |
| `expiry_expired` | `expiry_expired:{ingredient_id}` | `유통기한 만료` | `"{name} 유통기한이 지났습니다"` |

- [ ] **Step 1: Write failing service tests**

Create `tests/unit/test_notification_service.py`:

```python
from datetime import date, timedelta

import pytest

from domains.group.repository import GroupRepository
from domains.group.schemas import CreateGroupRequest
from domains.group.service import GroupService
from domains.ingredient.model import Ingredient
from domains.ingredient.repository import IngredientRepository
from domains.notification.repository import NotificationRepository
from domains.notification.service import NotificationService
from domains.shopping.repository import ShoppingRepository
from domains.user.model import User
from domains.user.repository import UserRepository


def _notif_service(user, db_session) -> NotificationService:
    return NotificationService(
        user=user,
        notification_repo=NotificationRepository(db_session),
        ingredient_repo=IngredientRepository(db_session),
        group_repo=GroupRepository(db_session),
    )


def _group_service(user, db_session) -> GroupService:
    return GroupService(
        user=user,
        group_repo=GroupRepository(db_session),
        user_repo=UserRepository(db_session),
        ingredient_repo=IngredientRepository(db_session),
        shopping_repo=ShoppingRepository(db_session),
        notification_repo=NotificationRepository(db_session),
    )


@pytest.mark.asyncio
async def test_sync_creates_soon_once(db_session, test_user):
    today = date(2026, 7, 21)
    db_session.add(
        Ingredient(
            user_id=test_user.id,
            ingredient_name="우유",
            purchase_date=today,
            expiration_date=today + timedelta(days=2),
        )
    )
    await db_session.flush()

    service = _notif_service(test_user, db_session)
    first = await service.list_notifications(today=today)
    second = await service.list_notifications(today=today)
    soon = [n for n in first if n.type == "expiry_soon"]
    assert len(soon) == 1
    assert soon[0].title == "유통기한 임박"
    assert len([n for n in second if n.type == "expiry_soon"]) == 1


@pytest.mark.asyncio
async def test_soon_then_expired_creates_second(db_session, test_user):
    soon_day = date(2026, 7, 21)
    expired_day = date(2026, 7, 25)
    db_session.add(
        Ingredient(
            user_id=test_user.id,
            ingredient_name="우유",
            purchase_date=soon_day,
            expiration_date=date(2026, 7, 23),
        )
    )
    await db_session.flush()

    service = _notif_service(test_user, db_session)
    await service.list_notifications(today=soon_day)
    listed = await service.list_notifications(today=expired_day)
    types = {n.type for n in listed}
    assert "expiry_soon" in types
    assert "expiry_expired" in types


@pytest.mark.asyncio
async def test_create_group_invite_notification_for_invitee(db_session, test_user):
    invitee = User(
        email="invitee@example.com",
        password="hashed",
        nickname="invitee",
    )
    db_session.add(invitee)
    await db_session.flush()

    owner_svc = _group_service(test_user, db_session)
    # If Task 5 not done yet, call NotificationService directly:
    from uuid import uuid4

    invite_id = uuid4()
    service = _notif_service(test_user, db_session)
    created = await service.create_group_invite_notification(
        invitee_id=invitee.id,
        invite_id=invite_id,
        group_id=uuid4(),
        group_name="우리집",
        inviter_nickname=test_user.nickname,
    )
    assert created is not None
    invitee_list = await _notif_service(invitee, db_session).list_notifications()
    assert len(invitee_list) == 1
    assert invitee_list[0].type == "group_invite"
    assert invitee_list[0].payload["invite_id"] == str(invite_id)
    owner_list = await service.list_notifications()
    assert all(n.type != "group_invite" for n in owner_list)
```

**Note:** `list_notifications(today=...)` optional `today` is for tests only — production callers omit it.

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/unit/test_notification_service.py -v`

Expected: FAIL (missing service/schemas; GroupService may lack `notification_repo` until Task 5 — for Step 1 tests that call `_group_service`, either skip group helper until Task 5 or only use direct `create_group_invite_notification` as shown)

- [ ] **Step 3: Implement schemas**

Create `src/domains/notification/schemas.py`:

```python
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    id: UUID
    type: str
    title: str
    body: str
    payload: dict[str, Any]
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UnreadCountResponse(BaseModel):
    count: int = Field(ge=0)
```

- [ ] **Step 4: Implement service**

Create `src/domains/notification/service.py`:

```python
from __future__ import annotations

from datetime import date
from uuid import UUID

import uuid6

from core.exception.exceptions import NotificationNotFoundException
from domains.group.repository import GroupRepository
from domains.ingredient.model import Ingredient
from domains.ingredient.repository import IngredientRepository
from domains.ingredient.service import compute_status
from domains.notification.model import Notification
from domains.notification.repository import NotificationRepository
from domains.notification.schemas import NotificationResponse, UnreadCountResponse
from domains.user.model import User


class NotificationService:
    def __init__(
        self,
        user: User,
        notification_repo: NotificationRepository,
        ingredient_repo: IngredientRepository,
        group_repo: GroupRepository,
    ) -> None:
        self.user = user
        self.notification_repo = notification_repo
        self.ingredient_repo = ingredient_repo
        self.group_repo = group_repo

    async def create_group_invite_notification(
        self,
        *,
        invitee_id: UUID,
        invite_id: UUID,
        group_id: UUID,
        group_name: str,
        inviter_nickname: str,
    ) -> Notification | None:
        body = f"{inviter_nickname}님이 '{group_name}'에 초대했습니다"
        return await self.notification_repo.create_if_absent(
            Notification(
                id=uuid6.uuid7(),
                user_id=invitee_id,
                type="group_invite",
                title="그룹 초대",
                body=body,
                reference_key=f"group_invite:{invite_id}",
                payload={
                    "invite_id": str(invite_id),
                    "group_id": str(group_id),
                    "group_name": group_name,
                    "inviter_nickname": inviter_nickname,
                },
            )
        )

    async def sync_expiry_notifications(self, today: date | None = None) -> None:
        today = today or date.today()
        ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
        membership = await self.group_repo.get_membership(self.user.id)
        if membership is not None:
            ingredients = [
                *ingredients,
                *await self.ingredient_repo.list_by_group(membership.group_id),
            ]
        for ingredient in ingredients:
            await self._maybe_create_expiry(ingredient, today)

    async def _maybe_create_expiry(
        self, ingredient: Ingredient, today: date
    ) -> None:
        status = compute_status(ingredient.expiration_date, today=today)
        if status == "soon":
            ntype = "expiry_soon"
            title = "유통기한 임박"
            body = (
                f"{ingredient.ingredient_name} 유통기한이 "
                f"{ingredient.expiration_date.isoformat()}까지입니다"
            )
        elif status == "expired":
            ntype = "expiry_expired"
            title = "유통기한 만료"
            body = f"{ingredient.ingredient_name} 유통기한이 지났습니다"
        else:
            return

        await self.notification_repo.create_if_absent(
            Notification(
                id=uuid6.uuid7(),
                user_id=self.user.id,
                type=ntype,
                title=title,
                body=body,
                reference_key=f"{ntype}:{ingredient.id}",
                payload={
                    "ingredient_id": ingredient.id,
                    "ingredient_name": ingredient.ingredient_name,
                    "expiration_date": (
                        ingredient.expiration_date.isoformat()
                        if ingredient.expiration_date
                        else None
                    ),
                    "group_id": str(ingredient.group_id)
                    if ingredient.group_id
                    else None,
                },
            )
        )

    async def list_notifications(
        self, today: date | None = None
    ) -> list[NotificationResponse]:
        await self.sync_expiry_notifications(today=today)
        rows = await self.notification_repo.list_by_user(self.user.id)
        return [NotificationResponse.model_validate(r) for r in rows]

    async def unread_count(
        self, today: date | None = None
    ) -> UnreadCountResponse:
        await self.sync_expiry_notifications(today=today)
        count = await self.notification_repo.count_unread(self.user.id)
        return UnreadCountResponse(count=count)

    async def mark_read(self, notification_id: UUID) -> NotificationResponse:
        row = await self.notification_repo.get_by_id_for_user(
            notification_id, self.user.id
        )
        if row is None:
            raise NotificationNotFoundException()
        row = await self.notification_repo.mark_read(row)
        return NotificationResponse.model_validate(row)

    async def mark_all_read(self) -> None:
        await self.notification_repo.mark_all_read(self.user.id)
```

- [ ] **Step 5: Adjust unit tests that used `_group_service`** — keep only direct invite notification test until Task 5; remove unused `_group_service` from this file for now.

- [ ] **Step 6: Run — expect PASS**

Run: `pytest tests/unit/test_notification_service.py -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/domains/notification/schemas.py src/domains/notification/service.py tests/unit/test_notification_service.py
git commit -m "$(cat <<'EOF'
Feat: NotificationService (expiry sync·초대 알림) 추가

EOF
)"
```

---

### Task 5: Wire group invite → notification

**Files:**
- Modify: `src/domains/group/service.py`
- Modify: `src/api/deps.py` (`get_group_service`)
- Modify: `tests/unit/test_group_service.py` (`_service` helper + invite test)

**Interfaces:**
- `GroupService.__init__` gains `notification_repo: NotificationRepository | None = None` (or required — prefer required and update all call sites)
- On **newly created** invite only, call `NotificationService.create_group_invite_notification` (or repo via a one-off `NotificationService` constructed with invitee as user is wrong — use the method that takes `invitee_id`)

Recommended: keep `notification_repo` on `GroupService` and instantiate a thin helper, or inject `NotificationRepository` and duplicate the create payload once. Prefer calling:

```python
from domains.notification.service import NotificationService
# inside invite_by_nickname after new invite:
notif = NotificationService(
    user=self.user,
    notification_repo=self.notification_repo,
    ingredient_repo=self.ingredient_repo,
    group_repo=self.group_repo,
)
await notif.create_group_invite_notification(
    invitee_id=invitee.id,
    invite_id=invite.id,
    group_id=group.id,
    group_name=group.name,
    inviter_nickname=self.user.nickname,
)
```

Only when `invite` was newly created (`find_pending_invite` was None path).

- [ ] **Step 1: Extend invite idempotency test**

In `tests/unit/test_group_service.py`, update `_service` to pass `notification_repo=NotificationRepository(db_session)`.

Extend `test_invite_by_nickname_is_idempotent_and_listed_for_invitee`:

```python
from domains.notification.repository import NotificationRepository

# after invites listed:
notif_repo = NotificationRepository(db_session)
invitee_notifs = await notif_repo.list_by_user(invitee.id)
assert len(invitee_notifs) == 1
assert invitee_notifs[0].type == "group_invite"
assert invitee_notifs[0].reference_key == f"group_invite:{first.id}"
owner_notifs = await notif_repo.list_by_user(test_user.id)
assert owner_notifs == []
```

- [ ] **Step 2: Run — expect FAIL** (no notification created / TypeError missing arg)

Run: `pytest tests/unit/test_group_service.py::test_invite_by_nickname_is_idempotent_and_listed_for_invitee -v`

- [ ] **Step 3: Implement wiring**

Update `GroupService.__init__` to accept `notification_repo: NotificationRepository`.

In `invite_by_nickname`, track whether created:

```python
        invite = await self.group_repo.find_pending_invite(group.id, invitee.id)
        created_new = False
        if invite is None:
            invite = await self.group_repo.add_invite(
                GroupInvite(
                    group_id=group.id,
                    inviter_id=self.user.id,
                    invitee_id=invitee.id,
                )
            )
            created_new = True
        if created_new:
            notif_service = NotificationService(
                user=self.user,
                notification_repo=self.notification_repo,
                ingredient_repo=self.ingredient_repo,
                group_repo=self.group_repo,
            )
            await notif_service.create_group_invite_notification(
                invitee_id=invitee.id,
                invite_id=invite.id,
                group_id=group.id,
                group_name=group.name,
                inviter_nickname=self.user.nickname,
            )
        return await self._to_invite_response(invite)
```

Update `get_group_service` in `src/api/deps.py`:

```python
        notification_repo=NotificationRepository(session),
```

Update all `GroupService(` constructions in tests.

- [ ] **Step 4: Run group tests**

Run: `pytest tests/unit/test_group_service.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domains/group/service.py src/api/deps.py tests/unit/test_group_service.py
git commit -m "$(cat <<'EOF'
Feat: 닉네임 초대 시 수신자 인앱 알림 생성

EOF
)"
```

---

### Task 6: Notification HTTP API

**Files:**
- Create: `src/api/v1/endpoints/notification.py`
- Modify: `src/api/deps.py` — `get_notification_service`
- Modify: `src/api/api.py` — include router
- Test: `tests/api/test_notification_api.py` (신규)

**Interfaces:**
- `GET /api/v1/notifications` → `list[NotificationResponse]`
- `GET /api/v1/notifications/unread-count` → `UnreadCountResponse`
- `PATCH /api/v1/notifications/{id}/read` → `NotificationResponse`
- `POST /api/v1/notifications/read-all` → `204`

- [ ] **Step 1: Write failing API tests**

Create `tests/api/test_notification_api.py`:

```python
from datetime import date, timedelta

from httpx import AsyncClient

from core.exception.codes import ErrorCode
from domains.ingredient.model import Ingredient
from domains.user.model import User
from core import security


async def test_notifications_require_auth(client: AsyncClient):
    response = await client.get("/api/v1/notifications")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_expiry_soon_appears_on_list(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    test_user: User,
):
    today = date.today()
    db_session.add(
        Ingredient(
            user_id=test_user.id,
            ingredient_name="우유",
            purchase_date=today,
            expiration_date=today + timedelta(days=1),
        )
    )
    await db_session.flush()

    listed = await client.get("/api/v1/notifications", headers=auth_headers)
    assert listed.status_code == 200
    body = listed.json()
    assert any(item["type"] == "expiry_soon" for item in body)

    count = await client.get(
        "/api/v1/notifications/unread-count", headers=auth_headers
    )
    assert count.status_code == 200
    assert count.json()["count"] >= 1

    notif_id = next(item["id"] for item in body if item["type"] == "expiry_soon")
    read = await client.patch(
        f"/api/v1/notifications/{notif_id}/read", headers=auth_headers
    )
    assert read.status_code == 200
    assert read.json()["is_read"] is True

    await client.post("/api/v1/notifications/read-all", headers=auth_headers)
    count2 = await client.get(
        "/api/v1/notifications/unread-count", headers=auth_headers
    )
    assert count2.json()["count"] == 0


async def test_invite_creates_notification_for_invitee(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    test_user: User,
):
    invitee = User(
        email="invitee2@example.com",
        password=security.hash_password("password123"),
        nickname="invitee2",
        is_email_verified=True,
    )
    db_session.add(invitee)
    await db_session.flush()
    invitee_headers = {
        "Authorization": f"Bearer {security.create_jwt(invitee.id)}"
    }

    created = await client.post(
        "/api/v1/groups",
        headers=auth_headers,
        json={"name": "알림그룹"},
    )
    assert created.status_code == 201

    invited = await client.post(
        "/api/v1/groups/me/invites",
        headers=auth_headers,
        json={"nickname": "invitee2"},
    )
    assert invited.status_code == 201
    invite_id = invited.json()["id"]

    listed = await client.get(
        "/api/v1/notifications", headers=invitee_headers
    )
    assert listed.status_code == 200
    invites = [n for n in listed.json() if n["type"] == "group_invite"]
    assert len(invites) == 1
    assert invites[0]["payload"]["invite_id"] == invite_id

    other = await client.get("/api/v1/notifications", headers=auth_headers)
    assert all(n["type"] != "group_invite" for n in other.json())


async def test_read_other_users_notification_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    test_user: User,
):
    other = User(
        email="other@example.com",
        password=security.hash_password("password123"),
        nickname="otheruser",
        is_email_verified=True,
    )
    db_session.add(other)
    await db_session.flush()
    other_headers = {
        "Authorization": f"Bearer {security.create_jwt(other.id)}"
    }

    today = date.today()
    db_session.add(
        Ingredient(
            user_id=test_user.id,
            ingredient_name="계란",
            purchase_date=today,
            expiration_date=today,
        )
    )
    await db_session.flush()
    listed = await client.get("/api/v1/notifications", headers=auth_headers)
    notif_id = listed.json()[0]["id"]

    resp = await client.patch(
        f"/api/v1/notifications/{notif_id}/read",
        headers=other_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == ErrorCode.NOTIFICATION_NOT_FOUND
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/api/test_notification_api.py -v`

Expected: FAIL (404 on routes)

- [ ] **Step 3: Implement endpoint + DI + router**

Create `src/api/v1/endpoints/notification.py`:

```python
from uuid import UUID

from fastapi import APIRouter, Depends, status

from api.deps import get_notification_service
from core.exception.exceptions import (
    NotificationNotFoundException,
    UnAuthorizedException,
)
from core.exception.openapi import create_error_response
from domains.notification.schemas import NotificationResponse, UnreadCountResponse
from domains.notification.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=list[NotificationResponse],
    responses=create_error_response(UnAuthorizedException),
)
async def list_notifications(
    service: NotificationService = Depends(get_notification_service),
) -> list[NotificationResponse]:
    return await service.list_notifications()


@router.get(
    "/unread-count",
    status_code=status.HTTP_200_OK,
    response_model=UnreadCountResponse,
    responses=create_error_response(UnAuthorizedException),
)
async def unread_count(
    service: NotificationService = Depends(get_notification_service),
) -> UnreadCountResponse:
    return await service.unread_count()


@router.patch(
    "/{notification_id}/read",
    status_code=status.HTTP_200_OK,
    response_model=NotificationResponse,
    responses=create_error_response(
        UnAuthorizedException, NotificationNotFoundException
    ),
)
async def mark_read(
    notification_id: UUID,
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    return await service.mark_read(notification_id)


@router.post(
    "/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=create_error_response(UnAuthorizedException),
)
async def mark_all_read(
    service: NotificationService = Depends(get_notification_service),
) -> None:
    await service.mark_all_read()
```

In `src/api/deps.py`:

```python
from domains.notification.repository import NotificationRepository
from domains.notification.service import NotificationService


def get_notification_repo(
    session: AsyncSession = Depends(get_db),
) -> NotificationRepository:
    return NotificationRepository(session)


def get_notification_service(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> NotificationService:
    return NotificationService(
        user=user,
        notification_repo=NotificationRepository(session),
        ingredient_repo=IngredientRepository(session),
        group_repo=GroupRepository(session),
    )
```

In `src/api/api.py`:

```python
from api.v1.endpoints.notification import router as notification_router
# ...
api_router.include_router(notification_router)
```

- [ ] **Step 4: Run API tests — expect PASS**

Run: `pytest tests/api/test_notification_api.py -v`

Expected: PASS

- [ ] **Step 5: Run related suites**

Run: `pytest tests/unit/test_notification_*.py tests/api/test_notification_api.py tests/unit/test_group_service.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/api/v1/endpoints/notification.py src/api/deps.py src/api/api.py tests/api/test_notification_api.py
git commit -m "$(cat <<'EOF'
Feat: 인앱 알림 API (목록·미읽음·읽음) 추가

EOF
)"
```

---

### Task 7: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Full related test run**

Run: `pytest tests/unit/test_notification_exception.py tests/unit/test_notification_repository.py tests/unit/test_notification_service.py tests/api/test_notification_api.py tests/unit/test_group_service.py tests/api/test_group_api.py -v`

Expected: PASS

- [ ] **Step 2: Spec checklist**

Confirm against `docs/superpowers/specs/2026-07-21-in-app-notifications-design.md`:
- [x] invite notification on create
- [x] expiry sync on list/unread-count
- [x] reference_key uniqueness
- [x] read / read-all / unread-count
- [x] NOTIFICATION_NOT_FOUND
- [x] no push/scheduler

- [ ] **Step 3: Commit plan checkbox updates if desired** (optional — or leave checkboxes for the executor)

No extra commit required if nothing changed.

---

## Plan Self-Review

**Spec coverage:** Goal, Decisions, API, Flows, Errors, Testing, Migration — each maps to Tasks 1–6.

**Placeholders:** None intentional; executor must resolve `create_if_absent` id defaulting as noted in Task 3.

**Type consistency:** `NotificationService.create_group_invite_notification(..., invitee_id=...)` used in Tasks 4–5; routes use `UUID` ids; ingredient ids remain `int` in payload.
