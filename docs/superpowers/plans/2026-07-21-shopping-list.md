# Shopping List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 레시피 `missing_ingredients`를 유저당 하나의 장보기 리스트에 모아 두고, 체크·삭제·선택적 냉장고 이동이 가능한 백엔드 API를 만든다.

**Architecture:** `domains/shopping/` (model/repository/service/schemas) + `/api/v1/shopping-items`. `(user_id, name)` UNIQUE로 중복 skip. `to-ingredient`는 `IngredientRepository`로 냉장고 항목을 만든 뒤 shopping item을 삭제한다.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic, pytest, PostgreSQL (테스트는 SQLite in-memory)

## Global Constraints

- 백엔드만 (앱 UI Out of Scope)
- 유저당 암묵적 리스트 하나 — `shopping_lists` 테이블 없음
- 항목은 **이름만** (수량·출처 레시피 없음)
- 중복 추가는 에러가 아님 — skip 후 신규만 201 반환 (전부 중복이면 201 + `[]`)
- `to-ingredient`는 `is_checked`와 무관
- Spec: `docs/superpowers/specs/2026-07-21-shopping-list-design.md`

## File map

| File | Responsibility |
|------|----------------|
| `src/domains/shopping/schemas.py` | request/response pydantic |
| `src/domains/shopping/model.py` | `ShoppingItem` ORM |
| `src/domains/shopping/repository.py` | CRUD + names lookup |
| `src/domains/shopping/service.py` | add/list/patch/delete/to-ingredient |
| `src/api/v1/endpoints/shopping.py` | HTTP routes |
| `src/api/deps.py` | `get_shopping_service` |
| `src/api/api.py` | include router |
| `src/core/exception/codes.py` | `SHOPPING_ITEM_NOT_FOUND` |
| `src/core/exception/exceptions.py` | `ShoppingItemNotFoundException` |
| `src/domains/user/model.py` | `shopping_items` relationship |
| `alembic/versions/c3d4e5f6a7b8_add_shopping_items.py` | migration |
| `tests/conftest.py` | import model + Integer id patch |
| `tests/unit/test_shopping_service.py` | service unit tests |
| `tests/api/test_shopping_api.py` | API tests |

---

### Task 1: ErrorCode + Exception + Schemas + Model + Migration

**Files:**
- Modify: `src/core/exception/codes.py`
- Modify: `src/core/exception/exceptions.py`
- Create: `src/domains/shopping/__init__.py` (empty)
- Create: `src/domains/shopping/schemas.py`
- Create: `src/domains/shopping/model.py`
- Create: `alembic/versions/c3d4e5f6a7b8_add_shopping_items.py` (down_revision=`b2c3d4e5f6a7`)
- Modify: `src/domains/user/model.py` — add `shopping_items` relationship
- Modify: `tests/conftest.py` — import `ShoppingItem`, patch `id` to `Integer()` like Ingredient
- Test: `tests/unit/test_shopping_schemas.py`

**Interfaces:**
- Produces: `ErrorCode.SHOPPING_ITEM_NOT_FOUND`
- Produces: `ShoppingItemNotFoundException(detail="장보기 항목을 찾을 수 없습니다.")`
- Produces: `AddShoppingItemsRequest(names: list[str])` — validator: non-empty list; each name strip, non-empty, ≤45
- Produces: `UpdateShoppingItemRequest(is_checked: bool)`
- Produces: `ShoppingItemResponse(id: int, name: str, is_checked: bool, created_at: datetime)` with `from_attributes=True`
- Produces: `ShoppingItem` table `shopping_items` with UNIQUE `(user_id, name)` name `uq_shopping_items_user_name`

- [ ] **Step 1: Write failing schema tests**

Create `tests/unit/test_shopping_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from domains.shopping.schemas import AddShoppingItemsRequest, UpdateShoppingItemRequest


def test_add_request_strips_names():
    req = AddShoppingItemsRequest(names=["  대파  ", "계란"])
    assert req.names == ["대파", "계란"]


def test_add_request_rejects_empty_list():
    with pytest.raises(ValidationError):
        AddShoppingItemsRequest(names=[])


def test_add_request_rejects_blank_name():
    with pytest.raises(ValidationError):
        AddShoppingItemsRequest(names=["  "])


def test_add_request_rejects_too_long_name():
    with pytest.raises(ValidationError):
        AddShoppingItemsRequest(names=["가" * 46])


def test_update_request_requires_is_checked():
    req = UpdateShoppingItemRequest(is_checked=True)
    assert req.is_checked is True
```

- [ ] **Step 2: Run tests — expect fail (module missing)**

Run: `pytest tests/unit/test_shopping_schemas.py -v`  
Expected: FAIL (import error / module not found)

- [ ] **Step 3: Implement ErrorCode + Exception**

In `codes.py` after ingredient section:

```python
    # ----------------------------------------
    # 5. 장보기 관련
    # ----------------------------------------
    SHOPPING_ITEM_NOT_FOUND = "SHOPPING_ITEM_NOT_FOUND"
```

In `exceptions.py` after `IngredientNotFoundException`:

```python
class ShoppingItemNotFoundException(NotFoundException):
    def __init__(self, detail: str = "장보기 항목을 찾을 수 없습니다."):
        super().__init__(code=ErrorCode.SHOPPING_ITEM_NOT_FOUND, detail=detail)
```

- [ ] **Step 4: Implement schemas**

`src/domains/shopping/schemas.py`:

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AddShoppingItemsRequest(BaseModel):
    names: list[str] = Field(min_length=1)

    @field_validator("names")
    @classmethod
    def validate_names(cls, names: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in names:
            name = raw.strip()
            if not name:
                raise ValueError("식재료 이름은 비어 있을 수 없습니다.")
            if len(name) > 45:
                raise ValueError("식재료 이름은 45자 이하여야 합니다.")
            cleaned.append(name)
        return cleaned


class UpdateShoppingItemRequest(BaseModel):
    is_checked: bool


class ShoppingItemResponse(BaseModel):
    id: int
    name: str
    is_checked: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 5: Implement model + User relationship + migration + conftest**

`src/domains/shopping/model.py` — mirror Ingredient style:

```python
from __future__ import annotations

import uuid6
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class ShoppingItem(Base):
    __tablename__ = "shopping_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid6.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(45), nullable=False)
    is_checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship("User", back_populates="shopping_items")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_shopping_items_user_name"),
    )
```

User model — add:

```python
    shopping_items: Mapped[list["ShoppingItem"]] = relationship(
        "ShoppingItem",
        back_populates="user",
        cascade="all, delete-orphan",
    )
```

Migration `alembic/versions/c3d4e5f6a7b8_add_shopping_items.py`:

- `revision = "c3d4e5f6a7b8"`
- `down_revision = "b2c3d4e5f6a7"`
- Create table `shopping_items` with columns above
- UniqueConstraint `uq_shopping_items_user_name`
- Index on `user_id`
- `downgrade`: drop table

`tests/conftest.py`:

```python
from domains.shopping.model import ShoppingItem  # noqa: F401, E402
# inside db_engine fixture, with Ingredient patch:
ShoppingItem.__table__.c.id.type = Integer()
```

- [ ] **Step 6: Run schema tests — expect PASS**

Run: `pytest tests/unit/test_shopping_schemas.py -v`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/core/exception/codes.py src/core/exception/exceptions.py \
  src/domains/shopping/ src/domains/user/model.py \
  alembic/versions/c3d4e5f6a7b8_add_shopping_items.py tests/conftest.py \
  tests/unit/test_shopping_schemas.py
git commit -m "$(cat <<'EOF'
Feat: 장보기 shopping_items 모델·스키마·마이그레이션 추가

EOF
)"
```

---

### Task 2: Repository + Service (TDD)

**Files:**
- Create: `src/domains/shopping/repository.py`
- Create: `src/domains/shopping/service.py`
- Test: `tests/unit/test_shopping_service.py`

**Interfaces:**
- `ShoppingRepository.__init__(session: AsyncSession)`
- `add_items(items: list[ShoppingItem]) -> list[ShoppingItem]`
- `list_by_user(user_id) -> list[ShoppingItem]` — DB order 자유, 정렬은 service
- `get_existing_names(user_id, names: list[str]) -> set[str]`
- `get_by_id(item_id, user_id) -> ShoppingItem | None`
- `delete_item(item_id, user_id) -> bool`
- `delete_all(user_id) -> bool`
- `ShoppingService.__init__(user, shopping_repo, ingredient_repo)`
- `add_items(AddShoppingItemsRequest) -> list[ShoppingItemResponse]`
- `list_items() -> list[ShoppingItemResponse]` — unchecked first, then `created_at` asc
- `update_item(id, UpdateShoppingItemRequest) -> ShoppingItemResponse`
- `delete_item(id) -> None`
- `delete_all() -> None` — empty면 `ShoppingItemNotFoundException` (ingredient와 대칭)
- `to_ingredient(id) -> AddIngredientResponse` — create Ingredient(name, purchase=today, expiration=None), delete shopping item, return response with `status` via `compute_status`

- [ ] **Step 1: Write failing service tests**

Create `tests/unit/test_shopping_service.py` with AsyncMock repos and fixtures patterned after `tests/unit/test_ingredient_service.py`.

Required tests:

```python
async def test_add_items_skips_existing_and_request_duplicates(...):
    # existing names {"대파"}; request ["대파", "계란", "계란", " 간장"]
    # after schema, names already stripped
    # get_existing_names returns {"대파"}
    # add_items called with only ["계란", "간장"] entities
    # response length 2

async def test_add_items_all_duplicate_returns_empty(...):
    # get_existing_names returns all names; add_items NOT called (or called with [])
    # result == []

async def test_list_items_unchecked_first(...):
    # two items: checked older, unchecked newer → unchecked first

async def test_update_item_sets_checked(...):
async def test_update_item_not_found_raises(...):
async def test_delete_item_not_found_raises(...):
async def test_delete_all_empty_raises(...):

async def test_to_ingredient_creates_ingredient_and_deletes_shopping(...):
    # get_by_id returns ShoppingItem(name="대파", is_checked=False)
    # ingredient_repo.add_ingredient returns Ingredient with id=10, name=대파
    # shopping_repo.delete_item called with (id, user_id)
    # response.ingredient_name == "대파", status == "unknown"

async def test_to_ingredient_not_found_raises(...):
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/unit/test_shopping_service.py -v`  
Expected: FAIL (import / not implemented)

- [ ] **Step 3: Implement repository**

Follow `IngredientRepository` error wrapping (`DatabaseException`).

`list_by_user`: `select(ShoppingItem).where(user_id=...).order_by(created_at.asc())`

`get_existing_names`:

```python
stmt = select(ShoppingItem.name).where(
    ShoppingItem.user_id == user_id,
    ShoppingItem.name.in_(names),
)
```

- [ ] **Step 4: Implement service**

Key logic for `add_items`:

```python
# preserve order, dedupe within request
unique_names = list(dict.fromkeys(request.names))
existing = await self.shopping_repo.get_existing_names(self.user.id, unique_names)
to_create = [n for n in unique_names if n not in existing]
if not to_create:
    return []
items = [
    ShoppingItem(user_id=self.user.id, name=name, is_checked=False)
    for name in to_create
]
saved = await self.shopping_repo.add_items(items)
return [ShoppingItemResponse.model_validate(i) for i in saved]
```

`list_items` sort:

```python
sorted_items = sorted(
    items,
    key=lambda i: (i.is_checked, i.created_at or datetime.min.replace(tzinfo=timezone.utc)),
)
```

`to_ingredient`:

```python
item = await self.shopping_repo.get_by_id(item_id, self.user.id)
if item is None:
    raise ShoppingItemNotFoundException()
ingredient = Ingredient(
    user_id=self.user.id,
    ingredient_name=item.name,
    purchase_date=date.today(),
    expiration_date=None,
)
saved = await self.ingredient_repo.add_ingredient([ingredient])
deleted = await self.shopping_repo.delete_item(item_id, self.user.id)
if not deleted:
    raise ShoppingItemNotFoundException()
# build AddIngredientResponse using compute_status from domains.ingredient.service
```

- [ ] **Step 5: Run service tests — PASS**

Run: `pytest tests/unit/test_shopping_service.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/domains/shopping/repository.py src/domains/shopping/service.py \
  tests/unit/test_shopping_service.py
git commit -m "$(cat <<'EOF'
Feat: 장보기 ShoppingService·Repository 추가

EOF
)"
```

---

### Task 3: API endpoints + DI wiring

**Files:**
- Create: `src/api/v1/endpoints/shopping.py`
- Modify: `src/api/deps.py` — `get_shopping_repo`, `get_shopping_service`
- Modify: `src/api/api.py` — include router
- Test: `tests/api/test_shopping_api.py`

**Routes** (`APIRouter(prefix="/shopping-items", tags=["shopping"])`):

| Method | Path | Status | Handler |
|--------|------|--------|---------|
| POST | `` | 201 | `add_items` |
| GET | `` | 200 | `list_items` |
| PATCH | `/{item_id}` | 200 | `update_item` |
| POST | `/{item_id}/to-ingredient` | 201 | `to_ingredient` → `AddIngredientResponse` |
| DELETE | `` | 204 | `delete_all` (register **before** `/{item_id}`) |
| DELETE | `/{item_id}` | 204 | `delete_item` |

OpenAPI errors: UnAuthorized, BadRequest, ShoppingItemNotFound as appropriate.

`get_shopping_service`:

```python
def get_shopping_service(
    user: User = Depends(get_current_user),
    shopping_repo: ShoppingRepository = Depends(get_shopping_repo),
    ingredient_repo: IngredientRepository = Depends(get_ingredient_repo),
) -> ShoppingService:
    return ShoppingService(
        user=user,
        shopping_repo=shopping_repo,
        ingredient_repo=ingredient_repo,
    )
```

- [ ] **Step 1: Write failing API tests**

`tests/api/test_shopping_api.py` — use `client` + `auth_headers` like ingredient tests:

```python
async def test_add_shopping_requires_auth(client):
    # POST /api/v1/shopping-items → 401

async def test_add_list_dedupe_and_patch(client, auth_headers):
    # POST names=["대파","계란"] → 201, len 2
    # POST names=["대파","당근"] → 201, len 1 (당근만)
    # GET → 3 items
    # PATCH id is_checked true → 200
    # GET → checked item present

async def test_to_ingredient_moves_to_fridge(client, auth_headers):
    # POST shopping ["대파"]
    # POST .../to-ingredient → 201, ingredient_name 대파, status unknown
    # GET shopping → empty
    # GET /api/v1/ingredients → contains 대파

async def test_delete_item_and_delete_all(client, auth_headers):
    # add two, delete one → 204, list len 1
    # delete all → 204, list empty
    # delete all again → 404 SHOPPING_ITEM_NOT_FOUND

async def test_get_other_users_item_not_found(client, auth_headers):
    # PATCH /shopping-items/999999 → 404
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/api/test_shopping_api.py -v`  
Expected: FAIL (404 route / import)

- [ ] **Step 3: Implement endpoint + deps + router include**

Mirror `ingredient.py` style. Import `AddIngredientResponse` for to-ingredient response_model.

- [ ] **Step 4: Run API + unit tests — PASS**

Run: `pytest tests/unit/test_shopping_schemas.py tests/unit/test_shopping_service.py tests/api/test_shopping_api.py -v`  
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/v1/endpoints/shopping.py src/api/deps.py src/api/api.py \
  tests/api/test_shopping_api.py
git commit -m "$(cat <<'EOF'
Feat: 장보기 shopping-items API 엔드포인트 추가

EOF
)"
```

---

### Task 4: Full verification

- [ ] **Step 1: Run full related suite**

Run: `pytest tests/unit/test_shopping_schemas.py tests/unit/test_shopping_service.py tests/api/test_shopping_api.py tests/unit/test_ingredient_service.py tests/api/test_ingredient_api.py -v`  
Expected: all PASS (to-ingredient must not break ingredient)

- [ ] **Step 2: Spec checklist (manual)**

Confirm against `docs/superpowers/specs/2026-07-21-shopping-list-design.md`:

- [ ] GET/POST/PATCH/DELETE/to-ingredient 모두 존재
- [ ] 중복 skip, 전부 중복 시 201 + `[]`
- [ ] UNIQUE `(user_id, name)`
- [ ] to-ingredient → ingredient + shopping 삭제, `is_checked` 무관
- [ ] 수량·출처·다중 리스트 없음

- [ ] **Step 3: Commit only if verification left uncommitted fixes**; otherwise done

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| `shopping_items` table + UNIQUE | Task 1 |
| domains/shopping layout | Task 1–2 |
| POST names / GET / PATCH / DELETE / delete all | Task 3 |
| to-ingredient → AddIngredientResponse | Task 2–3 |
| SHOPPING_ITEM_NOT_FOUND | Task 1 |
| Dedup skip, empty create → 201 [] | Task 2 |
| Unit + API tests | Task 2–3 |
| IngredientRepository (no IngredientService DI) | Task 2 |
| No quantity / source / multi-list | Out of scope — not in tasks |
