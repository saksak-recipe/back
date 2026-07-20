# Owned/Missing Ingredients Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 추천 API에서 `parsed_ingredients`를 제거하고 `owned_ingredients` / `missing_ingredients`로 분리 반환하며, 앱 RecipeCard에 표시한다.

**Architecture:** mapper에서 레시피 재료 문자열을 split·정규화한 뒤 사용자 보유 set과 완전 일치로 분류. RagService가 `names`를 mapper에 전달. 앱 타입·카드 갱신.

**Tech Stack:** FastAPI, Pydantic, pytest; Expo, TypeScript

**Spec:** `docs/superpowers/specs/2026-07-20-recipe-owned-missing-ingredients-design.md`

## Global Constraints

- 매칭: `normalize_name` 후 완전 일치만
- `parsed_ingredients` 필드 제거
- 상세 API 변경 금지
- 커밋 스타일: `Feat:` / `Test:` / `Fix:`

---

### Task 1: Backend schema + mapper + service

**Files:**
- Modify: `src/domains/rag/schemas.py`
- Modify: `src/domains/rag/mapper.py`
- Modify: `src/domains/rag/service.py`
- Modify: `tests/unit/test_rag_mapper.py`
- Modify: `tests/unit/test_rag_service.py`
- Modify: `tests/api/test_rag_api.py`

- [ ] TDD: mapper split/classify tests
- [ ] Schema: replace `parsed_ingredients` with owned/missing lists
- [ ] `map_document_to_recipe(doc, score, owned_names: list[str])`
- [ ] Service passes `names`; dedupe key without `parsed_ingredients` (use recipe_name + board_name + author_name)
- [ ] Commit: `Feat: 추천 응답 owned/missing 재료 분리`

### Task 2: App types + RecipeCard

**Files:**
- Modify: `app/src/types/api.ts`
- Modify: `app/src/components/RecipeCard.tsx`

- [ ] Update type
- [ ] Show “있어요” / “필요해요” lines
- [ ] Commit: `Feat: 추천 카드 보유·필요 재료 표시`
