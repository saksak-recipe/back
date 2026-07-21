# AI 레시피 일일 호출 한도 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI 레시피 LLM 호출에 personal/group 독립 일일 15회 한도(KST 자정 리셋, Redis)를 건다.

**Architecture:** `AiQuotaStore`가 Redis `INCR`+KST TTL로 쿼터를 관리하고, `AiRecipeService`가 캐시 miss / refresh / detail 미생성으로 LLM에 들어가기 직전에만 `consume`한다. 초과 시 `429 AI_QUOTA_EXCEEDED`, Redis 장애 시 fail-closed.

**Tech Stack:** FastAPI, Redis asyncio, pydantic-settings, pytest, `zoneinfo` (Asia/Seoul)

**Spec:** `docs/superpowers/specs/2026-07-21-ai-recipe-daily-quota-design.md`

## Global Constraints

- LLM이 실제로 호출될 때만 1회 차감 (캐시 hit·재료 없음·detail 이미 있음 제외)
- personal 유저당 15회/일, group 그룹당 15회/일, 서로 독립
- 리셋: KST 자정 (`Asia/Seoul`)
- 초과: `429` + `AI_QUOTA_EXCEEDED`
- Redis 장애: fail-closed (`ExternalServiceException`), LLM 미호출
- LLM 실패 후에도 차감 유지; `_generate_list` 내부 2회 재시도는 차감 1회
- API 경로·성공 응답 스키마 변경 없음; remaining 헤더/조회 API 없음
- RAG 임베딩 한도 Out of Scope
- 한도 설정: `AI_QUOTA_DAILY_LIMIT` 기본 15

## File Structure

| File | Responsibility |
|------|----------------|
| `src/core/config.py` | `AI_QUOTA_DAILY_LIMIT: int = 15` |
| `src/core/exception/codes.py` | `AI_QUOTA_EXCEEDED` |
| `src/core/exception/exceptions.py` | `TooManyRequestsException` (429) |
| `src/domains/ai_recipe/quota.py` | `AiQuotaStore` — 키, KST TTL, `consume` |
| `src/domains/ai_recipe/service.py` | LLM 직전 `quota.consume` |
| `src/api/deps.py` | `AiQuotaStore` DI |
| `tests/unit/test_ai_recipe_quota.py` | 쿼터 스토어 단위 테스트 |
| `tests/unit/test_ai_recipe_service.py` | 서비스 연동·캐시 hit 비차감 |
| `tests/api/test_ai_recipe_api.py` | 429 API 스모크 |

---

### Task 1: Error code + 429 exception + config

**Files:**
- Modify: `src/core/exception/codes.py`
- Modify: `src/core/exception/exceptions.py`
- Modify: `src/core/config.py`
- Test: `tests/unit/test_ai_quota_exception.py` (신규, 짧게)

**Interfaces:**
- Produces: `ErrorCode.AI_QUOTA_EXCEEDED = "AI_QUOTA_EXCEEDED"`
- Produces: `class TooManyRequestsException(BaseCustomException)` with `status_code=429`, default `code=ErrorCode.AI_QUOTA_EXCEEDED`
- Produces: `Settings.AI_QUOTA_DAILY_LIMIT: int = 15`
- Consumes: existing `BaseCustomException`, `ErrorCode`

- [ ] **Step 1: Write failing exception smoke test**

Create `tests/unit/test_ai_quota_exception.py`:

```python
from core.exception.codes import ErrorCode
from core.exception.exceptions import TooManyRequestsException


def test_too_many_requests_exception_defaults():
    exc = TooManyRequestsException()
    assert exc.status_code == 429
    assert exc.code == ErrorCode.AI_QUOTA_EXCEEDED
    assert "한도" in exc.detail
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/unit/test_ai_quota_exception.py -v`

Expected: FAIL (`TooManyRequestsException` / `AI_QUOTA_EXCEEDED` import or AttributeError)

- [ ] **Step 3: Implement code, exception, config**

In `src/core/exception/codes.py`, under 공통 section after `EXTERNAL_SERVICE_ERROR`:

```python
    AI_QUOTA_EXCEEDED = "AI_QUOTA_EXCEEDED"
```

In `src/core/exception/exceptions.py`, after `ExternalServiceException`:

```python
class TooManyRequestsException(BaseCustomException):
    def __init__(
        self,
        code: str | ErrorCode = ErrorCode.AI_QUOTA_EXCEEDED,
        detail: str = "오늘 AI 레시피 생성 한도(15회)를 초과했습니다.",
    ):
        super().__init__(status_code=429, code=code, detail=detail)
```

In `src/core/config.py`, after `AI_RECIPE_MODEL`:

```python
    AI_QUOTA_DAILY_LIMIT: int = 15
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/unit/test_ai_quota_exception.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/exception/codes.py src/core/exception/exceptions.py src/core/config.py tests/unit/test_ai_quota_exception.py
git commit -m "$(cat <<'EOF'
Feat: AI 쿼터용 429 예외와 일일 한도 설정 추가

EOF
)"
```

---

### Task 2: AiQuotaStore (Redis)

**Files:**
- Create: `src/domains/ai_recipe/quota.py`
- Create: `tests/unit/test_ai_recipe_quota.py`

**Interfaces:**
- Consumes: `RecipeScope` from `domains.ingredient.scope`
- Consumes: `settings.AI_QUOTA_DAILY_LIMIT`, `TooManyRequestsException`, `ExternalServiceException`
- Produces:

```python
class AiQuotaStore:
    def __init__(self, redis: Redis, daily_limit: int | None = None) -> None: ...
    def key(self, scope: RecipeScope, owner_id: uuid.UUID, *, now: datetime | None = None) -> str: ...
    def seconds_until_kst_midnight(self, *, now: datetime | None = None) -> int: ...
    async def consume(self, scope: RecipeScope, owner_id: uuid.UUID) -> int:
        """Increment daily counter. Returns new count. Raises TooManyRequestsException if over limit.
        Raises ExternalServiceException on Redis failure."""
```

- Key format: `ai_quota:personal:{owner_id}:{YYYYMMDD}` / `ai_quota:group:{owner_id}:{YYYYMMDD}` (date in Asia/Seoul)
- Algorithm: `INCR` → if count == 1 set `EXPIRE` to seconds until next KST midnight → if count > limit then `DECR` and raise `TooManyRequestsException`

- [ ] **Step 1: Write failing quota unit tests**

Create `tests/unit/test_ai_recipe_quota.py`:

```python
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException, TooManyRequestsException
from domains.ai_recipe.quota import AiQuotaStore
from domains.ingredient.scope import RecipeScope

KST = ZoneInfo("Asia/Seoul")
OWNER = uuid.UUID("11111111-1111-1111-1111-111111111111")
GROUP = uuid.UUID("22222222-2222-2222-2222-222222222222")


def test_key_uses_scope_and_kst_date():
    redis = MagicMock()
    store = AiQuotaStore(redis, daily_limit=15)
    now = datetime(2026, 7, 21, 23, 30, tzinfo=KST)

    assert (
        store.key(RecipeScope.personal, OWNER, now=now)
        == f"ai_quota:personal:{OWNER}:20260721"
    )
    assert (
        store.key(RecipeScope.group, GROUP, now=now)
        == f"ai_quota:group:{GROUP}:20260721"
    )


def test_seconds_until_kst_midnight():
    redis = MagicMock()
    store = AiQuotaStore(redis, daily_limit=15)
    now = datetime(2026, 7, 21, 23, 0, 0, tzinfo=KST)

    assert store.seconds_until_kst_midnight(now=now) == 3600


async def test_consume_increments_and_sets_ttl_on_first():
    redis = AsyncMock()
    redis.incr.return_value = 1
    redis.expire.return_value = True
    store = AiQuotaStore(redis, daily_limit=15)

    count = await store.consume(RecipeScope.personal, OWNER)

    assert count == 1
    redis.incr.assert_awaited_once()
    redis.expire.assert_awaited_once()
    assert redis.expire.await_args.args[1] > 0


async def test_consume_raises_when_over_limit_and_decrs():
    redis = AsyncMock()
    redis.incr.return_value = 16
    redis.decr.return_value = 15
    store = AiQuotaStore(redis, daily_limit=15)

    with pytest.raises(TooManyRequestsException) as exc_info:
        await store.consume(RecipeScope.personal, OWNER)

    assert exc_info.value.code == ErrorCode.AI_QUOTA_EXCEEDED
    redis.decr.assert_awaited_once()


async def test_consume_personal_and_group_use_different_keys():
    redis = AsyncMock()
    redis.incr.return_value = 1
    redis.expire.return_value = True
    store = AiQuotaStore(redis, daily_limit=15)

    await store.consume(RecipeScope.personal, OWNER)
    await store.consume(RecipeScope.group, GROUP)

    keys = [call.args[0] for call in redis.incr.await_args_list]
    assert keys[0].startswith("ai_quota:personal:")
    assert keys[1].startswith("ai_quota:group:")
    assert keys[0] != keys[1]


async def test_consume_redis_failure_is_fail_closed():
    redis = AsyncMock()
    redis.incr.side_effect = ConnectionError("down")
    store = AiQuotaStore(redis, daily_limit=15)

    with pytest.raises(ExternalServiceException):
        await store.consume(RecipeScope.personal, OWNER)
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/unit/test_ai_recipe_quota.py -v`

Expected: FAIL (`domains.ai_recipe.quota` missing)

- [ ] **Step 3: Implement AiQuotaStore**

Create `src/domains/ai_recipe/quota.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from core.config import settings
from core.exception.exceptions import ExternalServiceException, TooManyRequestsException
from domains.ingredient.scope import RecipeScope

KST = ZoneInfo("Asia/Seoul")


class AiQuotaStore:
    def __init__(
        self,
        redis: Redis,
        daily_limit: int | None = None,
    ) -> None:
        self._redis = redis
        self._daily_limit = (
            daily_limit if daily_limit is not None else settings.AI_QUOTA_DAILY_LIMIT
        )

    def key(
        self,
        scope: RecipeScope,
        owner_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> str:
        current = now or datetime.now(KST)
        if current.tzinfo is None:
            current = current.replace(tzinfo=KST)
        else:
            current = current.astimezone(KST)
        day = current.strftime("%Y%m%d")
        return f"ai_quota:{scope.value}:{owner_id}:{day}"

    def seconds_until_kst_midnight(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(KST)
        if current.tzinfo is None:
            current = current.replace(tzinfo=KST)
        else:
            current = current.astimezone(KST)
        tomorrow = (current + timedelta(days=1)).date()
        midnight = datetime(
            tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=KST
        )
        seconds = int((midnight - current).total_seconds())
        return max(seconds, 1)

    async def consume(self, scope: RecipeScope, owner_id: uuid.UUID) -> int:
        redis_key = self.key(scope, owner_id)
        try:
            count = await self._redis.incr(redis_key)
            if count == 1:
                await self._redis.expire(
                    redis_key, self.seconds_until_kst_midnight()
                )
            if count > self._daily_limit:
                await self._redis.decr(redis_key)
                raise TooManyRequestsException(
                    detail=(
                        f"오늘 AI 레시피 생성 한도"
                        f"({self._daily_limit}회)를 초과했습니다."
                    )
                )
            return int(count)
        except TooManyRequestsException:
            raise
        except Exception as exc:
            raise ExternalServiceException(
                detail="AI 사용량 확인에 실패했습니다."
            ) from exc
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/unit/test_ai_recipe_quota.py -v`

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/domains/ai_recipe/quota.py tests/unit/test_ai_recipe_quota.py
git commit -m "$(cat <<'EOF'
Feat: AI 레시피 Redis 일일 쿼터 스토어 추가

EOF
)"
```

---

### Task 3: Wire quota into AiRecipeService

**Files:**
- Modify: `src/domains/ai_recipe/service.py`
- Modify: `tests/unit/test_ai_recipe_service.py`
- Modify: `src/api/deps.py`

**Interfaces:**
- Consumes: `AiQuotaStore.consume(scope, owner_id) -> int`
- Modifies: `AiRecipeService.__init__(..., quota: AiQuotaStore)`
- Call sites:
  - `recommend`: after cache miss / refresh decision, **before** `_generate_list` — `await self.quota.consume(scoped.scope, scoped.cache_owner_id)`
  - `get_detail`: when `not record.has_detail()`, **before** `run_detail` — same consume with loaded `scoped`
- Empty ingredients / cache hit / `has_detail()`: **no** consume
- Update every `AiRecipeService(...)` construction in unit tests to pass `quota=AsyncMock()` (default `consume` returns 1). For “should not consume” tests, assert `quota.consume` not awaited. For LLM path tests, assert `consume` awaited once with correct scope/owner.

- [ ] **Step 1: Update service unit tests for quota (failing until wired)**

In `tests/unit/test_ai_recipe_service.py`:

1. Add helper or default in each constructor:

```python
def _quota():
    q = AsyncMock()
    q.consume.return_value = 1
    return q
```

2. Every `AiRecipeService(...)` must include `quota=_quota()` (or a shared fixture).

3. Add / adjust cases:

```python
async def test_recommend_cache_hit_does_not_consume_quota(user):
    # same setup as matching list cache test
    quota = _quota()
    service = AiRecipeService(
        user=user, scope_loader=scope_loader, agent=agent, cache=cache, quota=quota
    )
    await service.recommend()
    quota.consume.assert_not_awaited()


async def test_recommend_llm_path_consumes_quota(user):
    # refresh or cache miss setup with agent returning 5 candidates
    quota = _quota()
    service = AiRecipeService(
        user=user, scope_loader=scope_loader, agent=agent, cache=cache, quota=quota
    )
    await service.recommend(refresh=True)
    quota.consume.assert_awaited_once_with(RecipeScope.personal, user.id)
    agent.run_list.assert_called_once()


async def test_recommend_quota_exceeded_skips_agent(user):
    from core.exception.exceptions import TooManyRequestsException
    from core.exception.codes import ErrorCode

    quota = _quota()
    quota.consume.side_effect = TooManyRequestsException()
    agent = MagicMock()
    service = AiRecipeService(
        user=user, scope_loader=scope_loader, agent=agent, cache=cache, quota=quota
    )
    with pytest.raises(TooManyRequestsException) as exc_info:
        await service.recommend(refresh=True)
    assert exc_info.value.code == ErrorCode.AI_QUOTA_EXCEEDED
    agent.run_list.assert_not_called()


async def test_get_detail_cached_does_not_consume(user):
    # record with has_detail True
    quota = _quota()
    ...
    await service.get_detail("rid")
    quota.consume.assert_not_awaited()


async def test_get_detail_llm_consumes_quota(user):
    # record without detail; agent returns detail dict
    quota = _quota()
    ...
    await service.get_detail("rid")
    quota.consume.assert_awaited_once()
    agent.run_detail.assert_called_once()


async def test_recommend_group_consumes_group_owner(user):
    group_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    scope_loader = _scope_loader(
        [MagicMock(ingredient_name="계란", expiration_date=None)],
        scope=RecipeScope.group,
        cache_owner_id=group_id,
    )
    quota = _quota()
    ...
    await service.recommend(refresh=True, scope=RecipeScope.group)
    quota.consume.assert_awaited_once_with(RecipeScope.group, group_id)
```

Also assert empty-ingredients path does not call `consume`.

Adapt field names to existing fixtures in the file (`has_detail`, agent return shapes) — keep assertions exact.

- [ ] **Step 2: Run service tests — expect FAIL**

Run: `pytest tests/unit/test_ai_recipe_service.py -v`

Expected: FAIL (`quota` unexpected / missing argument, or new tests fail)

- [ ] **Step 3: Implement service + deps wiring**

`AiRecipeService.__init__` add:

```python
from domains.ai_recipe.quota import AiQuotaStore
# ...
def __init__(..., cache: AiRecipeCache, quota: AiQuotaStore) -> None:
    ...
    self.quota = quota
```

In `recommend`, immediately before `candidates = await self._generate_list(...)`:

```python
await self.quota.consume(scoped.scope, scoped.cache_owner_id)
```

In `get_detail`, after confirming `not record.has_detail()`, after `scoped = await self.scope_loader.load(scope)`, before `run_detail`:

```python
await self.quota.consume(scoped.scope, scoped.cache_owner_id)
```

In `src/api/deps.py`:

```python
from domains.ai_recipe.quota import AiQuotaStore
# ...
def get_ai_recipe_service(...) -> AiRecipeService:
    cache = AiRecipeCache(get_redis(), ttl_seconds=86400)
    return AiRecipeService(
        user=user,
        scope_loader=scope_loader,
        agent=AiRecipeAgent(),
        cache=cache,
        quota=AiQuotaStore(get_redis()),
    )
```

Update **all** existing service constructions in `test_ai_recipe_service.py` (and any other test that builds `AiRecipeService`) to pass `quota=_quota()`.

- [ ] **Step 4: Run unit tests — expect PASS**

Run: `pytest tests/unit/test_ai_recipe_service.py tests/unit/test_ai_recipe_quota.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domains/ai_recipe/service.py src/api/deps.py tests/unit/test_ai_recipe_service.py
git commit -m "$(cat <<'EOF'
Feat: AI 레시피 LLM 호출 직전에 일일 쿼터 차감

EOF
)"
```

---

### Task 4: API 429 smoke test

**Files:**
- Modify: `tests/api/test_ai_recipe_api.py`

**Interfaces:**
- Consumes: `TooManyRequestsException` raised from mocked `get_ai_recipe_service.recommend`
- Produces: API returns 429 + `code == ErrorCode.AI_QUOTA_EXCEEDED`

- [ ] **Step 1: Write API test**

```python
from core.exception.exceptions import TooManyRequestsException

async def test_ai_recommendations_quota_exceeded(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock = MagicMock()
    mock.recommend = AsyncMock(side_effect=TooManyRequestsException())
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/recommendations",
            headers=auth_headers,
        )
        assert response.status_code == 429
        assert response.json()["code"] == ErrorCode.AI_QUOTA_EXCEEDED
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)
```

- [ ] **Step 2: Run test — expect PASS** (handler already maps `BaseCustomException`)

Run: `pytest tests/api/test_ai_recipe_api.py::test_ai_recommendations_quota_exceeded -v`

Expected: PASS

If FAIL because handler missing — fix handler (should already work via `BaseCustomException`).

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_ai_recipe_api.py
git commit -m "$(cat <<'EOF'
Test: AI 쿼터 초과 시 429 API 응답 검증

EOF
)"
```

---

### Task 5: Full verification

- [ ] **Step 1: Run AI-related suite**

Run: `pytest tests/unit/test_ai_recipe_*.py tests/unit/test_ai_quota_exception.py tests/api/test_ai_recipe_api.py -v`

Expected: all PASS

- [ ] **Step 2: Spec checklist**

| Spec requirement | Covered by |
|------------------|------------|
| LLM only 차감 | Task 3 tests (cache hit / detail cached / empty) |
| personal 15 / group 15 independent | Task 2 key tests + Task 3 group consume |
| KST midnight | Task 2 key + TTL helpers |
| 429 AI_QUOTA_EXCEEDED | Task 1 + 4 |
| fail-closed Redis | Task 2 |
| list retry 차감 1회 | consume outside `_generate_list` loop (Task 3) |
| config AI_QUOTA_DAILY_LIMIT | Task 1 |
| RAG unchanged | no RAG file edits |

- [ ] **Step 3: Final commit only if dirty** (docs already committed earlier)

---

## Self-Review (plan author)

1. **Spec coverage:** All Decisions/Testing rows mapped to Tasks 1–5. Remaining API/header explicitly out of scope — no task.
2. **Placeholders:** None; code blocks are concrete.
3. **Type consistency:** `consume(scope: RecipeScope, owner_id: uuid.UUID) -> int` used uniformly; keys use `scope.value`.
