# 핵심 루프 심화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 유통기한 urgency를 RAG/AI 추천에 반영하고, 동의어·부분일치로 owned/missing을 맞추며, AI 목록을 structured 1회·캐시·재시도로 안정화한다.

**Architecture:** `ingredient_matching` 공유 레이어(정규화·동의어·urgency·classify)를 RAG mapper/AI service가 소비한다. RAG는 urgent 쿼리 가중 + 재정렬 후 TOP_K 고정(urgent 없을 때만 기존 random). AI 목록은 tool-calling 제거 후 structured 1회, Redis 목록 캐시, `refresh=true` 우회, 재료 CRUD 시 무효화.

**Tech Stack:** FastAPI, SQLAlchemy async, Redis, LangChain `ChatOpenAI.with_structured_output`, Pydantic, pytest

## Global Constraints

- API 브레이킹 변경 없음 (optional `refresh` 쿼리만 추가)
- expired·soon = urgent (소진 대상); unknown/ok = normal
- 동의어 = 정적 사전 + 부분일치(짧은 쪽 길이 ≥ 2); 임베딩/LLM 매칭 Out of Scope
- AI 목록 = structured 1회; `AGENT_TIMEOUT_SECONDS` ≈ 20–25; 실패 시 1회 재시도; RAG 폴백 없음
- `AI_RECIPE_MODEL` 설정값 유지
- 스트리밍·동의어 어드민·푸시 Out of Scope
- 작업 루트: `back/` (이 레포). 앱 `refresh=true` 연동은 별도(필요 시)

## File Structure

| Path | Responsibility |
|------|----------------|
| `src/domains/ingredient_matching/__init__.py` | 공개 API re-export |
| `src/domains/ingredient_matching/synonyms.py` | canonical→aliases 시드 + reverse map |
| `src/domains/ingredient_matching/matching.py` | `normalize_name`, `names_match`, `classify_ingredients` |
| `src/domains/ingredient_matching/urgency.py` | `urgent_names`, `count_urgent_owned` |
| `tests/unit/test_ingredient_matching.py` | 매칭·urgency unit |
| `src/domains/rag/mapper.py` | matching으로 classify/normalize 위임; `build_ingredient_query` urgent 가중 |
| `src/domains/rag/service.py` | urgency 추출·재정렬·선택 규칙 |
| `tests/unit/test_rag_mapper.py` / `test_rag_service.py` | 동의어·urgency 회귀 |
| `src/domains/ai_recipe/schemas.py` | structured list/detail payload + 목록 캐시 레코드 |
| `src/domains/ai_recipe/agent.py` | structured 1회 `run_list` / `run_detail` |
| `src/domains/ai_recipe/tools.py` | 삭제 또는 목록 path에서 제거 |
| `src/domains/ai_recipe/cache.py` | 개별 recipe + 목록 캐시·무효화 |
| `src/domains/ai_recipe/service.py` | timeout·retry·cache·urgency 힌트 |
| `src/api/v1/endpoints/rag.py` | `refresh` 쿼리 |
| `src/domains/ingredient/service.py` + `api/deps.py` | CRUD 후 목록 캐시 무효화 |
| `tests/unit/test_ai_recipe_*.py` / `tests/api/test_ai_recipe_api.py` | AI 회귀 |

---

### Task 1: `ingredient_matching` — normalize · synonym · names_match · classify

**Files:**
- Create: `src/domains/ingredient_matching/__init__.py`
- Create: `src/domains/ingredient_matching/synonyms.py`
- Create: `src/domains/ingredient_matching/matching.py`
- Create: `tests/unit/test_ingredient_matching.py`
- Modify: `src/domains/rag/mapper.py` — `normalize_name` / `classify_ingredients`를 matching에 위임(재export 유지)
- Modify: `tests/unit/test_rag_mapper.py` — 동의어 케이스 추가

**Interfaces:**
- Produces: `normalize_name(name: str) -> str`
- Produces: `names_match(a: str, b: str) -> bool`
- Produces: `classify_ingredients(recipe_ingredients: list[str], owned_names: list[str]) -> tuple[list[str], list[str]]`
- Produces: `canonical_of(normalized: str) -> str` (내부/테스트용)
- Consumes: none

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_ingredient_matching.py`:

```python
from domains.ingredient_matching.matching import (
    classify_ingredients,
    names_match,
    normalize_name,
)


def test_normalize_strips_casefold_spaces():
    assert normalize_name("  대 파 ") == "대파"
    assert normalize_name("Egg") == "egg"


def test_names_match_exact_normalized():
    assert names_match("대 파", "대파")


def test_names_match_synonym_egg():
    assert names_match("계란", "달걀")
    assert names_match("달걀", "계란")


def test_names_match_substring_min_len():
    assert names_match("달걀", "유기농달걀")
    assert not names_match("파", "대파")  # 1글자 부분일치 금지


def test_names_match_no_false_friend():
    assert not names_match("간장", "된장소스")


def test_classify_synonym_owned():
    owned, missing = classify_ingredients(
        ["달걀", "밥", "대파"],
        ["계란", "밥"],
    )
    assert owned == ["달걀", "밥"]
    assert missing == ["대파"]
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `cd /Users/jeong-yeonghun/Desktop/saksak/back && PYTHONPATH=src pytest tests/unit/test_ingredient_matching.py -v`

Expected: FAIL (`ModuleNotFoundError` or import error)

- [ ] **Step 3: Implement matching module**

`src/domains/ingredient_matching/synonyms.py`:

```python
"""정적 동의어 시드. canonical(정규화 키) → aliases(정규화 전 표기 포함 가능)."""

# 값은 사람이 읽기 쉬운 원문; 로드 시 normalize
SYNONYM_GROUPS: dict[str, list[str]] = {
    "달걀": ["계란", "에그", "egg", "eggs"],
    "대파": ["쪽파", "실파"],
    "돼지고기": ["돼지", "포크"],
    "소고기": ["소", "비프"],
    "닭고기": ["닭", "치킨"],
    "두부": ["순두부"],
    "고추장": [],
    "된장": [],
    "고춧가루": ["고추가루"],
    "다진마늘": ["마늘다진것", "다진 마늘"],
    "식용유": ["오일", "올리브유", "카놀라유"],
    "맛살": ["게맛살"],
    "어묵": ["오뎅"],
    "김": ["김가루", "김자반"],
}


def build_alias_to_canonical() -> dict[str, str]:
    from domains.ingredient_matching.matching import normalize_name

    mapping: dict[str, str] = {}
    for canonical, aliases in SYNONYM_GROUPS.items():
        c = normalize_name(canonical)
        mapping[c] = c
        for alias in aliases:
            mapping[normalize_name(alias)] = c
    return mapping
```

순환 import를 피하려면 `normalize_name`을 `matching.py` 상단에 두고, `synonyms.py`는 **원문만** 보관한 뒤 `matching.py`에서 reverse map을 빌드한다:

`synonyms.py` — `SYNONYM_GROUPS`만 (위 dict, import 없음).

`matching.py`:

```python
from __future__ import annotations

from domains.ingredient_matching.synonyms import SYNONYM_GROUPS

_MIN_SUBSTRING_LEN = 2
_alias_to_canonical: dict[str, str] | None = None


def normalize_name(name: str) -> str:
    return name.strip().casefold().replace(" ", "")


def _alias_map() -> dict[str, str]:
    global _alias_to_canonical
    if _alias_to_canonical is None:
        mapping: dict[str, str] = {}
        for canonical, aliases in SYNONYM_GROUPS.items():
            c = normalize_name(canonical)
            mapping[c] = c
            for alias in aliases:
                a = normalize_name(alias)
                if a:
                    mapping[a] = c
        _alias_to_canonical = mapping
    return _alias_to_canonical


def canonical_of(name: str) -> str:
    n = normalize_name(name)
    if not n:
        return ""
    return _alias_map().get(n, n)


def names_match(a: str, b: str) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if canonical_of(a) == canonical_of(b):
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) < _MIN_SUBSTRING_LEN:
        return False
    return shorter in longer


def classify_ingredients(
    recipe_ingredients: list[str], owned_names: list[str]
) -> tuple[list[str], list[str]]:
    owned_list = [n for n in owned_names if normalize_name(n)]
    owned: list[str] = []
    missing: list[str] = []
    for name in recipe_ingredients:
        if any(names_match(name, o) for o in owned_list):
            owned.append(name)
        else:
            missing.append(name)
    return owned, missing
```

`__init__.py`:

```python
from domains.ingredient_matching.matching import (
    canonical_of,
    classify_ingredients,
    names_match,
    normalize_name,
)

__all__ = [
    "canonical_of",
    "classify_ingredients",
    "names_match",
    "normalize_name",
]
```

`mapper.py` — 기존 `normalize_name` / `classify_ingredients` 본문을 제거하고:

```python
from domains.ingredient_matching.matching import (
    classify_ingredients,
    normalize_name,
)
```

나머지(`build_ingredient_query`, `is_recipe_name_in_ingredients` 등)는 `normalize_name` import를 쓰도록 유지.

`test_rag_mapper.py`에 추가:

```python
def test_classify_ingredients_synonym_match():
    owned, missing = classify_ingredients(["달걀", "밥"], ["계란"])
    assert owned == ["달걀"]
    assert missing == ["밥"]
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `PYTHONPATH=src pytest tests/unit/test_ingredient_matching.py tests/unit/test_rag_mapper.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domains/ingredient_matching src/domains/rag/mapper.py tests/unit/test_ingredient_matching.py tests/unit/test_rag_mapper.py
git commit -m "$(cat <<'EOF'
Feat: 재료 동의어·부분일치 매칭 레이어 추가

EOF
)"
```

---

### Task 2: urgency 헬퍼 + RAG 쿼리 가중 · 재정렬 · 선택

**Files:**
- Create: `src/domains/ingredient_matching/urgency.py`
- Modify: `tests/unit/test_ingredient_matching.py` — urgency 테스트 추가
- Modify: `src/domains/rag/mapper.py` — `build_ingredient_query(names, urgent_names=None)`
- Modify: `src/domains/rag/service.py` — urgent 추출·재정렬·TOP_K 규칙
- Modify: `tests/unit/test_rag_service.py` — urgency 선택 회귀
- Modify: `src/domains/ingredient_matching/__init__.py` — urgency export

**Interfaces:**
- Consumes: `compute_status` from `domains.ingredient.service`, `names_match` / `normalize_name`
- Produces: `urgent_names(ingredients: Sequence, today: date | None = None) -> list[str]`
- Produces: `count_urgent_owned(owned_ingredients: list[str], urgent: list[str]) -> int`
- Produces: `build_ingredient_query(names, urgent_names: list[str] | None = None) -> str`
- Produces: RagService — urgent≥1이면 재정렬 상위 TOP_K; 아니면 `random.sample`

- [ ] **Step 1: Write failing urgency + RAG selection tests**

`urgency.py` 테스트 (`test_ingredient_matching.py`에 추가):

```python
from datetime import date, timedelta
from types import SimpleNamespace

from domains.ingredient_matching.urgency import count_urgent_owned, urgent_names


def test_urgent_names_includes_soon_and_expired():
    today = date(2026, 7, 21)
    items = [
        SimpleNamespace(ingredient_name="우유", expiration_date=today - timedelta(days=1)),
        SimpleNamespace(ingredient_name="계란", expiration_date=today + timedelta(days=2)),
        SimpleNamespace(ingredient_name="양파", expiration_date=today + timedelta(days=10)),
        SimpleNamespace(ingredient_name="김치", expiration_date=None),
    ]
    assert urgent_names(items, today=today) == ["우유", "계란"]


def test_count_urgent_owned_uses_names_match():
    assert count_urgent_owned(["달걀", "밥"], ["계란", "우유"]) == 1
```

`test_rag_service.py` — 기존 패턴에 맞춰 mock retriever로 후보 여러 개 넣고, urgent 재료가 있으면 **random이 아닌** urgent 교집합이 큰 순 TOP_K가 나오는지 검증. (파일 기존 fixture를 읽고 동일 스타일로 추가.)

예시 핵심 assert:

```python
# urgent=["계란"] 이고 후보 A owned에 계란, B에는 없음 → A가 결과에 포함되고 B보다 우선
# len(recipes) == TOP_K
# 호출 시 random.sample이 쓰이지 않음(urgent 있을 때) — monkeypatch로 sample 호출 시 fail
```

`build_ingredient_query` 테스트 (`test_rag_mapper.py`):

```python
def test_build_ingredient_query_weights_urgent_first():
    q = build_ingredient_query(["양파", "계란", "밥"], urgent_names=["계란"])
    assert q.startswith("parsed_ingredients: 계란")
    assert "계란" in q and "양파" in q
```

- [ ] **Step 2: Run — expect FAIL**

Run: `PYTHONPATH=src pytest tests/unit/test_ingredient_matching.py tests/unit/test_rag_mapper.py::test_build_ingredient_query_weights_urgent_first tests/unit/test_rag_service.py -v`

Expected: FAIL (urgency / 새 시그니처 없음)

- [ ] **Step 3: Implement urgency + RAG hooks**

`urgency.py`:

```python
from __future__ import annotations

from datetime import date
from typing import Protocol

from domains.ingredient.service import compute_status
from domains.ingredient_matching.matching import names_match


class _HasNameAndExpiry(Protocol):
    ingredient_name: str
    expiration_date: date | None


def urgent_names(
    ingredients: list[_HasNameAndExpiry],
    today: date | None = None,
) -> list[str]:
    today = today or date.today()
    names: list[str] = []
    seen: set[str] = set()
    for item in ingredients:
        status = compute_status(item.expiration_date, today)
        if status not in ("expired", "soon"):
            continue
        key = item.ingredient_name.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(item.ingredient_name)
    return names


def count_urgent_owned(owned_ingredients: list[str], urgent: list[str]) -> int:
    return sum(
        1
        for owned in owned_ingredients
        if any(names_match(owned, u) for u in urgent)
    )
```

`build_ingredient_query` 변경:

```python
def build_ingredient_query(
    names: list[str], urgent_names: list[str] | None = None
) -> str:
    urgent = [n for n in (urgent_names or []) if n]
    # urgent를 앞에 두 번 넣어 검색 가중, 이어서 전체 이름
    weighted = list(urgent) + list(urgent) + list(names)
    return "parsed_ingredients: " + ", ".join(weighted)
```

`RagService.recommend_recipes` 핵심:

```python
from domains.ingredient_matching.urgency import count_urgent_owned, urgent_names

# ...
ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
names = [item.ingredient_name for item in ingredients]
if not names:
    return RecipeRecommendationResponse(ingredients_used=[], recipes=[])

urgent = urgent_names(ingredients)
query = build_ingredient_query(names, urgent_names=urgent)
# ... search, map, filter → candidates (기존과 동일, CANDIDATE_POOL_K까지)

if urgent:
    candidates.sort(
        key=lambda r: (
            count_urgent_owned(r.owned_ingredients, urgent),
            r.score,
        ),
        reverse=True,
    )
    recipes = candidates[:TOP_K]
else:
    if len(candidates) <= TOP_K:
        recipes = candidates
    else:
        recipes = random.sample(candidates, TOP_K)
```

- [ ] **Step 4: Run — expect PASS**

Run: `PYTHONPATH=src pytest tests/unit/test_ingredient_matching.py tests/unit/test_rag_mapper.py tests/unit/test_rag_service.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domains/ingredient_matching src/domains/rag tests/unit/test_ingredient_matching.py tests/unit/test_rag_mapper.py tests/unit/test_rag_service.py
git commit -m "$(cat <<'EOF'
Feat: 유통기한 urgency 기반 RAG 쿼리 가중·재정렬

EOF
)"
```

---

### Task 3: AI 목록 structured 1회 + timeout + 1회 재시도 + urgency 힌트

**Files:**
- Modify: `src/domains/ai_recipe/schemas.py` — `AiRecipeCandidateList` (recipes: list, min/max 5)
- Modify: `src/domains/ai_recipe/agent.py` — tool loop → `with_structured_output`; `run_list(owned_names, urgent_names=None)`
- Delete or gut: `src/domains/ai_recipe/tools.py` (목록/상세 path에서 미사용)
- Modify: `src/domains/ai_recipe/service.py` — `AGENT_TIMEOUT_SECONDS = 25`; retry 1회; `urgent_names` 전달; ChatOpenAI timeout 정합
- Modify: `tests/unit/test_ai_recipe_agent.py` — structured mock
- Modify: `tests/unit/test_ai_recipe_service.py` — timeout/retry
- Delete: `tests/unit/test_ai_recipe_tools.py` (tools 삭제 시)

**Interfaces:**
- Produces: `AiRecipeAgent.run_list(owned_names: list[str], urgent_names: list[str] | None = None) -> list[AiRecipeCandidate]`
- Produces: `AiRecipeAgent.run_detail(...)` structured 1회 (기존 시그니처 유지)
- Consumes: `classify_ingredients` (service 쪽 서버 분류 유지), `urgent_names` from matching

- [ ] **Step 1: Rewrite agent/service tests for structured + retry**

`test_ai_recipe_agent.py` 요지 — LLM mock이 `with_structured_output` 체인을 반환:

```python
def test_run_list_structured_returns_five():
    payload = MagicMock()
    payload.recipes = [
        AiRecipeCandidate(
            recipe_name=f"요리{i}",
            recipe_ingredients=["계란"],
            recipe_difficulty="초급",
            time="10분",
        )
        for i in range(5)
    ]
    structured = MagicMock()
    structured.invoke.return_value = payload
    llm = MagicMock()
    llm.with_structured_output.return_value = structured

    out = AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").run_list(
        ["계란"], urgent_names=["계란"]
    )
    assert len(out) == 5
    # invoke에 전달된 HumanMessage에 "우선 소진" 또는 urgent 이름 포함
```

`test_ai_recipe_service.py` — `run_list`가 첫 호출 TimeoutError/AgentFailedError, 두 번째 성공 → 응답 5개; 두 번 모두 실패 → ExternalServiceException.

- [ ] **Step 2: Run — expect FAIL**

Run: `PYTHONPATH=src pytest tests/unit/test_ai_recipe_agent.py tests/unit/test_ai_recipe_service.py -v`

Expected: FAIL (아직 tool-calling)

- [ ] **Step 3: Implement structured agent + service retry**

`schemas.py` 추가:

```python
class AiRecipeCandidateList(BaseModel):
    recipes: list[AiRecipeCandidate] = Field(min_length=5, max_length=5)
```

상세용 payload가 없으면:

```python
class AiRecipeDetailPayload(BaseModel):
    ingredients: list[AiRecipeIngredient]
    steps: list[AiRecipeStep]
    tips: list[str] = Field(default_factory=list)
```

`agent.py` 골격:

```python
LIST_SYSTEM = (
    "You are a Korean home-cooking assistant. "
    f"Propose exactly {TOP_K} recipes the user can mostly cook with fridge items. "
    "Prefer using urgent/expiring ingredients when listed. "
    "Return only the structured recipe list."
)
TOP_K = 5
LLM_TIMEOUT_SECONDS = 25

class AiRecipeAgent:
    def __init__(...):
        self._llm = llm or ChatOpenAI(
            model=self._model_name,
            api_key=settings.OPENAI_API_KEY.get_secret_value(),
            timeout=LLM_TIMEOUT_SECONDS,
        )

    def run_list(
        self,
        owned_names: list[str],
        urgent_names: list[str] | None = None,
    ) -> list[AiRecipeCandidate]:
        urgent = urgent_names or []
        urgent_line = (
            f"우선 소진(유통기한 임박/지남): {', '.join(urgent)}\n"
            if urgent
            else ""
        )
        structured = self._llm.with_structured_output(AiRecipeCandidateList)
        try:
            result = structured.invoke([
                SystemMessage(content=LIST_SYSTEM),
                HumanMessage(
                    content=(
                        f"{urgent_line}"
                        f"냉장고 재료: {', '.join(owned_names)}\n"
                        f"정확히 {TOP_K}개 레시피를 제안하세요."
                    )
                ),
            ])
        except Exception as exc:
            raise AgentFailedError("recipe list structured invoke failed") from exc
        recipes = list(result.recipes)
        if len(recipes) != TOP_K:
            raise AgentFailedError(f"expected {TOP_K} recipes, got {len(recipes)}")
        return recipes

    def run_detail(...):
        # with_structured_output(AiRecipeDetailPayload) 1회
        # tips/ingredients/steps dict로 반환 (기존 service 호환)
```

`service.py`:

```python
AGENT_TIMEOUT_SECONDS = 25

async def recommend(self, refresh: bool = False) -> AiRecipeRecommendationResponse:
    # Task 4에서 cache 연결. 여기선 generate 헬퍼 + retry
    ...

async def _generate_list(self, names: list[str], urgent: list[str]):
    last_exc: Exception | None = None
    for _ in range(2):  # 최초 + 1 재시도
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self.agent.run_list, names, urgent),
                timeout=AGENT_TIMEOUT_SECONDS,
            )
        except (TimeoutError, AgentFailedError, openai.OpenAIError) as exc:
            last_exc = exc
    assert last_exc is not None
    logger.exception("AI recipe recommend failed")
    raise ExternalServiceException(detail="AI 레시피 생성에 실패했습니다.") from last_exc
```

`tools.py` 삭제 시 `agent`·테스트·`TOP_K` import 경로를 `agent.py`/`schemas.py`로 정리.

- [ ] **Step 4: Run — expect PASS**

Run: `PYTHONPATH=src pytest tests/unit/test_ai_recipe_agent.py tests/unit/test_ai_recipe_service.py tests/unit/test_ai_recipe_schemas.py -v`

Expected: PASS (tools 테스트 파일 삭제했다면 제외)

- [ ] **Step 5: Commit**

```bash
git add src/domains/ai_recipe tests/unit/test_ai_recipe_*.py
git commit -m "$(cat <<'EOF'
Feat: AI 목록 structured 1회·urgency 힌트·재시도 안정화

EOF
)"
```

---

### Task 4: AI 목록 Redis 캐시 · `refresh` · 재료 CRUD 무효화

**Files:**
- Modify: `src/domains/ai_recipe/cache.py` — list get/set/invalidate
- Modify: `src/domains/ai_recipe/schemas.py` — `AiRecipeListCacheRecord` (ingredients_hash + response payload)
- Modify: `src/domains/ai_recipe/service.py` — recommend(refresh), hash, cache
- Modify: `src/api/v1/endpoints/rag.py` — `refresh: bool = False`
- Modify: `src/domains/ingredient/service.py` — CRUD 후 invalidate
- Modify: `src/api/deps.py` — IngredientService에 cache 주입
- Modify: `tests/unit/test_ai_recipe_cache.py`, `test_ai_recipe_service.py`, `tests/api/test_ai_recipe_api.py`
- Modify: `tests/unit/test_ingredient_service.py` — 무효화 호출 검증

**Interfaces:**
- Produces: `AiRecipeCache.list_key(user_id) -> str` = `ai_recipe_list:{user_id}`
- Produces: `async get_list(user_id) / set_list(user_id, record) / invalidate_list(user_id)`
- Produces: `ingredients_hash(names: list[str]) -> str` (sorted normalized join + sha256 hex[:16])
- Produces: `LIST_TTL_SECONDS = 1800` (30분)
- Produces: `GET /ai/recommendations?refresh=true`
- Consumes: Task 3 `recommend` generate path

- [ ] **Step 1: Write failing cache / API / invalidate tests**

```python
# test_ai_recipe_cache.py
async def test_list_cache_roundtrip(fake_redis):
    cache = AiRecipeCache(fake_redis, list_ttl_seconds=1800)
    record = AiRecipeListCacheRecord(
        ingredients_hash="abc",
        ingredients_used=["계란"],
        recipes=[...],  # 최소 1개 mock recommendation
    )
    await cache.set_list(user_id=1, record=record)
    got = await cache.get_list(1)
    assert got is not None
    assert got.ingredients_hash == "abc"
    await cache.invalidate_list(1)
    assert await cache.get_list(1) is None
```

Service: 동일 hash·`refresh=False`면 agent 미호출; `refresh=True`면 호출; 재료 이름 바뀌면 miss.

API: `?refresh=true`가 service.recommend(refresh=True)로 전달되는지 (기존 API 테스트 패턴).

IngredientService: add/update/delete/delete_all 후 `invalidate_list(user.id)` 1회 이상.

- [ ] **Step 2: Run — expect FAIL**

Run: `PYTHONPATH=src pytest tests/unit/test_ai_recipe_cache.py tests/unit/test_ai_recipe_service.py tests/api/test_ai_recipe_api.py tests/unit/test_ingredient_service.py -v`

Expected: FAIL

- [ ] **Step 3: Implement cache + wire-up**

`cache.py` 추가 메서드 (기존 recipe get/set 유지, Redis 예외 시 warning + None/no-op — 기존 패턴):

```python
LIST_TTL_SECONDS = 1800

def _list_key(self, user_id: int) -> str:
    return f"ai_recipe_list:{user_id}"

async def get_list(self, user_id: int) -> AiRecipeListCacheRecord | None: ...
async def set_list(self, user_id: int, record: AiRecipeListCacheRecord) -> None: ...
async def invalidate_list(self, user_id: int) -> None: ...
```

`service.recommend`:

```python
async def recommend(self, refresh: bool = False) -> AiRecipeRecommendationResponse:
    ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
    names = [item.ingredient_name for item in ingredients]
    if not names:
        return AiRecipeRecommendationResponse(ingredients_used=[], recipes=[])

    from domains.ingredient_matching.matching import normalize_name
    import hashlib
    digest = hashlib.sha256(
        ",".join(sorted(normalize_name(n) for n in names)).encode()
    ).hexdigest()[:16]

    if not refresh:
        cached = await self.cache.get_list(self.user.id)
        if cached is not None and cached.ingredients_hash == digest:
            return AiRecipeRecommendationResponse(
                ingredients_used=cached.ingredients_used,
                recipes=cached.recipes,
            )

    urgent = urgent_names(ingredients)
    candidates = await self._generate_list(names, urgent)
    # ... uuid + classify + per-recipe cache.set (기존)
    response = AiRecipeRecommendationResponse(...)
    await self.cache.set_list(
        self.user.id,
        AiRecipeListCacheRecord(
            ingredients_hash=digest,
            ingredients_used=names,
            recipes=response.recipes,
        ),
    )
    return response
```

엔드포인트:

```python
async def ai_recommend_recipes(
    refresh: bool = False,
    service: AiRecipeService = Depends(get_ai_recipe_service),
) -> AiRecipeRecommendationResponse:
    return await service.recommend(refresh=refresh)
```

`IngredientService.__init__(..., list_cache: AiRecipeCache | None = None)`  
CRUD 성공 직후:

```python
if self.list_cache is not None:
    await self.list_cache.invalidate_list(self.user.id)
```

`deps.get_ingredient_service`에서 `AiRecipeCache(get_redis())` 주입.

- [ ] **Step 4: Run — expect PASS**

Run: `PYTHONPATH=src pytest tests/unit/test_ai_recipe_cache.py tests/unit/test_ai_recipe_service.py tests/api/test_ai_recipe_api.py tests/unit/test_ingredient_service.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domains/ai_recipe src/domains/ingredient/service.py src/api/deps.py src/api/v1/endpoints/rag.py tests/
git commit -m "$(cat <<'EOF'
Feat: AI 목록 캐시·refresh·재료 변경 시 무효화

EOF
)"
```

---

### Task 5: 통합 회귀 · 스펙 성공 기준 확인

**Files:** none new (verification only)

- [ ] **Step 1: Run full related suite**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
PYTHONPATH=src pytest \
  tests/unit/test_ingredient_matching.py \
  tests/unit/test_rag_mapper.py \
  tests/unit/test_rag_service.py \
  tests/unit/test_ai_recipe_agent.py \
  tests/unit/test_ai_recipe_service.py \
  tests/unit/test_ai_recipe_cache.py \
  tests/unit/test_ai_recipe_schemas.py \
  tests/api/test_ai_recipe_api.py \
  tests/unit/test_ingredient_service.py \
  -v
```

Expected: all PASS

- [ ] **Step 2: Spec checklist**

| Criterion | Evidence |
|-----------|----------|
| 계란↔달걀 owned | Task 1 tests |
| urgent → RAG/AI | Task 2–3 |
| structured + ~25s + retry | Task 3 |
| cache hit / refresh bypass | Task 4 |
| CRUD invalidate | Task 4 |

- [ ] **Step 3: Commit only if verification fixes landed; otherwise done**

---

## Self-Review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| 공유 matching 레이어 | 1 |
| 동의어 + 부분일치(≥2) | 1 |
| classify RAG·AI 공통 | 1 (mapper 위임; AI service 기존 classify import 경로 유지) |
| urgency soon+expired | 2 |
| RAG 힌트+재정렬, urgent 시 TOP_K 고정 | 2 |
| AI structured 목록 + urgency 힌트 | 3 |
| timeout 20–25 + 1 retry | 3 |
| 목록 캐시 + refresh + CRUD 무효화 | 4 |
| RAG 폴백 없음 / 브레이킹 없음 | 3–4 |
| Out of scope (어드민, 임베딩, 스트리밍, 푸시) | 미포함 |

Placeholder scan: TBD/TODO 없음. 시그니처 `run_list(owned_names, urgent_names=None)`, `recommend(refresh=False)`, `urgent_names` / `count_urgent_owned` 일관.
