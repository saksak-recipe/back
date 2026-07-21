# Household Group Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 유저당 활성 그룹 1개로 가족·동거가 냉장고·장보기를 공유하고, 닉네임/코드로 초대하며, 개인 항목을 선택해 그룹에 복사·이동할 수 있는 백엔드 API를 만든다.

**Architecture:** `domains/group/` (Group / GroupMember / GroupInvite) + 기존 `ingredients`·`shopping_items`에 nullable `group_id`. 개인 API는 `group_id IS NULL`만 다루고, 그룹 API는 멤버십 확인 후 `group_id` 스코프로 CRUD·merge한다.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic, pytest, PostgreSQL (테스트는 SQLite in-memory + partial unique는 PG 전용 — 앱 레벨 중복 검사로 SQLite 테스트 보완)

## Global Constraints

- 백엔드만 (앱 UI Out of Scope)
- 유저당 활성 멤버십 **최대 1개** (`group_members.user_id` UNIQUE)
- 개인 냉장고·장보기 **유지**; merge는 항목 선택 + `copy`|`move`
- owner 나가기 불가 — **해산만** (소유권 이전 없음)
- 추천(RAG/AI)은 MVP에서 **개인 냉장고만** (변경 없음)
- Spec: `docs/superpowers/specs/2026-07-21-household-group-design.md`
- **Prerequisite:** 개인 `shopping_items` 도메인(`domains/shopping/` + `/shopping-items` API)이 머지되어 있어야 Task 6–7 진행 가능. 없으면 `docs/superpowers/plans/2026-07-21-shopping-list.md`를 먼저 완료한다. Task 1–5는 ingredient만으로 진행 가능.

## File map

| File | Responsibility |
|------|----------------|
| `src/domains/group/__init__.py` | 패키지 |
| `src/domains/group/model.py` | `Group`, `GroupMember`, `GroupInvite`, `GroupRole`, `InviteStatus` |
| `src/domains/group/schemas.py` | request/response |
| `src/domains/group/repository.py` | groups/members/invites 쿼리 |
| `src/domains/group/service.py` | 그룹·초대·merge·그룹 ingredient/shopping 오케스트레이션 |
| `src/api/v1/endpoints/group.py` | `/groups` HTTP |
| `src/api/deps.py` | `get_group_service` |
| `src/api/api.py` | include router |
| `src/core/exception/codes.py` | 그룹 ErrorCode |
| `src/core/exception/exceptions.py` | 필요 시 thin wrapper (또는 기존 Conflict/NotFound + code) |
| `src/domains/ingredient/model.py` | `group_id` FK |
| `src/domains/ingredient/repository.py` | 개인=`group_id IS NULL`; 그룹 스코프 메서드 |
| `src/domains/shopping/model.py` | `group_id` FK + partial unique |
| `src/domains/shopping/repository.py` | 동일 스코프 분리 |
| `src/domains/user/model.py` | relationships (optional) |
| `alembic/versions/*_add_household_groups.py` | 마이그레이션 |
| `tests/conftest.py` | 모델 import + Integer id patch |
| `tests/unit/test_group_service.py` | 서비스 단위 |
| `tests/api/test_group_api.py` | API |

---

### Task 1: ErrorCode + ORM models + migration

**Files:**
- Modify: `src/core/exception/codes.py`
- Create: `src/domains/group/__init__.py` (empty)
- Create: `src/domains/group/model.py`
- Modify: `src/domains/ingredient/model.py` — nullable `group_id`
- Modify: `src/domains/shopping/model.py` — nullable `group_id` (shopping 존재 시)
- Create: `alembic/versions/d4e5f6a7b8c9_add_household_groups.py`
  - `down_revision`: shopping migration이 있으면 그 revision, 없으면 `b2c3d4e5f6a7`
- Modify: `tests/conftest.py` — import Group models; ShoppingItem id Integer patch if present

**Interfaces:**
- Produces ErrorCodes: `ALREADY_IN_GROUP`, `GROUP_NOT_FOUND`, `INVITE_CODE_INVALID`, `INVALID_INVITE`, `OWNER_CANNOT_LEAVE`, `INGREDIENT_NAME_CONFLICT`
- Produces: `GroupRole` = `"owner"` | `"member"`; `InviteStatus` = `"pending"` | `"accepted"` | `"rejected"` | `"cancelled"`
- Produces models per spec columns; `invite_code` String(8) unique

- [ ] **Step 1: Add ErrorCodes**

```python
# codes.py — 회원/그룹 섹션에 추가
ALREADY_IN_GROUP = "ALREADY_IN_GROUP"
GROUP_NOT_FOUND = "GROUP_NOT_FOUND"
INVITE_CODE_INVALID = "INVITE_CODE_INVALID"
INVALID_INVITE = "INVALID_INVITE"
OWNER_CANNOT_LEAVE = "OWNER_CANNOT_LEAVE"
INGREDIENT_NAME_CONFLICT = "INGREDIENT_NAME_CONFLICT"
```

- [ ] **Step 2: Implement `domains/group/model.py`**

```python
from __future__ import annotations

import enum
from datetime import datetime

import uuid6
from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class GroupRole(str, enum.Enum):
    owner = "owner"
    member = "member"


class InviteStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    cancelled = "cancelled"


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    invite_code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)
    owner_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    members: Mapped[list[GroupMember]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    invites: Mapped[list[GroupInvite]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        unique=True,  # 유저당 1그룹
    )
    role: Mapped[GroupRole] = mapped_column(
        Enum(GroupRole, name="group_role", native_enum=False),
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    group: Mapped[Group] = relationship(back_populates="members")


class GroupInvite(Base):
    __tablename__ = "group_invites"

    id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )
    group_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    inviter_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    invitee_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[InviteStatus] = mapped_column(
        Enum(InviteStatus, name="invite_status", native_enum=False),
        nullable=False,
        default=InviteStatus.pending,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    group: Mapped[Group] = relationship(back_populates="invites")
```

- [ ] **Step 3: Add `group_id` to Ingredient (and ShoppingItem if present)**

```python
# ingredient/model.py — 컬럼 추가
group_id: Mapped[uuid6.UUID | None] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey("groups.id", ondelete="CASCADE"),
    nullable=True,
    index=True,
)
```

ShoppingItem도 동일. UniqueConstraint `(user_id, name)`는 마이그레이션에서 drop 후 partial unique로 교체 (아래 Step 4).

- [ ] **Step 4: Alembic migration**

`upgrade()` 요약:
1. `groups`, `group_members`, `group_invites` create
2. `ingredients.group_id` nullable FK + index
3. `op.create_index("uq_ingredients_group_name", "ingredients", ["group_id", "ingredient_name"], unique=True, postgresql_where=sa.text("group_id IS NOT NULL"))`
4. shopping 있으면: `shopping_items.group_id` 추가; `uq_shopping_items_user_name` drop;  
   `uq_shopping_items_user_name_personal` partial unique `(user_id, name) WHERE group_id IS NULL`;  
   `uq_shopping_items_group_name` partial `(group_id, name) WHERE group_id IS NOT NULL`

SQLite 테스트는 partial unique를 못 쓰므로 **서비스에서 이름 충돌을 검사**한다.

- [ ] **Step 5: conftest imports**

```python
from domains.group.model import Group, GroupInvite, GroupMember  # noqa: F401
# ShoppingItem id Integer patch if model exists (Ingredient와 동일)
```

- [ ] **Step 6: Commit**

```bash
git add src/core/exception/codes.py src/domains/group/ src/domains/ingredient/model.py \
  src/domains/shopping/model.py alembic/versions/d4e5f6a7b8c9_add_household_groups.py tests/conftest.py
git commit -m "$(cat <<'EOF'
Feat: 가구 그룹 ORM·마이그레이션 및 group_id 컬럼 추가

EOF
)"
```

---

### Task 2: Schemas + GroupRepository

**Files:**
- Create: `src/domains/group/schemas.py`
- Create: `src/domains/group/repository.py`
- Test: `tests/unit/test_group_schemas.py`

**Interfaces — schemas:**
- `CreateGroupRequest(name: str)` — strip, 1–40자
- `UpdateGroupRequest(name: str)` — 동일
- `GroupMemberResponse(user_id, nickname, role)`
- `GroupResponse(id, name, invite_code, owner_id, members: list[GroupMemberResponse], created_at)`
- `InviteByNicknameRequest(nickname: str)`
- `JoinByCodeRequest(invite_code: str)`
- `GroupInviteResponse(id, group_id, group_name, inviter_nickname, status, created_at)`
- `MergeRequest(mode: Literal["copy","move"], ingredients: list[int]=[], shopping_items: list[int]=[])`
- `MergeResponse(created_ingredients, created_shopping_items, skipped_ingredient_ids, skipped_shopping_item_ids, deleted_ingredient_ids, deleted_shopping_item_ids)`

**Interfaces — repository:**
```python
class GroupRepository:
    def __init__(self, session: AsyncSession): ...

    async def get_membership(self, user_id: UUID) -> GroupMember | None: ...
    async def get_group(self, group_id: UUID) -> Group | None: ...
    async def get_group_with_members(self, group_id: UUID) -> Group | None: ...
    async def get_by_invite_code(self, code: str) -> Group | None: ...
    async def add_group(self, group: Group) -> Group: ...
    async def add_member(self, member: GroupMember) -> GroupMember: ...
    async def delete_member(self, group_id: UUID, user_id: UUID) -> bool: ...
    async def delete_group(self, group: Group) -> None: ...  # session.delete + cascade
    async def find_pending_invite(
        self, group_id: UUID, invitee_id: UUID
    ) -> GroupInvite | None: ...
    async def list_pending_for_invitee(self, invitee_id: UUID) -> list[GroupInvite]: ...
    async def get_invite(self, invite_id: UUID) -> GroupInvite | None: ...
    async def add_invite(self, invite: GroupInvite) -> GroupInvite: ...
```

멤버 nickname은 service에서 `UserRepository.get_user_by_id`로 조인하거나, repository에서 `selectinload` + user relationship 추가. MVP: `GroupMember`에 user relationship 추가해도 됨.

- [ ] **Step 1: Schema unit tests** (`test_group_schemas.py`) — name strip/길이, merge mode literal
- [ ] **Step 2: Implement schemas + repository**
- [ ] **Step 3:** `pytest tests/unit/test_group_schemas.py -v` PASS
- [ ] **Step 4: Commit** — `Feat: 그룹 schemas·repository 추가`

---

### Task 3: GroupService — create / me / patch / dissolve / leave / kick

**Files:**
- Create: `src/domains/group/service.py` (core methods first)
- Test: `tests/unit/test_group_service.py`

**Interfaces:**
```python
class GroupService:
    def __init__(
        self,
        user: User,
        group_repo: GroupRepository,
        user_repo: UserRepository,
        ingredient_repo: IngredientRepository,
        shopping_repo: ShoppingRepository | None = None,  # shopping 없으면 None, merge shopping skip
    ): ...

    async def create(self, request: CreateGroupRequest) -> GroupResponse: ...
    async def get_me(self) -> GroupResponse: ...
    async def update_me(self, request: UpdateGroupRequest) -> GroupResponse: ...
    async def dissolve(self) -> None: ...
    async def leave(self) -> None: ...
    async def kick(self, user_id: UUID) -> None: ...
```

**Behavior:**
- `create`: membership 있으면 `ConflictException(ALREADY_IN_GROUP)`; `invite_code = secrets.token_hex(4)` (8 hex chars); owner member insert
- `get_me`: membership 없으면 `NotFoundException(GROUP_NOT_FOUND)`
- `update_me` / `dissolve` / `kick`: role != owner → `ForbiddenException`
- `leave`: role == owner → `BadRequestException(OWNER_CANNOT_LEAVE)`
- `kick`: target이 owner이거나 자기 자신 → 400; 멤버 없으면 404
- `_require_membership()` / `_require_owner()` 헬퍼
- `_to_group_response(group)` — members의 nickname을 user_repo로 조회

- [ ] **Step 1: Failing unit tests**

```python
@pytest.mark.asyncio
async def test_create_group_and_get_me(db_session, test_user):
    # real repos + GroupService
    ...
    created = await service.create(CreateGroupRequest(name="우리집"))
    assert created.name == "우리집"
    assert len(created.invite_code) == 8
    assert created.members[0].role == "owner"
    me = await service.get_me()
    assert me.id == created.id

@pytest.mark.asyncio
async def test_create_second_group_conflicts(db_session, test_user):
    ...
    with pytest.raises(ConflictException) as exc:
        await service.create(CreateGroupRequest(name="둘"))
    assert exc.value.code == ErrorCode.ALREADY_IN_GROUP

@pytest.mark.asyncio
async def test_owner_cannot_leave(db_session, test_user):
    ...
    with pytest.raises(BadRequestException) as exc:
        await service.leave()
    assert exc.value.code == ErrorCode.OWNER_CANNOT_LEAVE

@pytest.mark.asyncio
async def test_member_leave_and_owner_dissolve(...):
    # second user joins via repo insert as member, leave, then dissolve
    ...
```

- [ ] **Step 2: Implement create/get_me/update/dissolve/leave/kick**
- [ ] **Step 3:** `pytest tests/unit/test_group_service.py -v` PASS (해당 테스트만)
- [ ] **Step 4: Commit** — `Feat: 그룹 생성·조회·해산·나가기·추방 서비스`

---

### Task 4: Invites + join + rotate-code

**Files:**
- Modify: `src/domains/group/service.py`
- Modify: `tests/unit/test_group_service.py`

**Interfaces:**
```python
async def invite_by_nickname(self, request: InviteByNicknameRequest) -> GroupInviteResponse: ...
async def list_my_invites(self) -> list[GroupInviteResponse]: ...
async def accept_invite(self, invite_id: UUID) -> GroupResponse: ...
async def reject_invite(self, invite_id: UUID) -> None: ...
async def join_by_code(self, request: JoinByCodeRequest) -> GroupResponse: ...
async def rotate_code(self) -> GroupResponse: ...  # owner only
```

**Behavior:**
- invite: 자기 자신 → `BadRequestException(INVALID_INVITE)`; nickname 없음 → `UserNotFoundException`; pending 있으면 **기존 행 반환(멱등)**; 멤버 아니어도 초대 생성 가능(상대가 다른 그룹이어도 pending OK)
- accept: invitee 본인 + pending만; 이미 그룹 → `ALREADY_IN_GROUP`; member role로 insert, status=accepted
- reject: invitee 본인 + pending → rejected
- join_by_code: 코드 없음 → `NotFoundException(INVITE_CODE_INVALID)`; 이미 그룹 → 409; member insert
- rotate_code: owner만; 새 `token_hex(4)`

- [ ] **Step 1: Failing tests** — invite/accept/reject/join/rotate, self-invite, bad code, accept while already in group
- [ ] **Step 2: Implement**
- [ ] **Step 3:** `pytest tests/unit/test_group_service.py -v` PASS
- [ ] **Step 4: Commit** — `Feat: 그룹 닉네임·코드 초대 및 가입`

---

### Task 5: Ingredient personal scope + group ingredient CRUD

**Files:**
- Modify: `src/domains/ingredient/repository.py`
- Modify: `src/domains/ingredient/service.py` — 개인 경로가 그룹 행을 보지 않게
- Modify: `src/domains/group/service.py` — group ingredient methods
- Test: `tests/unit/test_ingredient_service.py` (회귀) + `tests/unit/test_group_service.py`

**Interfaces — IngredientRepository 추가/변경:**
```python
# 기존 get_ingredients / get_by_id / delete_* 에 조건 추가:
#   Ingredient.group_id.is_(None)

async def list_by_group(self, group_id: UUID) -> list[Ingredient]: ...
async def get_by_id_in_group(
    self, ingredient_id: int, group_id: UUID
) -> Ingredient | None: ...
async def find_name_in_group(
    self, group_id: UUID, name: str
) -> Ingredient | None: ...
async def delete_in_group(self, ingredient_id: int, group_id: UUID) -> bool: ...
async def delete_all_in_group(self, group_id: UUID) -> int: ...
```

**GroupService:**
```python
async def list_ingredients(self) -> list[GetIngredientResponse]: ...
async def add_ingredients(self, request: AddIngredientRequest) -> list[AddIngredientResponse]: ...
async def update_ingredient(self, ingredient_id: int, request: UpdateIngredientRequest) -> GetIngredientResponse: ...
async def delete_ingredient(self, ingredient_id: int) -> None: ...
async def delete_all_ingredients(self) -> None: ...
```

**Behavior:**
- add: 그룹에 동일 `ingredient_name` 있으면 **단건/목록 중 충돌분은 409** — 다건 요청 시 하나라도 충돌하면 전체 롤백 또는 충돌 이름만 409. **선택: 다건은 shopping과 달리 하나라도 존재하면 ConflictException(INGREDIENT_NAME_CONFLICT)** (스펙: 단건 409; 개인 API는 다건 리스트이므로 그룹도 리스트 받되, 추가 전 전부 검사 후 하나라도 있으면 409).
- 생성 시 `user_id=self.user.id`, `group_id=membership.group_id`
- 정렬/status는 기존 `compute_status` / `_list_sort_key` 재사용 (ingredient service에서 import)

- [ ] **Step 1: Failing tests** — personal list excludes group rows; group add conflict 409; group CRUD
- [ ] **Step 2: Implement repo filters + GroupService ingredient methods**
- [ ] **Step 3:** `pytest tests/unit/test_ingredient_service.py tests/unit/test_group_service.py -v` PASS
- [ ] **Step 4: Commit** — `Feat: 그룹 냉장고 CRUD 및 개인 스코프 분리`

---

### Task 6: Shopping personal scope + group shopping CRUD

**Prerequisite:** shopping domain complete.

**Files:**
- Modify: `src/domains/shopping/repository.py` — personal `group_id IS NULL`; group methods
- Modify: `src/domains/shopping/service.py` — personal queries만
- Modify: `src/domains/group/service.py`
- Test: shopping + group unit tests

**Interfaces — GroupService:**
```python
async def list_shopping_items(self) -> list[ShoppingItemResponse]: ...
async def add_shopping_items(self, request: AddShoppingItemsRequest) -> list[ShoppingItemResponse]: ...
async def update_shopping_item(self, item_id: int, request: UpdateShoppingItemRequest) -> ShoppingItemResponse: ...
async def delete_shopping_item(self, item_id: int) -> None: ...
async def delete_all_shopping_items(self) -> None: ...
async def shopping_to_ingredient(self, item_id: int) -> AddIngredientResponse: ...
```

**Behavior:**
- add: 그룹 내 동일 name **skip** (개인 shopping과 동일), 신규만 반환
- `to-ingredient`: 그룹 shopping 삭제 → **그룹** ingredient 생성 (`group_id` 설정). 그룹에 같은 이름 ingredient 있으면 409 또는 skip-after-delete? → **409 전에 검사**, 충돌 시 shopping 유지 + 409

- [ ] **Step 1: Failing tests**
- [ ] **Step 2: Implement**
- [ ] **Step 3:** `pytest tests/unit/test_shopping_service.py tests/unit/test_group_service.py -v` PASS
- [ ] **Step 4: Commit** — `Feat: 그룹 장보기 CRUD 및 to-ingredient`

---

### Task 7: Merge (copy / move)

**Files:**
- Modify: `src/domains/group/service.py`
- Modify: `tests/unit/test_group_service.py`

**Interfaces:**
```python
async def merge(self, request: MergeRequest) -> MergeResponse: ...
```

**Behavior (스펙 그대로):**
1. 멤버십 필수
2. 각 id: `user_id == me` AND `group_id IS NULL` — 아니면 404
3. 그룹에 동일 이름 있으면 id를 skipped_* 에 넣고 continue
4. copy: 그룹 insert; move: insert 후 개인 delete
5. ingredient 복사 시 expiration/purchase 필드 유지; shopping은 name + is_checked=False(또는 원본 is_checked 유지 — **원본 is_checked 유지**)

- [ ] **Step 1: Failing tests**

```python
async def test_merge_copy_keeps_personal_and_skips_dup(...): ...
async def test_merge_move_deletes_personal(...): ...
async def test_merge_foreign_id_not_found(...): ...
```

- [ ] **Step 2: Implement merge**
- [ ] **Step 3:** pytest PASS
- [ ] **Step 4: Commit** — `Feat: 개인→그룹 재료·장보기 merge`

---

### Task 8: HTTP router + deps + API tests

**Files:**
- Create: `src/api/v1/endpoints/group.py`
- Modify: `src/api/deps.py`, `src/api/api.py`
- Test: `tests/api/test_group_api.py`

**Routes** (`APIRouter(prefix="/groups", tags=["groups"])`):

| Method | Path | Handler |
|--------|------|---------|
| POST | `` | create |
| GET | `/me` | get_me |
| PATCH | `/me` | update_me |
| DELETE | `/me` | dissolve |
| POST | `/me/leave` | leave |
| DELETE | `/me/members/{user_id}` | kick |
| POST | `/me/invites` | invite_by_nickname |
| GET | `/invites` | list_my_invites |
| POST | `/invites/{invite_id}/accept` | accept |
| POST | `/invites/{invite_id}/reject` | reject |
| POST | `/join` | join_by_code |
| POST | `/me/rotate-code` | rotate_code |
| GET/POST | `/me/ingredients` | list/add |
| PATCH/DELETE | `/me/ingredients/{id}` | update/delete |
| DELETE | `/me/ingredients` | delete_all |
| GET/POST | `/me/shopping-items` | list/add |
| PATCH/DELETE | `/me/shopping-items/{id}` | update/delete |
| DELETE | `/me/shopping-items` | delete_all |
| POST | `/me/shopping-items/{id}/to-ingredient` | to_ingredient |
| POST | `/me/merge` | merge |

**deps:**
```python
def get_group_service(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GroupService:
    return GroupService(
        user=user,
        group_repo=GroupRepository(session),
        user_repo=UserRepository(session),
        ingredient_repo=IngredientRepository(session),
        shopping_repo=ShoppingRepository(session),  # shopping 없으면 조건부
    )
```

- [ ] **Step 1: API tests** — signup 두 유저, create, invite accept, group ingredient add, merge, leave/dissolve, auth 401
- [ ] **Step 2: Wire router**
- [ ] **Step 3:** `pytest tests/api/test_group_api.py tests/unit/test_group_service.py -v` PASS
- [ ] **Step 4: Commit** — `Feat: 그룹 API 엔드포인트 연결`

---

### Task 9: Full verification

- [ ] **Step 1:** `pytest tests/unit/test_group_service.py tests/api/test_group_api.py tests/unit/test_ingredient_service.py tests/api/test_ingredient*.py -v` (shopping 테스트 포함 가능하면 포함)
- [ ] **Step 2:** 개인 `GET /ingredients`가 그룹 행을 반환하지 않음 회귀 확인
- [ ] **Step 3:** 스펙 체크리스트 대조
  - [ ] 유저당 1그룹
  - [ ] 닉네임+코드 초대
  - [ ] 개인 유지 + merge copy/move + skip
  - [ ] owner 해산만 / member leave
  - [ ] RAG 경로 미변경
- [ ] **Step 4: Commit** (남은 정리만 있으면) 또는 검증만 하고 종료

---

## Spec coverage checklist

| Spec 항목 | Task |
|-----------|------|
| groups / members / invites 테이블 | 1 |
| ingredients/shopping `group_id` + unique | 1, 5, 6 |
| 생성·조회·패치·해산·leave·kick | 3, 8 |
| 닉네임 초대·수락·거절·코드 join·rotate | 4, 8 |
| 그룹 냉장고 CRUD | 5, 8 |
| 그룹 장보기 CRUD + to-ingredient | 6, 8 |
| merge copy/move/skip | 7, 8 |
| 개인 API group_id IS NULL | 5, 6 |
| Error codes | 1, 3–7 |
| RAG 미변경 | (명시적 no-op) |
