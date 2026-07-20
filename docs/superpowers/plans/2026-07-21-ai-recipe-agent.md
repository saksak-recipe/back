# AI Recipe Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 냉장고 재료 기반 OpenAI LangChain tool-calling 에이전트로 AI 레시피 목록·상세 API를 추가하고, 앱 레시피 화면에 「만개의 레시피」|「AI 레시피」탭을 넣는다. 만개 RAG/크롤은 변경하지 않는다.

**Architecture:** `domains/ai_recipe/`에서 재료 조회 → tool-calling 에이전트(후보 5개 제출·owned/missing 분류) → Redis `ai_recipe:{uuid}` 캐시. 상세는 캐시 miss expand 또는 hit. 앱은 동일 `recipes` 화면 탭 + `detail`의 `source=ai` 분기.

**Tech Stack:** FastAPI, Pydantic, Redis, LangChain Core tools + `ChatOpenAI.bind_tools` 수동 루프, pytest; Expo Router, TanStack Query, TypeScript

**Spec:** `docs/superpowers/specs/2026-07-21-ai-recipe-agent-design.md`

## Global Constraints

- 만개 API (`/recipes/recommendations`, `/recipes/detail`) 변경 금지
- AI 목록 기본 5개, 재료 0개면 LLM 미호출·빈 배열 200
- Redis 키 `ai_recipe:{recipe_id}`, TTL 86400초
- 최대 tool loop 8, 에이전트 타임아웃 60s
- owned/missing: `domains.rag.mapper.normalize_name` / `classify_ingredients` 재사용 (완전 일치)
- 모델 설정: `AI_RECIPE_MODEL` (기본 `gpt-4o-mini`)
- 커밋 스타일: `Feat:` / `Test:` / `Fix:` / `Docs:`
- 백엔드 작업 디렉터리: `/Users/jeong-yeonghun/Desktop/saksak/back`
- 앱 작업 디렉터리: `/Users/jeong-yeonghun/Desktop/saksak/app` (별도 git repo)

## File Structure

| Path | Responsibility |
|------|----------------|
| `back/src/core/config.py` | `AI_RECIPE_MODEL` |
| `back/src/domains/ai_recipe/schemas.py` | 목록/상세/캐시 DTO |
| `back/src/domains/ai_recipe/cache.py` | Redis get/set |
| `back/src/domains/ai_recipe/tools.py` | LangChain `@tool` + AgentSession 상태 |
| `back/src/domains/ai_recipe/agent.py` | ChatOpenAI tool-calling 루프 |
| `back/src/domains/ai_recipe/service.py` | 목록/상세 오케스트레이션 |
| `back/src/api/deps.py` | `get_ai_recipe_service` |
| `back/src/api/v1/endpoints/rag.py` | `/ai/recommendations`, `/ai/detail` 추가 (기존 prefix `/recipes`) |
| `back/tests/unit/test_ai_recipe_*.py` | 단위 테스트 |
| `back/tests/api/test_ai_recipe_api.py` | API 테스트 |
| `app/src/types/api.ts` | AI 타입 |
| `app/src/api/recipes.ts` | AI 클라이언트 |
| `app/src/components/RecipeCard.tsx` | 공통 카드 props |
| `app/src/app/(main)/recipes/index.tsx` | 탭 UI |
| `app/src/app/(main)/recipes/detail.tsx` | `source=ai` 분기 |

---

### Task 1: Config + Schemas

**Files:**
- Modify: `src/core/config.py`
- Create: `src/domains/ai_recipe/__init__.py` (empty)
- Create: `src/domains/ai_recipe/schemas.py`
- Test: `tests/unit/test_ai_recipe_schemas.py`

**Interfaces:**
- Produces: `Settings.AI_RECIPE_MODEL: str = "gpt-4o-mini"`
- Produces: `AiRecipeCandidate`, `AiRecipeCacheRecord`, `AiRecipeRecommendation`, `AiRecipeRecommendationResponse`, `AiRecipeIngredient`, `AiRecipeStep`, `AiRecipeDetailResponse`

- [ ] **Step 1: Write schema round-trip test**

```python
# tests/unit/test_ai_recipe_schemas.py
from domains.ai_recipe.schemas import (
    AiRecipeCacheRecord,
    AiRecipeRecommendation,
    AiRecipeRecommendationResponse,
)


def test_recommendation_response_roundtrip():
    body = AiRecipeRecommendationResponse(
        ingredients_used=["계란"],
        recipes=[
            AiRecipeRecommendation(
                recipe_id="11111111-1111-1111-1111-111111111111",
                recipe_name="계란볶음밥",
                owned_ingredients=["계란"],
                missing_ingredients=["밥"],
                recipe_difficulty="초급",
                time="15분",
            )
        ],
    )
    assert body.recipes[0].source == "ai"
    raw = body.model_dump_json()
    assert AiRecipeRecommendationResponse.model_validate_json(raw) == body


def test_cache_record_optional_detail():
    record = AiRecipeCacheRecord(
        recipe_id="11111111-1111-1111-1111-111111111111",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란", "밥"],
        owned_ingredients=["계란"],
        missing_ingredients=["밥"],
        recipe_difficulty="초급",
        time="15분",
    )
    assert record.ingredients is None
    assert record.steps is None
    assert record.tips is None
```

- [ ] **Step 2: Run test — expect FAIL (module missing)**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv run pytest tests/unit/test_ai_recipe_schemas.py -v
```

Expected: `ModuleNotFoundError` or import error for `domains.ai_recipe`

- [ ] **Step 3: Implement schemas + config**

`src/core/config.py` — `OPENAI_API_KEY` 아래에:

```python
AI_RECIPE_MODEL: str = "gpt-4o-mini"
```

`src/domains/ai_recipe/schemas.py`:

```python
from pydantic import BaseModel, Field


class AiRecipeCandidate(BaseModel):
    """에이전트가 propose_recipe_candidates로 제출하는 후보."""

    recipe_name: str
    recipe_ingredients: list[str] = Field(default_factory=list)
    recipe_difficulty: str = ""
    time: str = ""


class AiRecipeIngredient(BaseModel):
    name: str
    amount: str = ""


class AiRecipeStep(BaseModel):
    order: int
    description: str


class AiRecipeRecommendation(BaseModel):
    recipe_id: str
    recipe_name: str
    owned_ingredients: list[str] = Field(default_factory=list)
    missing_ingredients: list[str] = Field(default_factory=list)
    recipe_difficulty: str = ""
    time: str = ""
    source: str = "ai"


class AiRecipeRecommendationResponse(BaseModel):
    ingredients_used: list[str]
    recipes: list[AiRecipeRecommendation]


class AiRecipeCacheRecord(BaseModel):
    recipe_id: str
    recipe_name: str
    recipe_ingredients: list[str] = Field(default_factory=list)
    owned_ingredients: list[str] = Field(default_factory=list)
    missing_ingredients: list[str] = Field(default_factory=list)
    recipe_difficulty: str = ""
    time: str = ""
    # 상세 확장 전 None
    ingredients: list[AiRecipeIngredient] | None = None
    steps: list[AiRecipeStep] | None = None
    tips: list[str] | None = None

    def has_detail(self) -> bool:
        return self.ingredients is not None and self.steps is not None


class AiRecipeDetailResponse(BaseModel):
    recipe_id: str
    recipe_name: str
    source: str = "ai"
    ingredients: list[AiRecipeIngredient] = Field(default_factory=list)
    steps: list[AiRecipeStep] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)
    owned_ingredients: list[str] = Field(default_factory=list)
    missing_ingredients: list[str] = Field(default_factory=list)
    cached: bool = False
```

`src/domains/ai_recipe/__init__.py`: empty file.

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/unit/test_ai_recipe_schemas.py -v
```

- [ ] **Step 5: Commit (back repo)**

```bash
git add src/core/config.py src/domains/ai_recipe tests/unit/test_ai_recipe_schemas.py
git commit -m "$(cat <<'EOF'
Feat: AI 레시피 스키마 및 모델 설정 추가

EOF
)"
```

---

### Task 2: Redis Cache (TDD)

**Files:**
- Create: `src/domains/ai_recipe/cache.py`
- Test: `tests/unit/test_ai_recipe_cache.py`

**Interfaces:**
- Consumes: `AiRecipeCacheRecord`
- Produces: `AiRecipeCache` with `async get(recipe_id: str) -> AiRecipeCacheRecord | None`, `async set(record: AiRecipeCacheRecord) -> None`
- Redis key: `ai_recipe:{recipe_id}`, TTL default 86400

- [ ] **Step 1: Write failing cache tests**

```python
# tests/unit/test_ai_recipe_cache.py
import fakeredis.aioredis
import pytest

from domains.ai_recipe.cache import AiRecipeCache
from domains.ai_recipe.schemas import AiRecipeCacheRecord


@pytest.fixture
def cache():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return AiRecipeCache(redis, ttl_seconds=86400)


async def test_set_get_roundtrip(cache: AiRecipeCache):
    record = AiRecipeCacheRecord(
        recipe_id="11111111-1111-1111-1111-111111111111",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란", "밥"],
        owned_ingredients=["계란"],
        missing_ingredients=["밥"],
        recipe_difficulty="초급",
        time="15분",
    )
    await cache.set(record)
    got = await cache.get(record.recipe_id)
    assert got is not None
    assert got.recipe_name == "계란볶음밥"
    assert got.has_detail() is False


async def test_get_missing_returns_none(cache: AiRecipeCache):
    assert await cache.get("00000000-0000-0000-0000-000000000000") is None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_ai_recipe_cache.py -v
```

- [ ] **Step 3: Implement cache**

```python
# src/domains/ai_recipe/cache.py
from loguru import logger
from redis.asyncio import Redis

from domains.ai_recipe.schemas import AiRecipeCacheRecord

TTL_SECONDS = 86400


class AiRecipeCache:
    def __init__(self, redis: Redis, ttl_seconds: int = TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    def _key(self, recipe_id: str) -> str:
        return f"ai_recipe:{recipe_id}"

    async def get(self, recipe_id: str) -> AiRecipeCacheRecord | None:
        try:
            raw = await self._redis.get(self._key(recipe_id))
        except Exception:
            logger.warning("ai recipe cache get failed")
            return None
        if raw is None:
            return None
        try:
            return AiRecipeCacheRecord.model_validate_json(raw)
        except Exception:
            logger.warning("ai recipe cache decode failed")
            return None

    async def set(self, record: AiRecipeCacheRecord) -> None:
        try:
            await self._redis.set(
                self._key(record.recipe_id),
                record.model_dump_json(),
                ex=self._ttl,
            )
        except Exception:
            logger.warning("ai recipe cache set failed")
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/test_ai_recipe_cache.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/domains/ai_recipe/cache.py tests/unit/test_ai_recipe_cache.py
git commit -m "$(cat <<'EOF'
Feat: AI 레시피 Redis 캐시 추가

EOF
)"
```

---

### Task 3: Agent Tools + Session (TDD)

**Files:**
- Create: `src/domains/ai_recipe/tools.py`
- Test: `tests/unit/test_ai_recipe_tools.py`

**Interfaces:**
- Produces: `AgentSession` (mutable state: `owned_names`, `candidates: list[AiRecipeCandidate]`, `detail: ...`)
- Produces: `build_tools(session: AgentSession) -> list` of LangChain tools:
  - `get_user_ingredients`
  - `propose_recipe_candidates` (args: recipes list, length must be 5)
  - `classify_owned_missing` (recipe_ingredients → owned/missing JSON)
  - `expand_recipe_detail` (ingredients, steps, tips)

- [ ] **Step 1: Write tool tests**

```python
# tests/unit/test_ai_recipe_tools.py
import json

from domains.ai_recipe.schemas import AiRecipeCandidate
from domains.ai_recipe.tools import AgentSession, build_tools


def _tool_map(session: AgentSession):
    return {t.name: t for t in build_tools(session)}


def test_get_user_ingredients():
    session = AgentSession(owned_names=["계란", "양파"])
    tools = _tool_map(session)
    result = tools["get_user_ingredients"].invoke({})
    assert json.loads(result) == ["계란", "양파"]


def test_propose_recipe_candidates_stores_five():
    session = AgentSession(owned_names=["계란"])
    tools = _tool_map(session)
    payload = {
        "recipes": [
            {
                "recipe_name": f"요리{i}",
                "recipe_ingredients": ["계란", "밥"],
                "recipe_difficulty": "초급",
                "time": "10분",
            }
            for i in range(5)
        ]
    }
    result = tools["propose_recipe_candidates"].invoke(payload)
    assert "ok" in result.lower() or "5" in result
    assert len(session.candidates) == 5
    assert session.candidates[0].recipe_name == "요리0"


def test_propose_rejects_wrong_count():
    session = AgentSession(owned_names=["계란"])
    tools = _tool_map(session)
    result = tools["propose_recipe_candidates"].invoke(
        {"recipes": [{"recipe_name": "하나만", "recipe_ingredients": ["계란"]}]}
    )
    assert "5" in result  # error mentioning need 5
    assert session.candidates == []


def test_classify_owned_missing():
    session = AgentSession(owned_names=["계란", "양파"])
    tools = _tool_map(session)
    result = json.loads(
        tools["classify_owned_missing"].invoke(
            {"recipe_ingredients": ["계란", "밥", "양파"]}
        )
    )
    assert result["owned_ingredients"] == ["계란", "양파"]
    assert result["missing_ingredients"] == ["밥"]


def test_expand_recipe_detail_stores():
    session = AgentSession(owned_names=["계란"])
    tools = _tool_map(session)
    tools["expand_recipe_detail"].invoke(
        {
            "ingredients": [{"name": "계란", "amount": "2개"}],
            "steps": [{"order": 1, "description": "볶는다"}],
            "tips": ["약불"],
        }
    )
    assert session.detail is not None
    assert session.detail["tips"] == ["약불"]
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_ai_recipe_tools.py -v
```

- [ ] **Step 3: Implement tools**

```python
# src/domains/ai_recipe/tools.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import tool

from domains.ai_recipe.schemas import AiRecipeCandidate, AiRecipeIngredient, AiRecipeStep
from domains.rag.mapper import classify_ingredients

TOP_K = 5


@dataclass
class AgentSession:
    owned_names: list[str]
    candidates: list[AiRecipeCandidate] = field(default_factory=list)
    detail: dict[str, Any] | None = None


def build_tools(session: AgentSession):
    @tool
    def get_user_ingredients() -> str:
        """Return the user's fridge ingredient names as JSON list."""
        return json.dumps(session.owned_names, ensure_ascii=False)

    @tool
    def classify_owned_missing(recipe_ingredients: list[str]) -> str:
        """Classify recipe ingredients into owned vs missing using exact normalized match."""
        owned, missing = classify_ingredients(recipe_ingredients, session.owned_names)
        return json.dumps(
            {"owned_ingredients": owned, "missing_ingredients": missing},
            ensure_ascii=False,
        )

    @tool
    def propose_recipe_candidates(recipes: list[dict[str, Any]]) -> str:
        """Submit exactly 5 recipe candidates. Each needs recipe_name, recipe_ingredients, recipe_difficulty, time."""
        if len(recipes) != TOP_K:
            return f"error: must propose exactly {TOP_K} recipes, got {len(recipes)}"
        parsed: list[AiRecipeCandidate] = []
        for item in recipes:
            parsed.append(AiRecipeCandidate.model_validate(item))
        session.candidates = parsed
        return f"ok: stored {TOP_K} candidates"

    @tool
    def expand_recipe_detail(
        ingredients: list[dict[str, Any]],
        steps: list[dict[str, Any]],
        tips: list[str] | None = None,
    ) -> str:
        """Submit full recipe detail: ingredients[{name,amount}], steps[{order,description}], tips."""
        parsed_ingredients = [AiRecipeIngredient.model_validate(i) for i in ingredients]
        parsed_steps = [AiRecipeStep.model_validate(s) for s in steps]
        session.detail = {
            "ingredients": parsed_ingredients,
            "steps": parsed_steps,
            "tips": tips or [],
        }
        return "ok: detail stored"

    return [
        get_user_ingredients,
        classify_owned_missing,
        propose_recipe_candidates,
        expand_recipe_detail,
    ]
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/test_ai_recipe_tools.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/domains/ai_recipe/tools.py tests/unit/test_ai_recipe_tools.py
git commit -m "$(cat <<'EOF'
Feat: AI 레시피 에이전트 도구 추가

EOF
)"
```

---

### Task 4: Agent Loop (TDD)

**Files:**
- Create: `src/domains/ai_recipe/agent.py`
- Test: `tests/unit/test_ai_recipe_agent.py`

**Interfaces:**
- Produces: `AiRecipeAgent.run_list(owned_names: list[str]) -> list[AiRecipeCandidate]`
- Produces: `AiRecipeAgent.run_detail(owned_names, summary: AiRecipeCacheRecord) -> dict` (ingredients/steps/tips)
- Constraints: max 8 tool iterations; wrap OpenAI errors as cause for caller to map to 502
- Implementation: `ChatOpenAI.bind_tools` + manual message loop (no LangGraph). LLM이 도구를 안 부르고 끝나면, session에 candidates/detail이 없으면 `ExternalServiceException`에 가까운 런타임 에러 raise → service에서 502 매핑.

- [ ] **Step 1: Write agent tests with mocked LLM**

에이전트는 `llm`을 주입받아 테스트에서 fake AIMessage(tool_calls) 시퀀스를 반환하게 한다.

```python
# tests/unit/test_ai_recipe_agent.py
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from domains.ai_recipe.agent import AiRecipeAgent, AgentFailedError
from domains.ai_recipe.schemas import AiRecipeCacheRecord


def _five_recipes():
    return [
        {
            "recipe_name": f"요리{i}",
            "recipe_ingredients": ["계란", "밥"],
            "recipe_difficulty": "초급",
            "time": "10분",
        }
        for i in range(5)
    ]


def test_run_list_uses_tools_and_returns_candidates():
    llm = MagicMock()
    # 1) tool call propose  2) final stop
    llm.bind_tools.return_value = llm
    llm.invoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "propose_recipe_candidates",
                    "args": {"recipes": _five_recipes()},
                    "id": "call_1",
                }
            ],
        ),
        AIMessage(content="done"),
    ]
    agent = AiRecipeAgent(llm=llm, model_name="gpt-4o-mini")
    candidates = agent.run_list(["계란"])
    assert len(candidates) == 5
    assert candidates[0].recipe_name == "요리0"


def test_run_list_raises_when_no_candidates():
    llm = MagicMock()
    llm.bind_tools.return_value = llm
    llm.invoke.return_value = AIMessage(content="sorry")
    agent = AiRecipeAgent(llm=llm, model_name="gpt-4o-mini")
    with pytest.raises(AgentFailedError):
        agent.run_list(["계란"])


def test_run_detail_expands():
    llm = MagicMock()
    llm.bind_tools.return_value = llm
    llm.invoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "expand_recipe_detail",
                    "args": {
                        "ingredients": [{"name": "계란", "amount": "2개"}],
                        "steps": [{"order": 1, "description": "볶는다"}],
                        "tips": ["약불"],
                    },
                    "id": "call_1",
                }
            ],
        ),
        AIMessage(content="done"),
    ]
    agent = AiRecipeAgent(llm=llm, model_name="gpt-4o-mini")
    summary = AiRecipeCacheRecord(
        recipe_id="11111111-1111-1111-1111-111111111111",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란", "밥"],
        owned_ingredients=["계란"],
        missing_ingredients=["밥"],
        recipe_difficulty="초급",
        time="15분",
    )
    detail = agent.run_detail(["계란"], summary)
    assert detail["tips"] == ["약불"]
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_ai_recipe_agent.py -v
```

- [ ] **Step 3: Implement agent**

```python
# src/domains/ai_recipe/agent.py
from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from core.config import settings
from domains.ai_recipe.schemas import AiRecipeCacheRecord, AiRecipeCandidate
from domains.ai_recipe.tools import AgentSession, TOP_K, build_tools

MAX_TOOL_LOOPS = 8


class AgentFailedError(Exception):
    """에이전트가 유효한 결과를 만들지 못함."""


LIST_SYSTEM = (
    "You are a Korean home-cooking assistant. "
    f"Use tools to inspect ingredients and propose exactly {TOP_K} recipes "
    "the user can mostly cook with fridge items. "
    "Always call propose_recipe_candidates with exactly "
    f"{TOP_K} recipes before finishing."
)

DETAIL_SYSTEM = (
    "You are a Korean home-cooking assistant. "
    "Expand the given recipe summary into concrete ingredient amounts, "
    "ordered cooking steps, and optional tips. "
    "Always call expand_recipe_detail before finishing."
)


class AiRecipeAgent:
    def __init__(
        self,
        llm: BaseChatModel | None = None,
        model_name: str | None = None,
    ) -> None:
        self._model_name = model_name or settings.AI_RECIPE_MODEL
        self._llm = llm or ChatOpenAI(
            model=self._model_name,
            api_key=settings.OPENAI_API_KEY.get_secret_value(),
            timeout=60,
        )

    def run_list(self, owned_names: list[str]) -> list[AiRecipeCandidate]:
        session = AgentSession(owned_names=owned_names)
        tools = build_tools(session)
        self._run(
            system=LIST_SYSTEM,
            user=(
                "Propose recipes for these fridge ingredients. "
                f"Call get_user_ingredients first if needed."
            ),
            tools=tools,
            session=session,
        )
        if len(session.candidates) != TOP_K:
            raise AgentFailedError("agent did not propose 5 candidates")
        return session.candidates

    def run_detail(
        self, owned_names: list[str], summary: AiRecipeCacheRecord
    ) -> dict[str, Any]:
        session = AgentSession(owned_names=owned_names)
        tools = build_tools(session)
        self._run(
            system=DETAIL_SYSTEM,
            user=(
                f"Recipe: {summary.recipe_name}\n"
                f"Ingredients: {', '.join(summary.recipe_ingredients)}\n"
                f"Difficulty: {summary.recipe_difficulty}\n"
                f"Time: {summary.time}\n"
                "Call expand_recipe_detail with amounts, steps, tips."
            ),
            tools=tools,
            session=session,
        )
        if session.detail is None:
            raise AgentFailedError("agent did not expand detail")
        return session.detail

    def _run(
        self,
        *,
        system: str,
        user: str,
        tools: list,
        session: AgentSession,
    ) -> None:
        tool_map = {t.name: t for t in tools}
        llm = self._llm.bind_tools(tools)
        messages: list = [SystemMessage(content=system), HumanMessage(content=user)]
        for _ in range(MAX_TOOL_LOOPS):
            ai: AIMessage = llm.invoke(messages)
            messages.append(ai)
            if not ai.tool_calls:
                return
            for call in ai.tool_calls:
                name = call["name"]
                args = call.get("args") or {}
                tool = tool_map.get(name)
                if tool is None:
                    output = f"error: unknown tool {name}"
                else:
                    output = tool.invoke(args)
                messages.append(
                    ToolMessage(content=str(output), tool_call_id=call["id"])
                )
        # loop exhausted — leave session as-is; caller validates
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/test_ai_recipe_agent.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/domains/ai_recipe/agent.py tests/unit/test_ai_recipe_agent.py
git commit -m "$(cat <<'EOF'
Feat: AI 레시피 tool-calling 에이전트 루프 추가

EOF
)"
```

---

### Task 5: AiRecipeService (TDD)

**Files:**
- Create: `src/domains/ai_recipe/service.py`
- Test: `tests/unit/test_ai_recipe_service.py`

**Interfaces:**
- Consumes: `IngredientRepository`, `AiRecipeAgent`, `AiRecipeCache`, `User`
- Produces:
  - `async recommend() -> AiRecipeRecommendationResponse`
  - `async get_detail(recipe_id: str) -> AiRecipeDetailResponse`
- Empty ingredients → no agent call
- Agent/OpenAI failure → `ExternalServiceException`
- Cache miss on detail → `NotFoundException`
- On list: uuid4 per candidate, classify via `classify_ingredients`, cache each summary

- [ ] **Step 1: Write service tests**

```python
# tests/unit/test_ai_recipe_service.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.exception.exceptions import ExternalServiceException, NotFoundException
from domains.ai_recipe.agent import AgentFailedError
from domains.ai_recipe.schemas import (
    AiRecipeCacheRecord,
    AiRecipeCandidate,
    AiRecipeIngredient,
    AiRecipeStep,
)
from domains.ai_recipe.service import AiRecipeService


@pytest.fixture
def user():
    u = MagicMock()
    u.id = "user-1"
    return u


async def test_recommend_empty_skips_agent(user):
    repo = AsyncMock()
    repo.get_ingredients.return_value = []
    agent = MagicMock()
    cache = AsyncMock()
    service = AiRecipeService(user=user, ingredient_repo=repo, agent=agent, cache=cache)
    result = await service.recommend()
    assert result.recipes == []
    agent.run_list.assert_not_called()


async def test_recommend_caches_five(user):
    repo = AsyncMock()
    item = MagicMock()
    item.ingredient_name = "계란"
    repo.get_ingredients.return_value = [item]
    agent = MagicMock()
    agent.run_list.return_value = [
        AiRecipeCandidate(
            recipe_name=f"요리{i}",
            recipe_ingredients=["계란", "밥"],
            recipe_difficulty="초급",
            time="10분",
        )
        for i in range(5)
    ]
    cache = AsyncMock()
    service = AiRecipeService(user=user, ingredient_repo=repo, agent=agent, cache=cache)
    result = await service.recommend()
    assert len(result.recipes) == 5
    assert result.recipes[0].owned_ingredients == ["계란"]
    assert result.recipes[0].missing_ingredients == ["밥"]
    assert result.recipes[0].source == "ai"
    assert cache.set.await_count == 5


async def test_recommend_maps_agent_failure(user):
    repo = AsyncMock()
    item = MagicMock()
    item.ingredient_name = "계란"
    repo.get_ingredients.return_value = [item]
    agent = MagicMock()
    agent.run_list.side_effect = AgentFailedError("fail")
    cache = AsyncMock()
    service = AiRecipeService(user=user, ingredient_repo=repo, agent=agent, cache=cache)
    with pytest.raises(ExternalServiceException):
        await service.recommend()


async def test_detail_not_found(user):
    cache = AsyncMock()
    cache.get.return_value = None
    service = AiRecipeService(
        user=user,
        ingredient_repo=AsyncMock(),
        agent=MagicMock(),
        cache=cache,
    )
    with pytest.raises(NotFoundException):
        await service.get_detail("missing-id")


async def test_detail_cache_hit(user):
    cache = AsyncMock()
    cache.get.return_value = AiRecipeCacheRecord(
        recipe_id="rid",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란"],
        owned_ingredients=["계란"],
        missing_ingredients=[],
        recipe_difficulty="초급",
        time="10분",
        ingredients=[AiRecipeIngredient(name="계란", amount="2개")],
        steps=[AiRecipeStep(order=1, description="볶는다")],
        tips=["약불"],
    )
    agent = MagicMock()
    service = AiRecipeService(
        user=user, ingredient_repo=AsyncMock(), agent=agent, cache=cache
    )
    result = await service.get_detail("rid")
    assert result.cached is True
    agent.run_detail.assert_not_called()


async def test_detail_expands_when_missing(user):
    cache = AsyncMock()
    summary = AiRecipeCacheRecord(
        recipe_id="rid",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란", "밥"],
        owned_ingredients=["계란"],
        missing_ingredients=["밥"],
        recipe_difficulty="초급",
        time="10분",
    )
    cache.get.return_value = summary
    agent = MagicMock()
    agent.run_detail.return_value = {
        "ingredients": [AiRecipeIngredient(name="계란", amount="2개")],
        "steps": [AiRecipeStep(order=1, description="볶는다")],
        "tips": ["약불"],
    }
    repo = AsyncMock()
    item = MagicMock()
    item.ingredient_name = "계란"
    repo.get_ingredients.return_value = [item]
    service = AiRecipeService(user=user, ingredient_repo=repo, agent=agent, cache=cache)
    result = await service.get_detail("rid")
    assert result.cached is False
    assert result.steps[0].description == "볶는다"
    cache.set.assert_awaited()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/unit/test_ai_recipe_service.py -v
```

- [ ] **Step 3: Implement service**

```python
# src/domains/ai_recipe/service.py
from __future__ import annotations

import asyncio
import uuid

import openai

from core.exception.exceptions import ExternalServiceException, NotFoundException
from domains.ai_recipe.agent import AgentFailedError, AiRecipeAgent
from domains.ai_recipe.cache import AiRecipeCache
from domains.ai_recipe.schemas import (
    AiRecipeCacheRecord,
    AiRecipeDetailResponse,
    AiRecipeRecommendation,
    AiRecipeRecommendationResponse,
)
from domains.ingredient.repository import IngredientRepository
from domains.rag.mapper import classify_ingredients
from domains.user.model import User


class AiRecipeService:
    def __init__(
        self,
        user: User,
        ingredient_repo: IngredientRepository,
        agent: AiRecipeAgent,
        cache: AiRecipeCache,
    ) -> None:
        self.user = user
        self.ingredient_repo = ingredient_repo
        self.agent = agent
        self.cache = cache

    async def recommend(self) -> AiRecipeRecommendationResponse:
        ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
        names = [item.ingredient_name for item in ingredients]
        if not names:
            return AiRecipeRecommendationResponse(ingredients_used=[], recipes=[])

        try:
            candidates = await asyncio.to_thread(self.agent.run_list, names)
        except (AgentFailedError, openai.OpenAIError) as e:
            raise ExternalServiceException(
                detail="AI 레시피 생성에 실패했습니다."
            ) from e

        recipes: list[AiRecipeRecommendation] = []
        for candidate in candidates:
            recipe_id = str(uuid.uuid4())
            owned, missing = classify_ingredients(
                candidate.recipe_ingredients, names
            )
            record = AiRecipeCacheRecord(
                recipe_id=recipe_id,
                recipe_name=candidate.recipe_name,
                recipe_ingredients=candidate.recipe_ingredients,
                owned_ingredients=owned,
                missing_ingredients=missing,
                recipe_difficulty=candidate.recipe_difficulty,
                time=candidate.time,
            )
            await self.cache.set(record)
            recipes.append(
                AiRecipeRecommendation(
                    recipe_id=recipe_id,
                    recipe_name=candidate.recipe_name,
                    owned_ingredients=owned,
                    missing_ingredients=missing,
                    recipe_difficulty=candidate.recipe_difficulty,
                    time=candidate.time,
                )
            )
        return AiRecipeRecommendationResponse(
            ingredients_used=names, recipes=recipes
        )

    async def get_detail(self, recipe_id: str) -> AiRecipeDetailResponse:
        record = await self.cache.get(recipe_id)
        if record is None:
            raise NotFoundException(detail="AI 레시피를 찾지 못했습니다.")

        if record.has_detail():
            return AiRecipeDetailResponse(
                recipe_id=record.recipe_id,
                recipe_name=record.recipe_name,
                ingredients=record.ingredients or [],
                steps=record.steps or [],
                tips=record.tips or [],
                owned_ingredients=record.owned_ingredients,
                missing_ingredients=record.missing_ingredients,
                cached=True,
            )

        ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
        names = [item.ingredient_name for item in ingredients]
        try:
            detail = await asyncio.to_thread(self.agent.run_detail, names, record)
        except (AgentFailedError, openai.OpenAIError) as e:
            raise ExternalServiceException(
                detail="AI 레시피 상세 생성에 실패했습니다."
            ) from e

        updated = record.model_copy(
            update={
                "ingredients": detail["ingredients"],
                "steps": detail["steps"],
                "tips": detail["tips"],
            }
        )
        await self.cache.set(updated)
        return AiRecipeDetailResponse(
            recipe_id=updated.recipe_id,
            recipe_name=updated.recipe_name,
            ingredients=updated.ingredients or [],
            steps=updated.steps or [],
            tips=updated.tips or [],
            owned_ingredients=updated.owned_ingredients,
            missing_ingredients=updated.missing_ingredients,
            cached=False,
        )
```

`NotFoundException` / `ExternalServiceException` 생성자 시그니처가 프로젝트와 다르면 기존 예외 클래스 사용법에 맞춰 조정한다 (`grep NotFoundException` in `src/core/exception`).

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/unit/test_ai_recipe_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/domains/ai_recipe/service.py tests/unit/test_ai_recipe_service.py
git commit -m "$(cat <<'EOF'
Feat: AI 레시피 서비스 목록·상세 오케스트레이션

EOF
)"
```

---

### Task 6: API Endpoints + DI (TDD)

**Files:**
- Modify: `src/api/deps.py`
- Modify: `src/api/v1/endpoints/rag.py`
- Test: `tests/api/test_ai_recipe_api.py`

**Interfaces:**
- `GET /api/v1/recipes/ai/recommendations` → `AiRecipeRecommendationResponse`
- `GET /api/v1/recipes/ai/detail?recipe_id=` → `AiRecipeDetailResponse`
- `get_ai_recipe_service` Depends JWT + repo + cache + default agent

- [ ] **Step 1: Write API tests**

```python
# tests/api/test_ai_recipe_api.py
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from api.deps import get_ai_recipe_service
from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException, NotFoundException
from domains.ai_recipe.schemas import (
    AiRecipeDetailResponse,
    AiRecipeRecommendation,
    AiRecipeRecommendationResponse,
)
from main import app


async def test_ai_recommendations_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/recipes/ai/recommendations")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_ai_recommendations_empty(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock = MagicMock()
    mock.recommend = AsyncMock(
        return_value=AiRecipeRecommendationResponse(
            ingredients_used=[], recipes=[]
        )
    )
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/recommendations", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["recipes"] == []
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)


async def test_ai_recommendations_success(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock = MagicMock()
    mock.recommend = AsyncMock(
        return_value=AiRecipeRecommendationResponse(
            ingredients_used=["계란"],
            recipes=[
                AiRecipeRecommendation(
                    recipe_id="rid",
                    recipe_name="계란볶음밥",
                    owned_ingredients=["계란"],
                    missing_ingredients=["밥"],
                    recipe_difficulty="초급",
                    time="10분",
                )
            ],
        )
    )
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/recommendations", headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body["recipes"][0]["source"] == "ai"
        assert body["recipes"][0]["recipe_id"] == "rid"
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)


async def test_ai_detail_404(client: AsyncClient, auth_headers: dict[str, str]):
    mock = MagicMock()
    mock.get_detail = AsyncMock(side_effect=NotFoundException())
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/detail",
            headers=auth_headers,
            params={"recipe_id": "missing"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)


async def test_ai_detail_502(client: AsyncClient, auth_headers: dict[str, str]):
    mock = MagicMock()
    mock.get_detail = AsyncMock(side_effect=ExternalServiceException())
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/detail",
            headers=auth_headers,
            params={"recipe_id": "rid"},
        )
        assert response.status_code == 502
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)


async def test_ai_detail_success(client: AsyncClient, auth_headers: dict[str, str]):
    mock = MagicMock()
    mock.get_detail = AsyncMock(
        return_value=AiRecipeDetailResponse(
            recipe_id="rid",
            recipe_name="계란볶음밥",
            ingredients=[],
            steps=[],
            tips=[],
            owned_ingredients=["계란"],
            missing_ingredients=[],
            cached=True,
        )
    )
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/detail",
            headers=auth_headers,
            params={"recipe_id": "rid"},
        )
        assert response.status_code == 200
        assert response.json()["cached"] is True
        assert response.json()["source"] == "ai"
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)
```

예외 생성자가 `detail=` 필수를 요구하면 테스트의 `NotFoundException()` / `ExternalServiceException()` 호출을 기존 테스트(`tests/api/test_recipe_detail_api.py`)와 동일하게 맞춘다.

- [ ] **Step 2: Run — expect FAIL (deps missing)**

```bash
uv run pytest tests/api/test_ai_recipe_api.py -v
```

- [ ] **Step 3: Wire deps + endpoints**

`src/api/deps.py` 추가:

```python
from domains.ai_recipe.agent import AiRecipeAgent
from domains.ai_recipe.cache import AiRecipeCache
from domains.ai_recipe.service import AiRecipeService


def get_ai_recipe_service(
    user: User = Depends(get_current_user),
    ingredient_repo: IngredientRepository = Depends(get_ingredient_repo),
) -> AiRecipeService:
    cache = AiRecipeCache(get_redis(), ttl_seconds=86400)
    return AiRecipeService(
        user=user,
        ingredient_repo=ingredient_repo,
        agent=AiRecipeAgent(),
        cache=cache,
    )
```

`src/api/v1/endpoints/rag.py`에 엔드포인트 추가 (기존 핸들러는 수정하지 않음):

```python
from api.deps import get_ai_recipe_service
from domains.ai_recipe.schemas import (
    AiRecipeDetailResponse,
    AiRecipeRecommendationResponse,
)
from domains.ai_recipe.service import AiRecipeService


@router.get(
    "/ai/recommendations",
    status_code=status.HTTP_200_OK,
    summary="AI 에이전트 레시피 추천",
    response_model=AiRecipeRecommendationResponse,
    responses=create_error_response(
        UnAuthorizedException,
        ExternalServiceException,
        DatabaseException,
    ),
)
async def ai_recommend_recipes(
    service: AiRecipeService = Depends(get_ai_recipe_service),
) -> AiRecipeRecommendationResponse:
    return await service.recommend()


@router.get(
    "/ai/detail",
    status_code=status.HTTP_200_OK,
    summary="AI 에이전트 레시피 상세",
    response_model=AiRecipeDetailResponse,
    responses=create_error_response(
        UnAuthorizedException,
        NotFoundException,
        ExternalServiceException,
    ),
)
async def ai_recipe_detail(
    recipe_id: str,
    service: AiRecipeService = Depends(get_ai_recipe_service),
) -> AiRecipeDetailResponse:
    return await service.get_detail(recipe_id)
```

- [ ] **Step 4: Run all AI + existing recipe tests**

```bash
uv run pytest tests/unit/test_ai_recipe_*.py tests/api/test_ai_recipe_api.py tests/api/test_rag_api.py tests/api/test_recipe_detail_api.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/deps.py src/api/v1/endpoints/rag.py tests/api/test_ai_recipe_api.py
git commit -m "$(cat <<'EOF'
Feat: AI 레시피 추천·상세 API 엔드포인트 추가

EOF
)"
```

---

### Task 7: App types + API client

**Files (app repo):**
- Modify: `src/types/api.ts`
- Modify: `src/api/recipes.ts`

**Interfaces:**
- Produces: `AiRecipeRecommendation`, `AiRecipeRecommendationResponse`, `AiRecipeDetail`
- Produces: `getAiRecipeRecommendations()`, `getAiRecipeDetail(recipeId: string)`

- [ ] **Step 1: Add types to `src/types/api.ts`**

```typescript
export type AiRecipeRecommendation = {
  recipe_id: string;
  recipe_name: string;
  owned_ingredients: string[];
  missing_ingredients: string[];
  recipe_difficulty: string;
  time: string;
  source: 'ai';
};

export type AiRecipeRecommendationResponse = {
  ingredients_used: string[];
  recipes: AiRecipeRecommendation[];
};

export type AiRecipeDetail = {
  recipe_id: string;
  recipe_name: string;
  source: 'ai';
  ingredients: RecipeIngredient[];
  steps: RecipeStep[];
  tips: string[];
  owned_ingredients: string[];
  missing_ingredients: string[];
  cached: boolean;
};
```

- [ ] **Step 2: Add client functions in `src/api/recipes.ts`**

```typescript
import type {
  AiRecipeDetail,
  AiRecipeRecommendationResponse,
  RecipeDetail,
  RecipeRecommendationResponse,
} from '@/types/api';

export async function getAiRecipeRecommendations(): Promise<AiRecipeRecommendationResponse> {
  const { data } = await apiClient.get<AiRecipeRecommendationResponse>(
    '/recipes/ai/recommendations',
  );
  return data;
}

export async function getAiRecipeDetail(recipeId: string): Promise<AiRecipeDetail> {
  const { data } = await apiClient.get<AiRecipeDetail>('/recipes/ai/detail', {
    params: { recipe_id: recipeId },
  });
  return data;
}
```

- [ ] **Step 3: Commit (app repo)**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/app
git add src/types/api.ts src/api/recipes.ts
git commit -m "$(cat <<'EOF'
Feat: AI 레시피 API 타입·클라이언트 추가

EOF
)"
```

---

### Task 8: RecipeCard + tabs on list screen

**Files (app repo):**
- Modify: `src/components/RecipeCard.tsx`
- Modify: `src/app/(main)/recipes/index.tsx`

**Interfaces:**
- `RecipeCard` props: `{ recipe_name, owned_ingredients, missing_ingredients, recipe_difficulty, time }` 공통 타입으로 완화
- 탭 state: `'mangae' | 'ai'`
- 만개: 기존 query / `board_name`+`author_name` 네비
- AI: `getAiRecipeRecommendations` / `recipe_id`+`source=ai` 네비

- [ ] **Step 1: Widen RecipeCard props**

```typescript
// RecipeCard.tsx
type RecipeCardRecipe = {
  recipe_name: string;
  owned_ingredients: string[];
  missing_ingredients: string[];
  recipe_difficulty: string;
  time: string;
};

type RecipeCardProps = {
  recipe: RecipeCardRecipe;
  onPress: () => void;
};
```

`RecipeRecommendation` import 제거.

- [ ] **Step 2: Add tabs to `recipes/index.tsx`**

핵심 구조:

```tsx
type RecipeSourceTab = 'mangae' | 'ai';

const [tab, setTab] = useState<RecipeSourceTab>('mangae');

const mangaeQuery = useQuery({
  queryKey: ['recipes', 'recommendations'],
  queryFn: getRecipeRecommendations,
  enabled: tab === 'mangae',
});

const aiQuery = useQuery({
  queryKey: ['recipes', 'ai', 'recommendations'],
  queryFn: getAiRecipeRecommendations,
  enabled: tab === 'ai',
});

const activeQuery = tab === 'mangae' ? mangaeQuery : aiQuery;
```

탭 UI (리스트 상단):

```tsx
<View style={styles.tabs}>
  <Pressable onPress={() => setTab('mangae')} style={[styles.tab, tab === 'mangae' && styles.tabActive]}>
    <Text>만개의 레시피</Text>
  </Pressable>
  <Pressable onPress={() => setTab('ai')} style={[styles.tab, tab === 'ai' && styles.tabActive]}>
    <Text>AI 레시피</Text>
  </Pressable>
</View>
```

네비게이션:

- 만개: 기존 `board_name` / `author_name`
- AI:

```tsx
router.push({
  pathname: '/(main)/recipes/detail',
  params: { source: 'ai', recipe_id: item.recipe_id },
});
```

빈/에러 문구: AI 탭일 때 「AI 레시피를 불러오지 못했어요」 등으로 구분 가능하면 구분.

- [ ] **Step 3: Typecheck / smoke**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/app
npx tsc --noEmit
```

Expected: no errors related to changed files

- [ ] **Step 4: Commit (app)**

```bash
git add src/components/RecipeCard.tsx src/app/\(main\)/recipes/index.tsx
git commit -m "$(cat <<'EOF'
Feat: 레시피 화면에 만개/AI 탭 추가

EOF
)"
```

---

### Task 9: Detail screen AI branch

**Files (app repo):**
- Modify: `src/app/(main)/recipes/detail.tsx`

**Interfaces:**
- Params: `source?`, `recipe_id?` (AI) 또는 `board_name`+`author_name` (만개)
- AI: `getAiRecipeDetail`, 이미지·author·source_url UI 숨김
- 404: 재시도 숨김 / 그 외 재시도

- [ ] **Step 1: Branch query by source**

```tsx
const source = getFirstParam(sourceParam) ?? 'mangae';
const recipeId = getFirstParam(recipeIdParam);
const isAi = source === 'ai';

const mangaeQuery = useQuery({
  queryKey: ['recipes', 'detail', boardName, authorName],
  queryFn: () => getRecipeDetail(boardName!, authorName!),
  enabled: !isAi && Boolean(boardName && authorName),
});

const aiQuery = useQuery({
  queryKey: ['recipes', 'ai', 'detail', recipeId],
  queryFn: () => getAiRecipeDetail(recipeId!),
  enabled: isAi && Boolean(recipeId),
});

const detailQuery = isAi ? aiQuery : mangaeQuery;
```

가드:

- AI이고 `recipe_id` 없음 → 404 UI
- 만개이고 board/author 없음 → 기존과 동일

렌더:

- `main_image_url` / `author_name`: AI면 표시 안 함 (`'main_image_url' in recipe && recipe.main_image_url`)
- 재료·단계·팁: 공통 (`recipe.ingredients`, `recipe.steps`, `recipe.tips`)

- [ ] **Step 2: tsc**

```bash
npx tsc --noEmit
```

- [ ] **Step 3: Commit (app)**

```bash
git add src/app/\(main\)/recipes/detail.tsx
git commit -m "$(cat <<'EOF'
Feat: 레시피 상세 AI source_id 분기

EOF
)"
```

---

### Task 10: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Backend full AI suite**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/back
uv run pytest tests/unit/test_ai_recipe_*.py tests/api/test_ai_recipe_api.py -v
```

Expected: PASS

- [ ] **Step 2: Regression — 만개 API tests**

```bash
uv run pytest tests/api/test_rag_api.py tests/api/test_recipe_detail_api.py -v
```

Expected: PASS

- [ ] **Step 3: App typecheck**

```bash
cd /Users/jeong-yeonghun/Desktop/saksak/app
npx tsc --noEmit
```

Expected: PASS

- [ ] **Step 4: Manual smoke (optional live OpenAI)**
  1. 냉장고에 재료 추가
  2. 레시피 → AI 탭 → 카드 5개
  3. 카드 탭 → 상세(재료량·단계)
  4. 뒤로 후 같은 카드 재진입 → `cached` 가능(네트워크/로그로 확인)
  5. 만개 탭이 기존처럼 동작

---

## Spec Coverage Checklist

| Spec 요구 | Task |
|-----------|------|
| 만개 유지 | Global + Task 6 (기존 엔드포인트 미수정) + Task 10 regression |
| 탭 UX | Task 8 |
| 목록→상세 LLM | Task 4–5, 9 |
| 냉장고 재료만 | Task 5 empty short-circuit |
| Tool-calling agent | Task 3–4 |
| OpenAI + AI_RECIPE_MODEL | Task 1, 4 |
| Redis TTL 24h | Task 2 |
| API contracts | Task 1, 6 |
| 404/502 | Task 5–6, 9 |
| Out of scope (이미지/DB/LangGraph) | 의도적 미구현 |

## Self-Review Notes

- Placeholder 없음; 예외 생성자 시그니처는 구현 시 기존 `NotFoundException` 패턴에 맞출 것
- `propose_recipe_candidates`는 에이전트가 tool args로 5개를 제출 (도구가 검증·세션 저장)
- FE/BE는 별도 git repo — 커밋은 각 Task의 지정 repo에서
