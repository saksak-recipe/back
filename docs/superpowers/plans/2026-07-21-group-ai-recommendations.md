# Group AI · RAG Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 RAG·AI 레시피 API에 `scope=personal|group`을 추가해, 그룹 공유 냉장고만으로 추천·상세가 동작하게 한다.

**Architecture:** `IngredientScopeLoader`가 personal/group 재료 로드와 멤버십 검증을 담당하고, RAG·AI 서비스가 이를 사용한다. AI 목록 캐시는 `ai_recipe_list:{user_id}` / `ai_recipe_list:group:{group_id}`로 분리하며, 그룹 재료 CRUD 시 그룹 목록 캐시를 무효화한다.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Redis (`AiRecipeCache`), Pydantic, pytest

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-21-group-ai-recommendations-design.md`
- 재료 기준: **그룹 공유 냉장고만** (개인과 합산하지 않음)
- API: 기존 경로 + `scope` 쿼리 (기본 `personal`)
- 대상: RAG 목록 + AI 목록 + AI 상세
- 미가입 + `scope=group` → `404 GROUP_NOT_FOUND` (메시지: `가입된 그룹을 찾을 수 없습니다.`)
- 빈 재료 → `200` + 빈 목록
- 저장 레시피·만개 상세 크롤·그룹 전용 새 경로 **변경 없음**
- 커밋 메시지 스타일: `Feat:` / `Fix:` / `Test:` / `Docs:` (기존 저장소와 동일)

## File map

| File | Responsibility |
|------|----------------|
| `src/domains/ingredient/scope.py` | `RecipeScope`, `ScopedIngredients`, `IngredientScopeLoader` |
| `src/domains/ai_recipe/cache.py` | 목록 키에 scope 반영 |
| `src/domains/rag/service.py` | `scope`로 재료 로드 |
| `src/domains/ai_recipe/service.py` | `scope`로 재료·캐시 owner 사용 |
| `src/api/v1/endpoints/rag.py` | `scope` 쿼리 파라미터 |
| `src/api/deps.py` | loader / group_repo / list_cache 주입 |
| `src/domains/group/service.py` | 그룹 재료 변경 시 목록 캐시 무효화 |
| `src/domains/ingredient/service.py` | 캐시 API 시그니처 변경에 맞춤 (personal 기본값) |
| `tests/unit/test_ingredient_scope.py` | 스코프 로더 단위 테스트 |
| `tests/unit/test_ai_recipe_cache.py` | 그룹 키 테스트 |
| `tests/unit/test_rag_service.py` | group scope |
| `tests/unit/test_ai_recipe_service.py` | group scope |
| `tests/unit/test_group_service.py` | 그룹 캐시 무효화 |
| `tests/unit/test_ingredient_service.py` | invalidate 시그니처 회귀 |
| `tests/api/test_rag_api.py` | scope 쿼리 |
| `tests/api/test_ai_recipe_api.py` | scope 쿼리 |

---

### Task 1: IngredientScopeLoader

**Files:**
- Create: `src/domains/ingredient/scope.py`
- Create: `tests/unit/test_ingredient_scope.py`

**Interfaces:**
- Produces:
  - `class RecipeScope(StrEnum): personal = "personal"; group = "group"`
  - `@dataclass(frozen=True) class ScopedIngredients: ingredients: list[Ingredient]; scope: RecipeScope; cache_owner_id: uuid.UUID`
  - `class IngredientScopeLoader` with `__init__(user, ingredient_repo, group_repo)` and `async def load(self, scope: RecipeScope) -> ScopedIngredients`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_ingredient_scope.py
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.exception.codes import ErrorCode
from core.exception.exceptions import NotFoundException
from domains.ingredient.scope import IngredientScopeLoader, RecipeScope


@pytest.fixture
def user():
    u = MagicMock()
    u.id = uuid.uuid4()
    return u


async def test_load_personal_uses_personal_ingredients(user):
    item = MagicMock()
    ingredient_repo = AsyncMock()
    ingredient_repo.get_ingredients.return_value = [item]
    group_repo = AsyncMock()
    loader = IngredientScopeLoader(user, ingredient_repo, group_repo)

    result = await loader.load(RecipeScope.personal)

    assert result.ingredients == [item]
    assert result.scope is RecipeScope.personal
    assert result.cache_owner_id == user.id
    ingredient_repo.get_ingredients.assert_awaited_once_with(user.id)
    group_repo.get_membership.assert_not_awaited()


async def test_load_group_uses_group_ingredients(user):
    group_id = uuid.uuid4()
    membership = MagicMock(group_id=group_id)
    item = MagicMock()
    ingredient_repo = AsyncMock()
    ingredient_repo.list_by_group.return_value = [item]
    group_repo = AsyncMock()
    group_repo.get_membership.return_value = membership
    loader = IngredientScopeLoader(user, ingredient_repo, group_repo)

    result = await loader.load(RecipeScope.group)

    assert result.ingredients == [item]
    assert result.scope is RecipeScope.group
    assert result.cache_owner_id == group_id
    ingredient_repo.list_by_group.assert_awaited_once_with(group_id)
    ingredient_repo.get_ingredients.assert_not_awaited()


async def test_load_group_without_membership_raises_not_found(user):
    ingredient_repo = AsyncMock()
    group_repo = AsyncMock()
    group_repo.get_membership.return_value = None
    loader = IngredientScopeLoader(user, ingredient_repo, group_repo)

    with pytest.raises(NotFoundException) as exc_info:
        await loader.load(RecipeScope.group)

    assert exc_info.value.code == ErrorCode.GROUP_NOT_FOUND
    assert "가입된 그룹" in exc_info.value.detail
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/unit/test_ingredient_scope.py -v`  
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `src/domains/ingredient/scope.py`**

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from core.exception.codes import ErrorCode
from core.exception.exceptions import NotFoundException
from domains.group.repository import GroupRepository
from domains.ingredient.model import Ingredient
from domains.ingredient.repository import IngredientRepository
from domains.user.model import User


class RecipeScope(StrEnum):
    personal = "personal"
    group = "group"


@dataclass(frozen=True)
class ScopedIngredients:
    ingredients: list[Ingredient]
    scope: RecipeScope
    cache_owner_id: uuid.UUID


class IngredientScopeLoader:
    def __init__(
        self,
        user: User,
        ingredient_repo: IngredientRepository,
        group_repo: GroupRepository,
    ) -> None:
        self.user = user
        self.ingredient_repo = ingredient_repo
        self.group_repo = group_repo

    async def load(self, scope: RecipeScope) -> ScopedIngredients:
        if scope is RecipeScope.personal:
            ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
            return ScopedIngredients(
                ingredients=ingredients,
                scope=RecipeScope.personal,
                cache_owner_id=self.user.id,
            )

        membership = await self.group_repo.get_membership(self.user.id)
        if membership is None:
            raise NotFoundException(
                code=ErrorCode.GROUP_NOT_FOUND,
                detail="가입된 그룹을 찾을 수 없습니다.",
            )

        ingredients = await self.ingredient_repo.list_by_group(membership.group_id)
        return ScopedIngredients(
            ingredients=ingredients,
            scope=RecipeScope.group,
            cache_owner_id=membership.group_id,
        )
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/unit/test_ingredient_scope.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domains/ingredient/scope.py tests/unit/test_ingredient_scope.py
git commit -m "$(cat <<'EOF'
Feat: 레시피 추천용 IngredientScopeLoader 추가

EOF
)"
```

---

### Task 2: AiRecipeCache scope-aware list keys

**Files:**
- Modify: `src/domains/ai_recipe/cache.py`
- Modify: `tests/unit/test_ai_recipe_cache.py`
- Modify: `tests/unit/test_ingredient_service.py` (invalidate assert가 keyword `scope`를 쓰게 되면 맞춤 — 기본값 personal이면 `assert_awaited_once_with(user.id)` 유지 가능)

**Interfaces:**
- Consumes: `RecipeScope` from `domains.ingredient.scope`
- Produces updated:
  - `list_key(owner_id: uuid.UUID, *, scope: RecipeScope = RecipeScope.personal) -> str`
  - `get_list(owner_id, *, scope=...)`
  - `set_list(owner_id, record, *, scope=...)`
  - `invalidate_list(owner_id, *, scope=...)`
- Key format:
  - personal → `ai_recipe_list:{owner_id}`
  - group → `ai_recipe_list:group:{owner_id}`

- [ ] **Step 1: Write failing cache tests for group key**

기존 `test_list_cache_roundtrip_and_invalidation`의 `user_id=1`을 `uuid.UUID`로 바꾸고, 아래 테스트 추가:

```python
import uuid

from domains.ingredient.scope import RecipeScope

async def test_group_list_key_and_isolation():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = AiRecipeCache(redis, list_ttl_seconds=1800)
    user_id = uuid.uuid4()
    group_id = uuid.uuid4()
    record = AiRecipeListCacheRecord(
        ingredients_hash="abc",
        ingredients_used=["계란"],
        recipes=[],
    )

    await cache.set_list(group_id, record, scope=RecipeScope.group)
    assert await cache.get_list(group_id, scope=RecipeScope.group) == record
    assert await cache.get_list(group_id, scope=RecipeScope.personal) is None
    assert await cache.get_list(user_id, scope=RecipeScope.personal) is None
    assert cache.list_key(group_id, scope=RecipeScope.group) == (
        f"ai_recipe_list:group:{group_id}"
    )

    await cache.invalidate_list(group_id, scope=RecipeScope.group)
    assert await cache.get_list(group_id, scope=RecipeScope.group) is None
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/unit/test_ai_recipe_cache.py -v`  
Expected: FAIL (signature / scope 미지원)

- [ ] **Step 3: Update `AiRecipeCache`**

```python
import uuid
from domains.ingredient.scope import RecipeScope

# list_key / get_list / set_list / invalidate_list 시그니처를 아래로 통일
@staticmethod
def list_key(
    owner_id: uuid.UUID,
    *,
    scope: RecipeScope = RecipeScope.personal,
) -> str:
    if scope is RecipeScope.group:
        return f"ai_recipe_list:group:{owner_id}"
    return f"ai_recipe_list:{owner_id}"

async def get_list(
    self,
    owner_id: uuid.UUID,
    *,
    scope: RecipeScope = RecipeScope.personal,
) -> AiRecipeListCacheRecord | None:
    ...
    raw = await self._redis.get(self.list_key(owner_id, scope=scope))

async def set_list(
    self,
    owner_id: uuid.UUID,
    record: AiRecipeListCacheRecord,
    *,
    scope: RecipeScope = RecipeScope.personal,
) -> None:
    ...
    await self._redis.set(
        self.list_key(owner_id, scope=scope),
        record.model_dump_json(),
        ex=self._list_ttl,
    )

async def invalidate_list(
    self,
    owner_id: uuid.UUID,
    *,
    scope: RecipeScope = RecipeScope.personal,
) -> None:
    ...
    await self._redis.delete(self.list_key(owner_id, scope=scope))
```

기존 personal 호출(`invalidate_list(user.id)` 등)은 기본값으로 동작해야 한다.

- [ ] **Step 4: Fix unit cache test that used `user_id=1`**

`set_list`/`get_list`/`invalidate_list`/`list_key`에 `uuid.uuid4()` 사용.

- [ ] **Step 5: Run related tests**

Run: `pytest tests/unit/test_ai_recipe_cache.py tests/unit/test_ingredient_service.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/domains/ai_recipe/cache.py tests/unit/test_ai_recipe_cache.py tests/unit/test_ingredient_service.py
git commit -m "$(cat <<'EOF'
Feat: AI 레시피 목록 캐시에 group 스코프 키 지원

EOF
)"
```

---

### Task 3: RagService + endpoint `scope`

**Files:**
- Modify: `src/domains/rag/service.py`
- Modify: `src/api/v1/endpoints/rag.py` (`recommend_recipes`만)
- Modify: `src/api/deps.py` (`get_rag_service`)
- Modify: `tests/unit/test_rag_service.py`
- Modify: `tests/api/test_rag_api.py`

**Interfaces:**
- Consumes: `IngredientScopeLoader`, `RecipeScope`
- Produces: `RagService.recommend_recipes(scope: RecipeScope = RecipeScope.personal)`
- `RagService.__init__(..., scope_loader: IngredientScopeLoader)` — `ingredient_repo` 직접 호출 제거(로더로 대체). 기존 테스트 fixture는 `scope_loader` mock 또는 로더+repo로 재구성.

- [ ] **Step 1: Add failing unit tests for group scope**

```python
# tests/unit/test_rag_service.py — 추가/수정
from domains.ingredient.scope import RecipeScope, ScopedIngredients

async def test_recommend_group_scope_uses_scoped_ingredients(
    user, retriever
):
    group_id = uuid6.uuid7()
    item = Ingredient(
        id=1,
        user_id=user.id,
        group_id=group_id,
        ingredient_name="양파",
        purchase_date=date.today(),
    )
    scope_loader = AsyncMock()
    scope_loader.load.return_value = ScopedIngredients(
        ingredients=[item],
        scope=RecipeScope.group,
        cache_owner_id=group_id,
    )
    service = RagService(user=user, scope_loader=scope_loader, retriever=retriever)
    retriever.search.return_value = []

    result = await service.recommend_recipes(scope=RecipeScope.group)

    scope_loader.load.assert_awaited_once_with(RecipeScope.group)
    assert result.ingredients_used == ["양파"]


async def test_recommend_defaults_to_personal(user, retriever):
    scope_loader = AsyncMock()
    scope_loader.load.return_value = ScopedIngredients(
        ingredients=[],
        scope=RecipeScope.personal,
        cache_owner_id=user.id,
    )
    service = RagService(user=user, scope_loader=scope_loader, retriever=retriever)

    await service.recommend_recipes()

    scope_loader.load.assert_awaited_once_with(RecipeScope.personal)
```

기존 `ingredient_repo.get_ingredients` 기반 테스트는 `scope_loader.load`가 동일 재료를 반환하도록 전부한다.

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/unit/test_rag_service.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement RagService**

```python
from domains.ingredient.scope import IngredientScopeLoader, RecipeScope

class RagService:
    def __init__(
        self,
        user: User,
        scope_loader: IngredientScopeLoader,
        retriever: RecipeRetriever,
    ):
        self.user = user
        self.scope_loader = scope_loader
        self.retriever = retriever

    async def recommend_recipes(
        self, scope: RecipeScope = RecipeScope.personal
    ) -> RecipeRecommendationResponse:
        scoped = await self.scope_loader.load(scope)
        ingredients = scoped.ingredients
        names = [item.ingredient_name for item in ingredients]
        if not names:
            return RecipeRecommendationResponse(ingredients_used=[], recipes=[])
        # ... 이하 기존 로직 동일 (urgent / search / map)
```

- [ ] **Step 4: Wire deps + endpoint**

```python
# deps.py
from domains.group.repository import GroupRepository
from domains.ingredient.scope import IngredientScopeLoader

def get_ingredient_scope_loader(
    user: User = Depends(get_current_user),
    ingredient_repo: IngredientRepository = Depends(get_ingredient_repo),
    session: AsyncSession = Depends(get_db),
) -> IngredientScopeLoader:
    return IngredientScopeLoader(
        user=user,
        ingredient_repo=ingredient_repo,
        group_repo=GroupRepository(session),
    )

def get_rag_service(
    user: User = Depends(get_current_user),
    scope_loader: IngredientScopeLoader = Depends(get_ingredient_scope_loader),
    retriever: RecipeRetriever = Depends(get_rag_retriever),
) -> RagService:
    return RagService(user=user, scope_loader=scope_loader, retriever=retriever)
```

```python
# endpoints/rag.py
from domains.ingredient.scope import RecipeScope

async def recommend_recipes(
    scope: RecipeScope = RecipeScope.personal,
    service: RagService = Depends(get_rag_service),
) -> RecipeRecommendationResponse:
    return await service.recommend_recipes(scope=scope)
```

- [ ] **Step 5: API test — invalid scope 422, default personal**

```python
async def test_recommendations_invalid_scope_422(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.get(
        "/api/v1/recipes/recommendations",
        headers=auth_headers,
        params={"scope": "workspace"},
    )
    assert response.status_code == 422


async def test_recommendations_group_without_membership_404(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.get(
        "/api/v1/recipes/recommendations",
        headers=auth_headers,
        params={"scope": "group"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.GROUP_NOT_FOUND
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/test_rag_service.py tests/api/test_rag_api.py -v`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/domains/rag/service.py src/api/v1/endpoints/rag.py src/api/deps.py \
  tests/unit/test_rag_service.py tests/api/test_rag_api.py
git commit -m "$(cat <<'EOF'
Feat: RAG 추천에 personal|group scope 지원

EOF
)"
```

---

### Task 4: AiRecipeService + endpoint `scope`

**Files:**
- Modify: `src/domains/ai_recipe/service.py`
- Modify: `src/api/v1/endpoints/rag.py` (`ai_recommend_recipes`, `ai_recipe_detail`)
- Modify: `src/api/deps.py` (`get_ai_recipe_service`)
- Modify: `tests/unit/test_ai_recipe_service.py`
- Modify: `tests/api/test_ai_recipe_api.py`

**Interfaces:**
- Consumes: `IngredientScopeLoader`, `RecipeScope`
- Produces:
  - `recommend(refresh: bool = False, scope: RecipeScope = RecipeScope.personal)`
  - `get_detail(recipe_id: str, scope: RecipeScope = RecipeScope.personal)`
- Cache calls: `get_list/set_list(cache_owner_id, ..., scope=scoped.scope)`

- [ ] **Step 1: Add failing unit tests**

```python
from domains.ingredient.scope import RecipeScope, ScopedIngredients

async def test_recommend_group_scope_uses_group_cache_owner(user):
    group_id = uuid.uuid4()
    item = MagicMock(ingredient_name="계란", expiration_date=None)
    scope_loader = AsyncMock()
    scope_loader.load.return_value = ScopedIngredients(
        ingredients=[item],
        scope=RecipeScope.group,
        cache_owner_id=group_id,
    )
    cache = AsyncMock()
    cache.get_list.return_value = None
    agent = MagicMock()
    agent.run_list.return_value = [
        AiRecipeCandidate(recipe_name=f"요리{i}", recipe_ingredients=["계란"])
        for i in range(5)
    ]
    service = AiRecipeService(
        user=user, scope_loader=scope_loader, agent=agent, cache=cache
    )

    await service.recommend(scope=RecipeScope.group)

    scope_loader.load.assert_awaited_once_with(RecipeScope.group)
    cache.get_list.assert_awaited_once_with(group_id, scope=RecipeScope.group)
    cache.set_list.assert_awaited_once()
    assert cache.set_list.await_args.args[0] == group_id
    assert cache.set_list.await_args.kwargs["scope"] is RecipeScope.group


async def test_get_detail_group_scope_loads_group_ingredients(user):
    group_id = uuid.uuid4()
    record = AiRecipeCacheRecord(
        recipe_id="rid",
        recipe_name="계란찜",
        recipe_ingredients=["계란"],
        owned_ingredients=["계란"],
        missing_ingredients=[],
    )
    scope_loader = AsyncMock()
    scope_loader.load.return_value = ScopedIngredients(
        ingredients=[MagicMock(ingredient_name="계란", expiration_date=None)],
        scope=RecipeScope.group,
        cache_owner_id=group_id,
    )
    cache = AsyncMock()
    cache.get.return_value = record
    agent = MagicMock()
    agent.run_detail.return_value = {
        "ingredients": [],
        "steps": [],
        "tips": [],
    }
    service = AiRecipeService(
        user=user, scope_loader=scope_loader, agent=agent, cache=cache
    )

    await service.get_detail("rid", scope=RecipeScope.group)

    scope_loader.load.assert_awaited_once_with(RecipeScope.group)
```

기존 테스트의 `ingredient_repo`를 `scope_loader`로 교체하고, `cache.get_list`/`set_list` assert에 `scope=RecipeScope.personal`을 반영한다.

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/unit/test_ai_recipe_service.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement AiRecipeService**

```python
class AiRecipeService:
    def __init__(
        self,
        user: User,
        scope_loader: IngredientScopeLoader,
        agent: AiRecipeAgent,
        cache: AiRecipeCache,
    ) -> None:
        self.user = user
        self.scope_loader = scope_loader
        self.agent = agent
        self.cache = cache

    async def recommend(
        self,
        refresh: bool = False,
        scope: RecipeScope = RecipeScope.personal,
    ) -> AiRecipeRecommendationResponse:
        scoped = await self.scope_loader.load(scope)
        ingredients = scoped.ingredients
        names = [item.ingredient_name for item in ingredients]
        if not names:
            return AiRecipeRecommendationResponse(ingredients_used=[], recipes=[])

        digest = ingredients_hash(names)
        if not refresh:
            cached = await self.cache.get_list(
                scoped.cache_owner_id, scope=scoped.scope
            )
            if cached is not None and cached.ingredients_hash == digest:
                return AiRecipeRecommendationResponse(
                    ingredients_used=cached.ingredients_used,
                    recipes=cached.recipes,
                )

        candidates = await self._generate_list(names, urgent_names(ingredients))
        # ... 기존 recipe 생성 루프 동일 ...
        await self.cache.set_list(
            scoped.cache_owner_id,
            AiRecipeListCacheRecord(
                ingredients_hash=digest,
                ingredients_used=names,
                recipes=response.recipes,
            ),
            scope=scoped.scope,
        )
        return response

    async def get_detail(
        self,
        recipe_id: str,
        scope: RecipeScope = RecipeScope.personal,
    ) -> AiRecipeDetailResponse:
        record = await self.cache.get(recipe_id)
        if record is None:
            raise NotFoundException(detail="AI 레시피를 찾지 못했습니다.")
        if record.has_detail():
            return self._detail_response(record, cached=True)

        scoped = await self.scope_loader.load(scope)
        names = [item.ingredient_name for item in scoped.ingredients]
        # ... 기존 run_detail / set 동일 ...
```

- [ ] **Step 4: Wire deps + endpoints**

```python
def get_ai_recipe_service(
    user: User = Depends(get_current_user),
    scope_loader: IngredientScopeLoader = Depends(get_ingredient_scope_loader),
) -> AiRecipeService:
    cache = AiRecipeCache(get_redis(), ttl_seconds=86400)
    return AiRecipeService(
        user=user,
        scope_loader=scope_loader,
        agent=AiRecipeAgent(),
        cache=cache,
    )
```

```python
async def ai_recommend_recipes(
    refresh: bool = False,
    scope: RecipeScope = RecipeScope.personal,
    service: AiRecipeService = Depends(get_ai_recipe_service),
) -> AiRecipeRecommendationResponse:
    return await service.recommend(refresh=refresh, scope=scope)

async def ai_recipe_detail(
    recipe_id: str,
    scope: RecipeScope = RecipeScope.personal,
    service: AiRecipeService = Depends(get_ai_recipe_service),
) -> AiRecipeDetailResponse:
    return await service.get_detail(recipe_id, scope=scope)
```

- [ ] **Step 5: Update API tests**

기존 mock assert를 `recommend(refresh=False, scope=RecipeScope.personal)` 형태로 맞추고, 아래 추가:

```python
from domains.ingredient.scope import RecipeScope

async def test_ai_recommendations_passes_group_scope(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock = MagicMock()
    mock.recommend = AsyncMock(
        return_value=AiRecipeRecommendationResponse(ingredients_used=[], recipes=[])
    )
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/recommendations",
            headers=auth_headers,
            params={"scope": "group", "refresh": "true"},
        )
        assert response.status_code == 200
        mock.recommend.assert_awaited_once_with(
            refresh=True, scope=RecipeScope.group
        )
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)


async def test_ai_detail_passes_group_scope(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock = MagicMock()
    mock.get_detail = AsyncMock(
        return_value=AiRecipeDetailResponse(
            recipe_id="rid",
            recipe_name="x",
            recipe_ingredients=[],
            owned_ingredients=[],
            missing_ingredients=[],
            ingredients=[],
            steps=[],
            tips=[],
            cached=True,
        )
    )
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/detail",
            headers=auth_headers,
            params={"recipe_id": "rid", "scope": "group"},
        )
        assert response.status_code == 200
        mock.get_detail.assert_awaited_once_with("rid", scope=RecipeScope.group)
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)
```

(`AiRecipeDetailResponse` 필드가 실제 스키마와 다르면 기존 `test_ai_recipe_api.py`의 성공 픽스처를 복사해 사용.)

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/test_ai_recipe_service.py tests/api/test_ai_recipe_api.py -v`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/domains/ai_recipe/service.py src/api/v1/endpoints/rag.py src/api/deps.py \
  tests/unit/test_ai_recipe_service.py tests/api/test_ai_recipe_api.py
git commit -m "$(cat <<'EOF'
Feat: AI 레시피 목록·상세에 personal|group scope 지원

EOF
)"
```

---

### Task 5: GroupService AI list cache invalidation

**Files:**
- Modify: `src/domains/group/service.py`
- Modify: `src/api/deps.py` (`get_group_service`)
- Modify: `tests/unit/test_group_service.py`

**Interfaces:**
- Consumes: `AiRecipeCache.invalidate_list(group_id, scope=RecipeScope.group)`
- `GroupService.__init__(..., list_cache: AiRecipeCache | None = None)`
- 무효화 대상 메서드: `add_ingredients`, `update_ingredient`, `delete_ingredient`, `delete_all_ingredients`, 그리고 merge에서 그룹 재료가 생성·삭제되는 경로
- 패턴: `IngredientService._schedule_ai_recipe_list_invalidation`과 동일하게 after_commit / after_rollback (`scope=RecipeScope.group`, `owner_id=membership.group_id`)

- [ ] **Step 1: Write failing test**

`_service` 헬퍼에 optional `list_cache`를 받게 하고:

```python
from unittest.mock import AsyncMock
from domains.ingredient.scope import RecipeScope

async def test_add_group_ingredients_invalidates_ai_list_cache(db_session):
    owner = await _add_user(db_session, "o@t.com", "owner1")
    svc = _service(owner, db_session)
    await svc.create(CreateGroupRequest(name="home"))
    membership = await GroupRepository(db_session).get_membership(owner.id)
    assert membership is not None

    list_cache = AsyncMock()
    svc_with_cache = GroupService(
        user=owner,
        group_repo=GroupRepository(db_session),
        user_repo=UserRepository(db_session),
        ingredient_repo=IngredientRepository(db_session),
        shopping_repo=ShoppingRepository(db_session),
        list_cache=list_cache,
    )
    await svc_with_cache.add_ingredients(
        AddIngredientRequest(ingredients=["계란"], purchase_date=date.today())
    )
    list_cache.invalidate_list.assert_not_awaited()
    await db_session.commit()
    list_cache.invalidate_list.assert_awaited_once_with(
        membership.group_id, scope=RecipeScope.group
    )
```

(프로젝트의 `IngredientService` 무효화 테스트와 동일하게 commit 후에만 await 되는지 확인. SQLite 테스트 세션이 autocommit이면 해당 파일의 기존 패턴을 그대로 따른다.)

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/unit/test_group_service.py::test_add_group_ingredients_invalidates_ai_list_cache -v`  
Expected: FAIL

- [ ] **Step 3: Implement invalidation on GroupService**

`IngredientService`의 `_schedule_ai_recipe_list_invalidation`을 참고해 그룹용으로 복제:

```python
def _schedule_ai_recipe_list_invalidation(self, group_id: UUID) -> None:
    if self.list_cache is None:
        return
    # after_commit → list_cache.invalidate_list(group_id, scope=RecipeScope.group)
    # after_rollback → cancel
```

호출 위치: 그룹 재료가 실제로 바뀌는 메서드 끝(성공 경로) — `add_ingredients`, `update_ingredient`, `delete_ingredient`, `delete_all_ingredients`, merge에서 그룹 재료 create/delete가 일어난 경우.

- [ ] **Step 4: Wire `get_group_service`**

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
        shopping_repo=ShoppingRepository(session),
        list_cache=AiRecipeCache(get_redis()),
    )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_group_service.py tests/unit/test_ingredient_service.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/domains/group/service.py src/api/deps.py tests/unit/test_group_service.py
git commit -m "$(cat <<'EOF'
Feat: 그룹 재료 변경 시 AI 목록 캐시 무효화

EOF
)"
```

---

### Task 6: End-to-end API happy path (group ingredients → RAG)

**Files:**
- Modify: `tests/api/test_rag_api.py` (또는 `tests/api/test_group_ai_recommendations_api.py` 신규)

**Interfaces:**
- Consumes: 기존 group API + RAG endpoint + `get_rag_retriever` override

- [ ] **Step 1: Write API test**

```python
async def test_recommendations_group_scope_uses_group_fridge_only(
    client: AsyncClient, auth_headers: dict[str, str]
):
    # personal ingredient
    await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={"ingredients": ["개인재료"]},
    )
    # create group + group ingredient
    create = await client.post(
        "/api/v1/groups",
        headers=auth_headers,
        json={"name": "우리집"},
    )
    assert create.status_code == 201
    add = await client.post(
        "/api/v1/groups/me/ingredients",
        headers=auth_headers,
        json={"ingredients": ["그룹재료"], "purchase_date": "2026-07-21"},
    )
    assert add.status_code == 201

    mock_retriever = MagicMock()
    mock_retriever.search.return_value = []
    app.dependency_overrides[get_rag_retriever] = lambda: mock_retriever
    try:
        response = await client.get(
            "/api/v1/recipes/recommendations",
            headers=auth_headers,
            params={"scope": "group"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ingredients_used"] == ["그룹재료"]
        # search query should be built from group ingredient only
        called_query = mock_retriever.search.call_args.args[0]
        assert "그룹재료" in called_query
        assert "개인재료" not in called_query
    finally:
        app.dependency_overrides.pop(get_rag_retriever, None)
```

(그룹 재료 POST 스키마·날짜 필드가 다르면 `tests/api/test_group_api.py`의 성공 요청을 그대로 복사.)

- [ ] **Step 2: Run — expect PASS (구현 완료 후)**

Run: `pytest tests/api/test_rag_api.py::test_recommendations_group_scope_uses_group_fridge_only -v`  
Expected: PASS

빈 그룹 냉장고 케이스도 추가:

```python
async def test_recommendations_group_scope_empty_ignores_personal(
    client: AsyncClient, auth_headers: dict[str, str]
):
    await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={"ingredients": ["개인재료"]},
    )
    create = await client.post(
        "/api/v1/groups",
        headers=auth_headers,
        json={"name": "우리집"},
    )
    assert create.status_code == 201
    mock_retriever = MagicMock()
    app.dependency_overrides[get_rag_retriever] = lambda: mock_retriever
    try:
        response = await client.get(
            "/api/v1/recipes/recommendations",
            headers=auth_headers,
            params={"scope": "group"},
        )
        assert response.status_code == 200
        assert response.json()["ingredients_used"] == []
        mock_retriever.search.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_rag_retriever, None)
```

- [ ] **Step 3: Full related suite**

Run: `pytest tests/unit/test_ingredient_scope.py tests/unit/test_ai_recipe_cache.py tests/unit/test_rag_service.py tests/unit/test_ai_recipe_service.py tests/unit/test_group_service.py tests/api/test_rag_api.py tests/api/test_ai_recipe_api.py -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/api/test_rag_api.py
git commit -m "$(cat <<'EOF'
Test: 그룹 scope RAG가 공유 냉장고만 쓰는지 검증

EOF
)"
```

---

## Spec coverage checklist

| Spec 요구 | Task |
|-----------|------|
| `scope` on RAG / AI list / AI detail | 3, 4 |
| group fridge only | 1, 3, 4, 6 |
| default personal | 3, 4 |
| 404 GROUP_NOT_FOUND | 1, 3 |
| 422 invalid scope | 3 |
| empty → empty list | 1, 6 |
| group cache key | 2, 4 |
| group CRUD invalidates cache | 5 |
| no saved-recipe / detail crawl change | (의도적 미변경) |

## Self-review notes

- Placeholder 없음
- `RecipeScope` / `ScopedIngredients` / cache 시그니처가 Task 1→5에서 일관됨
- `IngredientService`는 `invalidate_list(user_id)` 기본 scope=personal로 회귀 유지
