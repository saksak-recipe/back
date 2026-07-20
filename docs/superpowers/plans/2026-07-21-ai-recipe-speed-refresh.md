# AI 레시피 속도 개선 + 새로고침 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI 레시피 목록을 1회 structured LLM 호출로 15초 이내에 만들고, 앱 pull-to-refresh로 강제 재생성한다.

**Architecture:** `AiRecipeAgent`의 tool-calling 루프를 `with_structured_output` 1회로 교체. owned/missing은 서버 `classify_ingredients`. FE는 AI API timeout 20s + RefreshControl.

**Tech Stack:** FastAPI, Pydantic, LangChain `ChatOpenAI.with_structured_output`, pytest, Expo Router, TanStack Query, TypeScript

## Global Constraints

- 목록 체감 목표 ≤ 15초; 서버/클라이언트 AI timeout ≈ 20초
- API 경로·응답 스키마 변경 없음
- 새로고침 = 기존 `GET /recipes/ai/recommendations` 재호출(강제 재생성)
- `AI_RECIPE_MODEL` 설정값 유지
- 스트리밍·목록 전체 캐시·만개 RAG 변경 Out of Scope

---

### Task 1: Agent structured output (TDD)

**Files:**
- Modify: `back/src/domains/ai_recipe/schemas.py` — list/detail payload 모델 추가
- Modify: `back/src/domains/ai_recipe/agent.py` — tool loop → structured 1회
- Modify: `back/src/domains/ai_recipe/service.py` — `AGENT_TIMEOUT_SECONDS = 20`
- Delete: `back/src/domains/ai_recipe/tools.py`
- Modify: `back/tests/unit/test_ai_recipe_agent.py` — structured mock
- Delete: `back/tests/unit/test_ai_recipe_tools.py`

**Interfaces:**
- Produces: `AiRecipeAgent.run_list(owned_names) -> list[AiRecipeCandidate]`
- Produces: `AiRecipeAgent.run_detail(owned_names, summary) -> dict` with ingredients/steps/tips
- Produces: `TOP_K = 5` in `agent.py` (or schemas)
- Consumes: `AiRecipeCandidateList`, `AiRecipeDetailPayload` pydantic models

- [x] **Step 1: Rewrite failing agent tests for structured output**
- [x] **Step 2: Run tests — expect FAIL (old API)**
- [x] **Step 3: Implement schemas + agent + timeout; delete tools**
- [x] **Step 4: Run `pytest tests/unit/test_ai_recipe_*.py tests/api/test_ai_recipe_api.py -v` — PASS**
- [ ] **Step 5: Commit back** (유저 요청 시)

---

### Task 2: App refresh + AI timeout

**Files:**
- Modify: `app/src/api/recipes.ts` — AI calls `timeout: 20000`
- Modify: `app/src/app/(main)/recipes/index.tsx` — RefreshControl + AI 로딩 문구

- [x] **Step 1: AI API timeout 20s**
- [x] **Step 2: FlatList RefreshControl + AI loading hint**
- [x] **Step 3: Manual sanity / typecheck if available** (`tsc --noEmit` EXIT 0)
- [ ] **Step 4: Commit app** (유저 요청 시)

---

### Task 3: Verification

- [x] Back unit + API tests green (21–25 passed)
- [x] Spec success criteria covered
- [x] App `tsc --noEmit` EXIT 0
