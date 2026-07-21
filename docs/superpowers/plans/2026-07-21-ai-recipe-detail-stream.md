# AI 레시피 상세 SSE 스트리밍 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI 레시피 상세를 SSE로 섹션 단위(`ingredients` → `steps` → `tips`) 스트리밍하되, LLM 1회·25초 안에 완료하고 성공 시에만 Redis에 저장한다.

**Architecture:** `PartialDetailParser`가 토큰 버퍼에서 배열이 닫힐 때 섹션을 emit. `AiRecipeAgent.stream_detail`이 ChatOpenAI 문자열 스트림 1회 + 최종 Pydantic validate. `AiRecipeService.stream_detail`이 캐시 hit/miss·quota·타임아웃을 오케스트레이션하고, `GET /recipes/ai/detail/stream`이 SSE로 전달한다.

**Tech Stack:** FastAPI `StreamingResponse`, SSE, LangChain `ChatOpenAI.stream`, Pydantic `AiRecipeDetailPayload`, pytest, httpx AsyncClient

## Global Constraints

- 전체 생성 ≤ 25초 (`AGENT_TIMEOUT_SECONDS` / `LLM_TIMEOUT_SECONDS` 유지)
- LLM 상세 miss당 **1회** 호출 (섹션별 다중 호출 금지)
- 기존 `GET /ai/detail` 동작·스키마 유지
- `AI_RECIPE_MODEL` 강제 변경 없음
- 부분 실패 시 Redis 미저장; 이미 emit한 섹션 롤백 없음
- 프론트엔드 구현 Out of Scope (API 계약만)
- 커밋은 유저가 요청할 때만 (스텝에 커밋이 있어도 유저 요청 전 skip)

---

## File Structure

| 파일 | 책임 |
|------|------|
| `src/domains/ai_recipe/partial_json.py` | 스트림 텍스트 → 섹션 emit (`ingredients`/`steps`/`tips`) |
| `src/domains/ai_recipe/schemas.py` | 스트림 이벤트 DTO (필요 시) |
| `src/domains/ai_recipe/agent.py` | `stream_detail` 추가 (`run_detail` 유지) |
| `src/domains/ai_recipe/service.py` | `stream_detail` AsyncIterator 오케스트레이션 |
| `src/api/v1/endpoints/rag.py` | `GET /ai/detail/stream` SSE 엔드포인트 |
| `tests/unit/test_ai_recipe_partial_json.py` | 부분 파서 단위 테스트 |
| `tests/unit/test_ai_recipe_agent.py` | `stream_detail` 테스트 추가 |
| `tests/unit/test_ai_recipe_service.py` | service 스트림 테스트 추가 |
| `tests/api/test_ai_recipe_api.py` | SSE API 테스트 추가 |

---

### Task 1: PartialDetailParser (TDD)

**Files:**
- Create: `src/domains/ai_recipe/partial_json.py`
- Create: `tests/unit/test_ai_recipe_partial_json.py`

**Interfaces:**
- Produces: `class PartialDetailParser`
  - `feed(chunk: str) -> list[tuple[str, object]]` — 0개 이상 `(section, value)`  
    `section` ∈ `{"ingredients", "steps", "tips"}`  
    `value`는 JSON-decoded Python 객체 (list)
  - `finish() -> list[tuple[str, object]]` — 버퍼 잔여에서 미emit 섹션이 완성됐으면 emit (보통 빈 리스트)
  - 각 섹션은 **최대 1회**만 emit
- Consumes: 없음

- [ ] **Step 1: Write failing parser tests**

```python
# tests/unit/test_ai_recipe_partial_json.py
from domains.ai_recipe.partial_json import PartialDetailParser


def test_emits_sections_as_arrays_close():
    parser = PartialDetailParser()
    events: list[tuple[str, object]] = []
    events.extend(parser.feed('{"ingredients":[{"name":"계란","amount":"2개"}]'))
    assert events == []
    events.extend(parser.feed(',"steps":[{"order":1,"description":"볶는다"}]'))
    assert events == [
        ("ingredients", [{"name": "계란", "amount": "2개"}]),
    ]
    events.extend(parser.feed(',"tips":["약불"]}'))
    assert ("steps", [{"order": 1, "description": "볶는다"}]) in events
    assert ("tips", ["약불"]) in events


def test_section_emitted_only_once():
    parser = PartialDetailParser()
    first = parser.feed(
        '{"ingredients":[{"name":"계란","amount":"1"}],'
        '"steps":[],"tips":[]}'
    )
    second = parser.feed("")
    assert sum(1 for s, _ in first if s == "ingredients") == 1
    assert second == []


def test_ignores_incomplete_json():
    parser = PartialDetailParser()
    assert parser.feed('{"ingredients":[{"name":"계') == []
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/unit/test_ai_recipe_partial_json.py -v`  
Expected: FAIL (`PartialDetailParser` import/존재하지 않음)

- [ ] **Step 3: Implement PartialDetailParser**

```python
# src/domains/ai_recipe/partial_json.py
from __future__ import annotations

import json
import re
from typing import Any

_SECTION_KEYS = ("ingredients", "steps", "tips")


class PartialDetailParser:
    """Accumulate streamed JSON text; emit each top-level array once when closed."""

    def __init__(self) -> None:
        self._buf = ""
        self._emitted: set[str] = set()

    def feed(self, chunk: str) -> list[tuple[str, Any]]:
        if chunk:
            self._buf += chunk
        return self._emit_ready()

    def finish(self) -> list[tuple[str, Any]]:
        return self._emit_ready()

    def _emit_ready(self) -> list[tuple[str, Any]]:
        events: list[tuple[str, Any]] = []
        for key in _SECTION_KEYS:
            if key in self._emitted:
                continue
            value = self._try_extract_array(key)
            if value is not None:
                self._emitted.add(key)
                events.append((key, value))
        return events

    def _try_extract_array(self, key: str) -> list[Any] | None:
        # Find `"key":` then parse balanced [...] from that position.
        match = re.search(rf'"{key}"\s*:', self._buf)
        if not match:
            return None
        start = self._buf.find("[", match.end())
        if start < 0:
            return None
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(self._buf)):
            ch = self._buf[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(self._buf[start : i + 1])
                    except json.JSONDecodeError:
                        return None
                    if isinstance(parsed, list):
                        return parsed
                    return None
        return None
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/unit/test_ai_recipe_partial_json.py -v`  
Expected: PASS

- [ ] **Step 5: Commit** (유저 요청 시)

```bash
git add src/domains/ai_recipe/partial_json.py tests/unit/test_ai_recipe_partial_json.py
git commit -m "$(cat <<'EOF'
feat: add partial JSON parser for AI recipe detail sections

EOF
)"
```

---

### Task 2: Agent `stream_detail` (TDD)

**Files:**
- Modify: `src/domains/ai_recipe/agent.py`
- Modify: `tests/unit/test_ai_recipe_agent.py`

**Interfaces:**
- Consumes: `PartialDetailParser`, `DETAIL_SYSTEM`, `AiRecipeDetailPayload`, `AiRecipeCacheRecord`
- Produces: `AiRecipeAgent.stream_detail(owned_names, summary) -> Iterator[tuple[str, object]]`
  - Yields `("ingredients"|"steps"|"tips", value)` then finally `("complete", dict)` where dict keys are `ingredients`/`steps`/`tips` (Pydantic 모델 또는 plain dict — service가 `AiRecipeDetailPayload`로 validate 가능해야 함)
  - On LLM/parse failure: raise `AgentFailedError` (기존과 동일)
- `run_detail` 시그니처·동작 변경 없음

**Streaming approach (고정):**
- `with_structured_output` invoke가 아니라 **문자열 토큰 스트림** 사용
- `self._llm.stream(messages)` 각 chunk의 `content`를 문자열로 이어 붙임
- Human 메시지에 기존 detail 입력 + `"Respond with a single JSON object with keys ingredients, steps, tips."` 추가
- 최종 버퍼를 `AiRecipeDetailPayload.model_validate_json` (또는 `model_validate` after `json.loads`)로 validate
- 프롬프트 본문(레시피 요약 필드)은 `run_detail`과 동일하게 유지

- [ ] **Step 1: Write failing agent stream tests**

`tests/unit/test_ai_recipe_agent.py`에 추가:

```python
def test_stream_detail_emits_sections_then_complete():
    chunks = [
        MagicMock(content='{"ingredients":[{"name":"계란","amount":"2개"}],'),
        MagicMock(content='"steps":[{"order":1,"description":"볶는다"}],'),
        MagicMock(content='"tips":["약불"]}'),
    ]
    llm = MagicMock()
    llm.stream.return_value = iter(chunks)

    events = list(
        AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").stream_detail(
            ["계란"], _summary()
        )
    )

    assert events[0][0] == "ingredients"
    assert events[1][0] == "steps"
    assert events[2][0] == "tips"
    assert events[3][0] == "complete"
    assert events[3][1]["tips"] == ["약불"]
    llm.stream.assert_called_once()
    llm.with_structured_output.assert_not_called()


def test_stream_detail_raises_on_invalid_final_json():
    llm = MagicMock()
    llm.stream.return_value = iter([MagicMock(content='{"ingredients":[}')])

    with pytest.raises(AgentFailedError):
        list(
            AiRecipeAgent(llm=llm, model_name="gpt-4o-mini").stream_detail(
                ["계란"], _summary()
            )
        )
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/unit/test_ai_recipe_agent.py::test_stream_detail_emits_sections_then_complete tests/unit/test_ai_recipe_agent.py::test_stream_detail_raises_on_invalid_final_json -v`  
Expected: FAIL (`stream_detail` 없음)

- [ ] **Step 3: Implement `stream_detail`**

`agent.py`에 추가 (요지):

```python
def stream_detail(
    self,
    owned_names: list[str],
    summary: AiRecipeCacheRecord,
):
    from domains.ai_recipe.partial_json import PartialDetailParser

    messages = [
        SystemMessage(content=DETAIL_SYSTEM),
        HumanMessage(
            content=(
                f"Recipe: {summary.recipe_name}\n"
                f"Ingredients: {', '.join(summary.recipe_ingredients)}\n"
                f"Owned fridge ingredients: {', '.join(owned_names)}\n"
                f"Difficulty: {summary.recipe_difficulty}\n"
                f"Time: {summary.time}\n"
                "Provide ingredient amounts, ordered steps, and tips.\n"
                "Respond with a single JSON object with keys "
                "ingredients, steps, tips."
            )
        ),
    ]
    parser = PartialDetailParser()
    buf = ""
    try:
        for chunk in self._llm.stream(messages):
            text = chunk.content if isinstance(chunk.content, str) else ""
            if not text:
                continue
            buf += text
            for event in parser.feed(text):
                yield event
        for event in parser.finish():
            yield event
        payload = AiRecipeDetailPayload.model_validate_json(buf)
    except Exception as exc:
        raise AgentFailedError("recipe detail stream failed") from exc

    yield (
        "complete",
        {
            "ingredients": payload.ingredients,
            "steps": payload.steps,
            "tips": payload.tips,
        },
    )
```

Note: 모델이 JSON 앞뒤에 마크다운 fence를 붙이면 validate가 실패한다. fence가 보이면 `buf`에서 첫 `{`~마지막 `}`만 잘라 validate하도록 최소 가드 추가:

```python
def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end < start:
        raise ValueError("no json object")
    return text[start : end + 1]
```

- [ ] **Step 4: Run agent unit tests — expect PASS**

Run: `pytest tests/unit/test_ai_recipe_agent.py -v`  
Expected: PASS (기존 + 신규)

- [ ] **Step 5: Commit** (유저 요청 시)

```bash
git add src/domains/ai_recipe/agent.py tests/unit/test_ai_recipe_agent.py
git commit -m "$(cat <<'EOF'
feat: stream AI recipe detail sections from one LLM call

EOF
)"
```

---

### Task 3: Service `stream_detail` (TDD)

**Files:**
- Modify: `src/domains/ai_recipe/service.py`
- Modify: `src/domains/ai_recipe/schemas.py` (선택: 이벤트 타입 없음 — tuple로 충분하면 스키마 추가 금지)
- Modify: `tests/unit/test_ai_recipe_service.py`

**Interfaces:**
- Produces: `async def stream_detail(self, recipe_id: str, scope: RecipeScope = RecipeScope.personal) -> AsyncIterator[tuple[str, object]]`
  - Yields SSE용 논리 이벤트:
    - `("meta", dict)` — `recipe_id`, `recipe_name`, `owned_ingredients`, `missing_ingredients`, `cached`
    - `("ingredients"|"steps"|"tips", list)`
    - `("done", {"cached": bool})`
    - `("error", {"detail": str})` — 예외를 삼키고 yield 후 return (엔드포인트가 연결 종료)
  - Redis miss: `NotFoundException` raise (**yield 전**)
  - expand 경로: **첫 yield 전에** `quota.consume` (429는 HTTP로 나가게) — 스펙 “가능하면 스트림 시작 전” 우선
  - miss expand: `asyncio.to_thread`로 sync generator를 돌리되, 전체 wall clock `AGENT_TIMEOUT_SECONDS` 초과 시 `error` yield
  - 성공 시에만 `cache.set` 후 `done`
  - 실패 시 `cache.set` 호출 안 함

**Timeout 구현 요지:**
- `loop.run_in_executor` / `asyncio.to_thread`로 generator를 한 번에 소비하지 말고,  
  `asyncio.wait_for(_consume_agent_stream(), timeout=AGENT_TIMEOUT_SECONDS)` 안에서  
  queue를 쓰거나, agent 전체를 to_thread로 list화한 뒤 순차 yield (단순안):

**단순안 (권장, YAGNI):**  
expand 시 `await asyncio.wait_for(asyncio.to_thread(_collect), timeout=...)`  
`_collect`가 `list(agent.stream_detail(...))`를 반환.  
그다음 메모리의 이벤트들을 yield하고, `complete`로 캐시 갱신.  

트레이드오프: 섹션이 LLM 중간에 나와도 **HTTP로는 collect 끝난 뒤** 한꺼번에 흘러갈 수 있음.  
**진짜 점진 SSE**가 필요하면 queue 방식이 맞다.

**스펙 의도 = 체감 스트리밍**이므로 queue 방식을 쓴다:

```python
async def stream_detail(...):
    record = await self.cache.get(recipe_id)
    if record is None:
        raise NotFoundException(detail="AI 레시피를 찾지 못했습니다.")

    if record.has_detail():
        yield ("meta", {... cached: True ...})
        yield ("ingredients", [i.model_dump() for i in record.ingredients or []])
        yield ("steps", [s.model_dump() for s in record.steps or []])
        yield ("tips", list(record.tips or []))
        yield ("done", {"cached": True})
        return

    scoped = await self.scope_loader.load(scope)
    names = [item.ingredient_name for item in scoped.ingredients]
    await self.quota.consume(scoped.scope, scoped.cache_owner_id)

    yield ("meta", {... cached: False ...})

    queue: asyncio.Queue = asyncio.Queue()
    done_sentinel = object()

    def worker():
        try:
            for event in self.agent.stream_detail(names, record):
                asyncio.get_event_loop()  # DON'T — use call_soon_threadsafe
        ...
```

스레드→async 전달은 실수하기 쉽다. **권장 단순+점진 타협:**

1. `asyncio.to_thread`에서 agent generator를 돌리며 **각 이벤트를 `loop.call_soon_threadsafe(queue.put_nowait, event)`**
2. async 쪽에서 `asyncio.wait_for(queue.get(), ...)` 누적 deadline

구현 복잡도 대비, 플랜에서는 다음을 **필수**로 고정한다:

```python
async def _iter_agent_detail(self, names, record):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def run():
        try:
            for item in self.agent.stream_detail(names, record):
                loop.call_soon_threadsafe(queue.put_nowait, ("ok", item))
            loop.call_soon_threadsafe(queue.put_nowait, ("end", None))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("err", exc))

    task = loop.run_in_executor(None, run)
    deadline = loop.time() + AGENT_TIMEOUT_SECONDS
    complete_payload = None
    try:
        while True:
            timeout = deadline - loop.time()
            if timeout <= 0:
                raise TimeoutError()
            status, payload = await asyncio.wait_for(queue.get(), timeout=timeout)
            if status == "end":
                break
            if status == "err":
                raise payload
            kind, value = payload
            if kind == "complete":
                complete_payload = value
            else:
                yield (kind, _maybe_dump(value))
        await task
    except TimeoutError as exc:
        raise TimeoutError() from exc

    if complete_payload is None:
        raise AgentFailedError("missing complete payload")
    return complete_payload  # async generator can't return easily in all py versions
```

Python async generator `return value`는 `StopAsyncIteration.value`로만 전달되므로, **complete를 일반 yield로 처리**하고 service가 모아서 캐시한다:

```python
# service expand path
yield ("meta", meta)
try:
    complete = None
    async for kind, value in self._agent_stream_events(names, record):
        if kind == "complete":
            complete = value
        else:
            yield (kind, value)
    if complete is None:
        raise AgentFailedError("missing complete")
    updated = record.model_copy(update={...complete...})
    await self.cache.set(updated)
    yield ("done", {"cached": False})
except (TimeoutError, AgentFailedError, openai.OpenAIError) as exc:
    logger.exception("AI recipe detail stream failed")
    yield ("error", {"detail": "AI 레시피 상세 생성에 실패했습니다."})
```

`_maybe_dump`: Pydantic 모델이면 `model_dump()`, list of models면 각각 dump.

- [ ] **Step 1: Write failing service tests**

```python
async def test_stream_detail_cache_hit(user):
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
        user=user, scope_loader=AsyncMock(), agent=agent, cache=cache, quota=_quota()
    )

    events = [e async for e in service.stream_detail("rid")]

    assert events[0][0] == "meta"
    assert events[0][1]["cached"] is True
    assert events[1][0] == "ingredients"
    assert events[-1] == ("done", {"cached": True})
    agent.stream_detail.assert_not_called()
    cache.set.assert_not_awaited()


async def test_stream_detail_expands_and_caches(user):
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
    agent.stream_detail.return_value = iter(
        [
            ("ingredients", [{"name": "계란", "amount": "2개"}]),
            ("steps", [{"order": 1, "description": "볶는다"}]),
            ("tips", ["약불"]),
            (
                "complete",
                {
                    "ingredients": [AiRecipeIngredient(name="계란", amount="2개")],
                    "steps": [AiRecipeStep(order=1, description="볶는다")],
                    "tips": ["약불"],
                },
            ),
        ]
    )
    item = MagicMock()
    item.ingredient_name = "계란"
    scope_loader = _scope_loader([item], cache_owner_id=user.id)
    quota = _quota()
    service = AiRecipeService(
        user=user, scope_loader=scope_loader, agent=agent, cache=cache, quota=quota
    )

    events = [e async for e in service.stream_detail("rid")]

    assert events[0][0] == "meta"
    assert events[0][1]["cached"] is False
    kinds = [k for k, _ in events]
    assert kinds == ["meta", "ingredients", "steps", "tips", "done"]
    cache.set.assert_awaited_once()
    quota.consume.assert_awaited_once()


async def test_stream_detail_error_does_not_cache(user):
    cache = AsyncMock()
    cache.get.return_value = AiRecipeCacheRecord(
        recipe_id="rid",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란"],
        owned_ingredients=[],
        missing_ingredients=[],
    )
    agent = MagicMock()
    agent.stream_detail.side_effect = AgentFailedError("fail")
    scope_loader = _scope_loader([], cache_owner_id=user.id)
    service = AiRecipeService(
        user=user, scope_loader=scope_loader, agent=agent, cache=cache, quota=_quota()
    )

    events = [e async for e in service.stream_detail("rid")]

    assert events[-1][0] == "error"
    cache.set.assert_not_awaited()


async def test_stream_detail_missing_raises(user):
    cache = AsyncMock()
    cache.get.return_value = None
    service = AiRecipeService(
        user=user,
        scope_loader=AsyncMock(),
        agent=MagicMock(),
        cache=cache,
        quota=_quota(),
    )

    with pytest.raises(NotFoundException):
        _ = [e async for e in service.stream_detail("missing")]
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/unit/test_ai_recipe_service.py -k stream_detail -v`  
Expected: FAIL (`stream_detail` 없음)

- [ ] **Step 3: Implement service `stream_detail` + `_agent_stream_events`**

위 인터페이스대로 `service.py`에 구현. expand 경로에서 quota는 **meta yield 전**.  
`get_detail` 코드는 수정하지 않는다.

- [ ] **Step 4: Run service tests — expect PASS**

Run: `pytest tests/unit/test_ai_recipe_service.py -v`  
Expected: PASS

- [ ] **Step 5: Commit** (유저 요청 시)

```bash
git add src/domains/ai_recipe/service.py tests/unit/test_ai_recipe_service.py
git commit -m "$(cat <<'EOF'
feat: orchestrate AI recipe detail SSE events in service

EOF
)"
```

---

### Task 4: API SSE endpoint (TDD)

**Files:**
- Modify: `src/api/v1/endpoints/rag.py`
- Modify: `tests/api/test_ai_recipe_api.py`

**Interfaces:**
- Produces: `GET /api/v1/recipes/ai/detail/stream?recipe_id=&scope=`
  - `media_type="text/event-stream"`
  - 각 이벤트: `event: {name}\ndata: {json}\n\n`
  - `NotFoundException` / `TooManyRequestsException` / auth는 기존처럼 **HTTP 상태** (스트림 전)
  - 스트림 중 `error` 이벤트 후 generator 종료 (HTTP 200으로 열린 뒤 body에 error — 정상 SSE 패턴)

헬퍼:

```python
import json
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

async def ai_recipe_detail_stream(...):
    async def gen() -> AsyncIterator[str]:
        async for name, payload in service.stream_detail(recipe_id, scope=scope):
            yield _sse(name, payload)

    # NotFound/quota: stream_detail의 첫 await 전에 raise → dependency/endpoint에서 처리
    # FastAPI는 StreamingResponse 생성 시 gen이 아직 안 돌 수 있음.
    # 해결: 첫 이벤트를 peek하거나, service.prepare 분리.
```

**Peek 패턴 (필수):** StreamingResponse가 lazy라 404가 200으로 나오지 않게:

```python
async def ai_recipe_detail_stream(
    recipe_id: str,
    scope: RecipeScope = RecipeScope.personal,
    service: AiRecipeService = Depends(get_ai_recipe_service),
) -> StreamingResponse:
    stream = service.stream_detail(recipe_id, scope=scope)
    try:
        first = await anext(stream)
    except NotFoundException:
        raise
    except TooManyRequestsException:
        raise

    async def gen() -> AsyncIterator[str]:
        name, payload = first
        yield _sse(name, payload)
        async for name, payload in stream:
            yield _sse(name, payload)

    return StreamingResponse(gen(), media_type="text/event-stream")
```

`responses=`에 `UnAuthorizedException`, `NotFoundException`, `TooManyRequestsException`, `ExternalServiceException` 포함.  
`TooManyRequestsException` import 추가.

- [ ] **Step 1: Write failing API tests**

```python
async def test_ai_detail_stream_requires_auth(client: AsyncClient):
    response = await client.get(
        "/api/v1/recipes/ai/detail/stream",
        params={"recipe_id": "rid"},
    )
    assert response.status_code == 401


async def test_ai_detail_stream_404(client: AsyncClient, auth_headers: dict[str, str]):
    async def _gen():
        raise NotFoundException(detail="AI 레시피를 찾지 못했습니다.")
        yield  # pragma: no cover

    mock = MagicMock()
    mock.stream_detail = MagicMock(return_value=_gen())
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/detail/stream",
            headers=auth_headers,
            params={"recipe_id": "missing"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)


async def test_ai_detail_stream_sse_body(
    client: AsyncClient, auth_headers: dict[str, str]
):
    async def _gen():
        yield ("meta", {"recipe_id": "rid", "recipe_name": "계란볶음밥",
                        "owned_ingredients": ["계란"], "missing_ingredients": [],
                        "cached": True})
        yield ("ingredients", [{"name": "계란", "amount": "2개"}])
        yield ("steps", [{"order": 1, "description": "볶는다"}])
        yield ("tips", ["약불"])
        yield ("done", {"cached": True})

    mock = MagicMock()
    mock.stream_detail = MagicMock(return_value=_gen())
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/detail/stream",
            headers=auth_headers,
            params={"recipe_id": "rid"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = response.text
        assert "event: meta" in body
        assert "event: ingredients" in body
        assert "event: done" in body
        mock.stream_detail.assert_called_once_with("rid", scope=RecipeScope.personal)
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)
```

Note: `stream_detail`가 async generator면 mock은 `async def _gen()`를 반환해야 하고, endpoint는 `async for` / `anext`를 쓴다. MagicMock `return_value=_gen()`는 coroutine이 아니라 async gen iterator — OK.

서비스가 async gen이면:

```python
mock.stream_detail = lambda *a, **k: _gen()
```

- [ ] **Step 2: Run API tests — expect FAIL**

Run: `pytest tests/api/test_ai_recipe_api.py -k stream -v`  
Expected: FAIL (404 route)

- [ ] **Step 3: Implement endpoint**

`rag.py`에 `/ai/detail/stream` 추가 (위 peek 패턴).

- [ ] **Step 4: Run API + regression — expect PASS**

Run: `pytest tests/api/test_ai_recipe_api.py tests/unit/test_ai_recipe_*.py -v`  
Expected: PASS

- [ ] **Step 5: Commit** (유저 요청 시)

```bash
git add src/api/v1/endpoints/rag.py tests/api/test_ai_recipe_api.py
git commit -m "$(cat <<'EOF'
feat: add SSE endpoint for AI recipe detail stream

EOF
)"
```

---

### Task 5: Verification

- [ ] **Step 1: Full AI recipe test suite**

Run: `pytest tests/unit/test_ai_recipe_*.py tests/api/test_ai_recipe_api.py -v`  
Expected: 전부 PASS

- [ ] **Step 2: Spec coverage checklist**

| Success Criteria | 증거 |
|------------------|------|
| 25초 안 `done`/`error` | service timeout → `error` 이벤트 |
| miss 시 섹션 순 emit | agent + service 테스트 |
| hit 즉시 동일 순서 | `test_stream_detail_cache_hit` |
| 완료 후 `/ai/detail` hit | `cache.set` 후 기존 `get_detail` 경로 (기존 테스트 유지) |
| 목록/모델 강제 변경 없음 | diff에 recommendations·config 모델 강제 없음 |

- [ ] **Step 3: Commit** (유저 요청 시) — 남은 문서/정리만

---

## Spec Self-Review

| Spec 요구 | Task |
|-----------|------|
| `GET /ai/detail/stream` SSE | Task 4 |
| 이벤트 meta→ingredients→steps→tips→done/error | Task 3–4 |
| LLM 1회 + 부분 JSON | Task 1–2 |
| 25초 타임아웃 | Task 3 |
| 성공 시만 Redis | Task 3 |
| 기존 `/ai/detail` 유지 | Task 3 (미수정) |
| 캐시 hit 즉시 스트림 | Task 3 |
| 404 스트림 전 | Task 4 peek |
| quota 스트림 전 | Task 3 |
| Out of scope (목록 스트림, WS, 모델 강제) | 미포함 |

Placeholder scan: 없음.  
타입: 이벤트 `tuple[str, object]`, complete dict 키 `ingredients`/`steps`/`tips`로 Task 2–3 일치.
