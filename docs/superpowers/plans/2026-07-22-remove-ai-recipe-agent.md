# AI 에이전트 레시피 제거 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LLM AI 에이전트 레시피(`/recipes/ai/*`, `domains/ai_recipe`)를 하드 삭제하고 RAG·만개 크롤·mangae saved만 남긴다. DB의 `source=ai` 저장 행은 Alembic으로 삭제한다.

**Architecture:** AI 도메인·라우트·설정·quota 예외를 제거하고, ingredient/group의 list-cache invalidate와 saved의 AI 분기를 끊는다. 마이그레이션은 `DELETE FROM saved_recipes WHERE source = 'ai'`만 수행한다.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Redis(기존), pytest

## Global Constraints

- `/recipes/ai/*` 및 `domains/ai_recipe/` **완전 제거**
- RAG `GET /recommendations`, 크롤 `GET /detail` **유지**
- Saved: `source`는 **`mangae`만**; AI 저장 요청 → 422
- Alembic: `DELETE FROM saved_recipes WHERE source = 'ai'`; downgrade **no-op**
- `OPENAI_API_KEY` **유지** (RAG 임베딩)
- Redis AI 키 강제 flush **없음**
- 앱(프론트) Out of Scope
- 커밋은 유저 요청 시에만 (스텝에 있어도 요청 전 skip 가능)

---

## File Structure

| 동작 | 경로 |
|------|------|
| Delete | `src/domains/ai_recipe/` 전체 |
| Delete | `tests/api/test_ai_recipe_api.py`, `tests/unit/test_ai_recipe_*.py`, `tests/unit/test_ai_quota_exception.py` |
| Delete | AI 전용 docs (아래 Task 5 목록) |
| Modify | `src/api/v1/endpoints/rag.py`, `src/api/deps.py` |
| Modify | `src/domains/ingredient/service.py`, `src/domains/group/service.py` |
| Modify | `src/domains/saved_recipe/service.py`, `schemas.py` |
| Modify | `src/core/config.py`, `codes.py`, `exceptions.py` |
| Modify | saved/ingredient/group 테스트 |
| Create | `alembic/versions/*_delete_ai_saved_recipes.py` |

---

### Task 1: Saved mangae-only + drop AI dependency (TDD)

**Files:**
- Modify: `src/domains/saved_recipe/schemas.py`
- Modify: `src/domains/saved_recipe/service.py`
- Modify: `src/api/deps.py` — `get_saved_recipe_service`에서 `ai_recipe_service` 제거 (AI factory는 Task 3에서 삭제)
- Modify: `tests/unit/test_saved_recipe_schemas.py`
- Modify: `tests/unit/test_saved_recipe_service.py`
- Modify: `tests/api/test_saved_recipe_api.py`

**Interfaces:**
- Produces: `SaveRecipeRequest.source: Literal["mangae"]`
- Produces: `SavedRecipeService.__init__(user, repo, recipe_detail_service)` — **no** `ai_recipe_service`
- Produces: `save()`는 mangae 경로만 (기존 mangae 스냅샷 로직)
- Consumes: `RecipeDetailService.get_detail`

- [ ] **Step 1: Update failing tests first**

`test_saved_recipe_schemas.py`: `source="ai"`는 `ValidationError` 기대; mangae만 성공.

`test_saved_recipe_service.py`:
- 삭제: `test_save_ai_recipe` 및 AI mock fixture 의존
- `SavedRecipeService(...)` 생성에서 `ai_recipe_service=` 제거
- status 테스트에 `source="ai"`가 있으면 mangae만 남기거나 422 기대로 변경

`test_saved_recipe_api.py`:
- AI save 플로우·`get_ai_recipe_service` override 제거
- mangae save/list/detail/delete만 유지

- [ ] **Step 2: Run saved tests — expect FAIL** (constructor/schema mismatch)

Run: `uv run pytest tests/unit/test_saved_recipe_*.py tests/api/test_saved_recipe_api.py -v`

- [ ] **Step 3: Implement schemas + service + deps wiring**

```python
# schemas.py
class SaveRecipeRequest(BaseModel):
    source: Literal["mangae"]
    source_id: str = Field(min_length=1)
```

```python
# service.py — save() mangae only
async def save(self, request: SaveRecipeRequest) -> SavedRecipeDetailResponse:
    parse_mangae_source_id(request.source_id)
    existing = await self.repo.find_by_source(...)
    if existing is not None:
        raise ConflictException(...)
    board_name, author_name = parse_mangae_source_id(request.source_id)
    detail = await self.recipe_detail_service.get_detail(board_name, author_name)
    # snapshot as today for mangae
    ...
```

`get_status` / 검증 메시지: `"source는 mangae 여야 합니다."` (ai 제거).

`deps.get_saved_recipe_service`: `ai_recipe_service` 인자 제거. (`get_ai_recipe_service` 함수는 아직 다른 곳에서 쓰이면 Task 3까지 남겨도 됨 — saved에서만 끊기.)

- [ ] **Step 4: Run saved tests — PASS**

Run: `uv run pytest tests/unit/test_saved_recipe_*.py tests/api/test_saved_recipe_api.py -v`

- [ ] **Step 5: Commit** (유저 요청 시)

```bash
git add src/domains/saved_recipe src/api/deps.py tests/unit/test_saved_recipe_*.py tests/api/test_saved_recipe_api.py
git commit -m "$(cat <<'EOF'
refactor: restrict saved recipes to mangae source only

EOF
)"
```

---

### Task 2: Strip AI list-cache from ingredient + group (TDD)

**Files:**
- Modify: `src/domains/ingredient/service.py` — remove `AiRecipeCache`, `_schedule_ai_recipe_list_invalidation`, all call sites
- Modify: `src/domains/group/service.py` — same pattern (`_AI_RECIPE_INVALIDATION_PENDING`, `_schedule_ai_recipe_list_invalidation`)
- Modify: `src/api/deps.py` — `get_ingredient_service` / `get_group_service`에서 `list_cache=AiRecipeCache(...)` 제거
- Modify: `tests/unit/test_ingredient_service.py` — invalidate_list assertions / list_cache fixture 제거 또는 서비스가 cache 없이 동작하도록 fixtures 정리
- Modify: `tests/unit/test_group_service.py` — `test_*_invalidates_ai_list_cache*` 삭제 또는 assertion 제거; `list_cache` mock 주입 제거

**Interfaces:**
- Produces: `IngredientService(user, ingredient_repo)` — no `list_cache`
- Produces: `GroupService(..., notification_repo, ...)` — no `list_cache` kwarg
- Consumes: 기존 CRUD 동작 유지

- [ ] **Step 1: Rewrite tests without AI cache**

Ingredient: remove `list_cache.invalidate_list` expects; construct service without cache.  
Group: delete AI invalidation-focused tests (약 7개); keep functional group tests.

- [ ] **Step 2: Run — expect FAIL** if service still requires list_cache

Run: `uv run pytest tests/unit/test_ingredient_service.py tests/unit/test_group_service.py -v`

- [ ] **Step 3: Remove invalidation code + deps wiring**

Delete methods/constants related to AI invalidation. After commit hooks / `session.info` listeners that only existed for AI cache — remove entirely.

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit** (유저 요청 시)

```bash
git commit -m "$(cat <<'EOF'
refactor: remove AI recipe list cache invalidation from ingredient and group

EOF
)"
```

---

### Task 3: Delete AI domain, routes, config, quota exception

**Files:**
- Delete: `src/domains/ai_recipe/` (all files)
- Delete: `tests/api/test_ai_recipe_api.py`
- Delete: `tests/unit/test_ai_recipe_agent.py`, `test_ai_recipe_service.py`, `test_ai_recipe_cache.py`, `test_ai_recipe_quota.py`, `test_ai_recipe_schemas.py`, `test_ai_recipe_partial_json.py`, `test_ai_quota_exception.py`
- Modify: `src/api/v1/endpoints/rag.py` — remove `/ai/*` endpoints and AI imports (`TooManyRequestsException` if unused)
- Modify: `src/api/deps.py` — remove `get_ai_recipe_service` and all `ai_recipe` / `AiRecipe*` imports
- Modify: `src/core/config.py` — remove `AI_RECIPE_MODEL`, `AI_QUOTA_DAILY_LIMIT`
- Modify: `src/core/exception/codes.py` — remove `AI_QUOTA_EXCEEDED`
- Modify: `src/core/exception/exceptions.py` — remove `TooManyRequestsException` (AI-only)

**Interfaces:**
- Produces: rag router with only `/recommendations` and `/detail`
- Produces: no import path `domains.ai_recipe`

- [ ] **Step 1: Delete AI test files** (so suite cannot pass while domain remains partially)

- [ ] **Step 2: Delete domain + strip routes/deps/config/exceptions**

Keep in `rag.py`:
- `GET /recommendations`
- `GET /detail`

Remove entirely:
- `ai_recommend_recipes`, `ai_recipe_detail`, `ai_recipe_detail_stream`, `_sse` helper if only used by stream

Grep to confirm clean:
```bash
rg -n "ai_recipe|AiRecipe|AI_RECIPE|AI_QUOTA|TooManyRequestsException|get_ai_recipe" src tests
```
Expected: no matches (or only historical docs until Task 5).

- [ ] **Step 3: Run regression**

Run: `uv run pytest tests/api/test_rag_api.py tests/api/test_recipe_detail_api.py tests/api/test_saved_recipe_api.py tests/unit/test_rag_*.py tests/unit/test_recipe_detail_*.py tests/unit/test_saved_recipe_*.py tests/unit/test_ingredient_service.py tests/unit/test_group_service.py -q`

Expected: PASS

Also: `uv run pytest -q` full suite if feasible.

- [ ] **Step 4: Commit** (유저 요청 시)

```bash
git commit -m "$(cat <<'EOF'
feat: remove AI recipe agent domain and endpoints

EOF
)"
```

---

### Task 4: Alembic delete `source=ai` saved rows

**Files:**
- Create: `alembic/versions/i9j0k1l2m3n4_delete_ai_saved_recipes.py` (revision id may differ; **must** set `down_revision = "h8i9j0k1l2m3"`)

**Interfaces:**
- Produces: upgrade deletes AI rows; downgrade no-op

- [ ] **Step 1: Write migration**

```python
"""delete_ai_saved_recipes

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
"""
from typing import Sequence, Union
from alembic import op

revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, Sequence[str], None] = "h8i9j0k1l2m3"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("DELETE FROM saved_recipes WHERE source = 'ai'")

def downgrade() -> None:
    # AI snapshots are not recoverable
    pass
```

If head is not `h8i9j0k1l2m3` at implement time, run `alembic heads` and chain correctly.

- [ ] **Step 2: Verify revision graph**

Run: `uv run alembic heads`  
Expected: single head including new revision

- [ ] **Step 3: Commit** (유저 요청 시)

```bash
git commit -m "$(cat <<'EOF'
chore: migrate delete saved recipes with source=ai

EOF
)"
```

---

### Task 5: Docs cleanup + verification

**Files (delete AI-only docs):**
- `docs/superpowers/specs/2026-07-21-ai-recipe-agent-design.md`
- `docs/superpowers/plans/2026-07-21-ai-recipe-agent.md`
- `docs/superpowers/specs/2026-07-21-ai-recipe-detail-stream-design.md`
- `docs/superpowers/plans/2026-07-21-ai-recipe-detail-stream.md`
- `docs/superpowers/specs/2026-07-21-ai-recipe-daily-quota-design.md`
- `docs/superpowers/plans/2026-07-21-ai-recipe-daily-quota.md`
- `docs/superpowers/specs/2026-07-21-ai-recipe-speed-refresh-design.md`
- `docs/superpowers/plans/2026-07-21-ai-recipe-speed-refresh.md`

**Mixed docs (optional light edit, do not block):**  
`core-loop-deepening*`, `group-ai-recommendations*` — AI 섹션이 있으면 “removed” 한 줄 또는 파일 유지. YAGNI: **삭제하지 말고** Task 5에서 grep으로 AI 라우트가 코드에 없는지만 확인.

- [ ] **Step 1: Delete AI-only doc files listed above**

- [ ] **Step 2: Final greps**

```bash
rg -n "domains\.ai_recipe|/recipes/ai/|AI_RECIPE_MODEL|AI_QUOTA_DAILY_LIMIT|get_ai_recipe_service" src tests
```
Expected: no matches

- [ ] **Step 3: Full pytest**

Run: `uv run pytest -q`  
Expected: PASS

- [ ] **Step 4: Spec checklist**

| Criteria | Evidence |
|----------|----------|
| no `/ai/*` or `ai_recipe` domain | grep |
| RAG + detail + mangae saved work | pytest |
| migration deletes ai rows | migration file present |
| config keys gone | `config.py` |
| AI tests gone | no `test_ai_recipe*` |

- [ ] **Step 5: Commit** (유저 요청 시) docs + any leftovers

---

## Spec Self-Review

| Spec 요구 | Task |
|-----------|------|
| Hard-delete AI domain/routes | Task 3 |
| Saved mangae-only + 422 for ai | Task 1 |
| DELETE source=ai | Task 4 |
| Strip ingredient/group invalidate | Task 2 |
| Config AI_* removed | Task 3 |
| OPENAI_API_KEY kept | Task 3 (do not touch) |
| RAG/detail kept | Task 3 |
| AI tests/docs removed | Task 3, 5 |
| App out of scope | — |

Placeholder scan: none.  
Type consistency: `Literal["mangae"]`, `SavedRecipeService` without AI service — Tasks 1–3 aligned.
