# Saved Recipe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI·만개 레시피를 Postgres 스냅샷으로 저장하고, JWT 사용자가 목록·상세·삭제·저장여부 조회할 수 있는 백엔드 API를 만든다.

**Architecture:** `domains/saved_recipe/` (model/repository/service/schemas) + `/api/v1/recipes/saved` 엔드포인트. 저장 시 `AiRecipeService` / `RecipeDetailService`로 원본 상세를 조회해 JSON 스냅샷을 저장. `(user_id, source, source_id)` UNIQUE로 중복 방지.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic, pytest, PostgreSQL JSONB (테스트는 SQLite JSON)

## Global Constraints

- 백엔드만 (앱 UI Out of Scope)
- 스냅샷 immutable; 클라이언트 JSON 직접 제출 없음
- source: `"ai"` | `"mangae"`; 만개 source_id = `{board_name}|{author_name}`
- `GET .../status`는 `{id}` 라우트보다 먼저 등록
- Spec: `docs/superpowers/specs/2026-07-21-saved-recipe-design.md`

## File map

| File | Responsibility |
|------|----------------|
| `src/domains/saved_recipe/schemas.py` | request/response pydantic |
| `src/domains/saved_recipe/model.py` | `SavedRecipe` ORM |
| `src/domains/saved_recipe/repository.py` | CRUD + find by source key |
| `src/domains/saved_recipe/service.py` | save/list/get/delete/status + source parse |
| `src/api/v1/endpoints/saved_recipe.py` | HTTP routes |
| `src/api/deps.py` | `get_saved_recipe_service` |
| `src/api/api.py` | include router |
| `alembic/versions/*_add_saved_recipes.py` | migration |
| `tests/unit/test_saved_recipe_service.py` | service unit tests |
| `tests/api/test_saved_recipe_api.py` | API tests (deps override for detail services) |
| `tests/conftest.py` | import SavedRecipe model |

---

### Task 1: Schemas + Model + Migration

**Files:**
- Create: `src/domains/saved_recipe/schemas.py`
- Create: `src/domains/saved_recipe/model.py`
- Create: `alembic/versions/b2c3d4e5f6a7_add_saved_recipes.py` (down_revision=`a1b2c3d4e5f6`)
- Modify: `tests/conftest.py` — import SavedRecipe
- Test: `tests/unit/test_saved_recipe_schemas.py`

**Interfaces:**
- Produces: `SaveRecipeRequest(source: Literal["ai","mangae"], source_id: str)`
- Produces: `SavedRecipeListItem`, `SavedRecipeDetailResponse`, `SavedRecipeStatusResponse`
- Produces: `SavedRecipe` model with columns per spec; `snapshot` as JSON

- [x] **Step 1:** Schema unit tests (source literal, status shape)
- [x] **Step 2:** Implement schemas + model + migration; register model in conftest
- [x] **Step 3:** `pytest tests/unit/test_saved_recipe_schemas.py -v` PASS

---

### Task 2: Repository + Service (TDD)

**Files:**
- Create: `src/domains/saved_recipe/repository.py`
- Create: `src/domains/saved_recipe/service.py`
- Test: `tests/unit/test_saved_recipe_service.py`

**Interfaces:**
- Repo: `add`, `list_by_user`, `get_by_id`, `find_by_source`, `delete`
- Service `__init__(user, repo, ai_recipe_service, recipe_detail_service)`
- Service: `save(request)`, `list_saved()`, `get(id)`, `delete(id)`, `status(source, source_id)`
- `parse_mangae_source_id(source_id) -> tuple[board, author]` — BadRequest if invalid
- Duplicate → `ConflictException(ErrorCode.CONFLICT, ...)`
- Missing saved → `NotFoundException`

- [x] **Step 1:** Failing service tests (save ai/mangae, duplicate, bad source_id, get/delete/status)
- [x] **Step 2:** Implement repository + service
- [x] **Step 3:** `pytest tests/unit/test_saved_recipe_service.py -v` PASS

---

### Task 3: API endpoints + wiring

**Files:**
- Create: `src/api/v1/endpoints/saved_recipe.py`
- Modify: `src/api/deps.py`, `src/api/api.py`
- Test: `tests/api/test_saved_recipe_api.py`

**Routes:** prefix `/recipes/saved` under existing recipes tag or `saved-recipes`
- POST `` → 201
- GET `` → 200 list
- GET `/status` before `/{id}`
- GET `/{id}` → 200
- DELETE `/{id}` → 204

API tests override `get_ai_recipe_service` / `get_recipe_detail_service` with mocks returning fixed details.

- [x] **Step 1:** Failing API tests
- [x] **Step 2:** Wire deps + router
- [x] **Step 3:** `pytest tests/unit/test_saved_recipe*.py tests/api/test_saved_recipe_api.py -v` PASS

---

### Task 4: Verification

- [x] Full related pytest green
- [x] Spec success criteria covered
