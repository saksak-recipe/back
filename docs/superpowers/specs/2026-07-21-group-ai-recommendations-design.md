# 그룹 냉장고 기반 AI·RAG 추천

날짜: 2026-07-21  
상태: Approved (대화에서 섹션별 승인 완료)  
관련 스펙:
- `2026-07-21-household-group-design.md` (MVP에서 그룹 추천 Out of Scope → 본 스펙으로 해제)
- `2026-07-20-recipe-recommendation-rag-design.md`
- `2026-07-21-ai-recipe-agent-design.md`
- `2026-07-21-ai-recipe-speed-refresh-design.md`

## Goal

가구 그룹의 **공유 냉장고**를 기준으로  
기존 **RAG 만개 추천**과 **AI 레시피 목록/상세**를 사용할 수 있게 한다.

- 개인 추천(`scope=personal`)은 **동작·캐시 그대로 유지**
- 그룹 추천은 **그룹 공유 냉장고만** 사용 (개인 재료와 합치지 않음)
- 클라이언트가 기존 경로에 `scope` 쿼리만 추가하면 되도록 한다

이번 범위는 **백엔드 API** 우선이다. (프론트는 별도)

## Decisions

| 항목 | 선택 |
|------|------|
| 재료 기준 | **그룹 공유 냉장고만** (`group_id` 스코프) |
| API 형태 | 기존 추천 경로 + `scope` 쿼리 (`personal` \| `group`) |
| 대상 기능 | RAG 만개 추천 + AI 목록 + AI 상세 **모두** |
| 기본값 | `scope=personal` (미전달 시 기존과 동일) |
| 아키텍처 | 재료 스코프 로더 헬퍼 공유 (RAG·AI 공통) |
| AI 목록 캐시 | personal: `ai_recipe_list:{user_id}` / group: `ai_recipe_list:group:{group_id}` |
| 그룹 캐시 공유 | 같은 그룹 멤버가 **그룹 단위 캐시**를 공유 |
| 권한 | 그룹 `owner` / `member` 모두 `scope=group` 가능 |
| 미가입 + group | 기존 그룹 API와 동일 — `404 GROUP_NOT_FOUND` |
| 빈 그룹 냉장고 | 개인과 동일 — `200` + 빈 추천 |

## Out of Scope

- 프론트엔드 UI
- 개인 + 그룹 재료 합산 추천
- `/groups/me/recipes/...` 전용 엔드포인트
- 저장 레시피 공유·스코프 변경
- 만개 상세 크롤(`GET /recipes/detail`) 변경
- 추천 도메인 전체 scope-first 재설계
- 역할별 추천 제한 (읽기전용 등)

## Problem

가구 그룹 MVP는 공유 냉장고·장보기만 제공했고,  
RAG/AI는 `IngredientRepository.get_ingredients`가 `group_id IS NULL`만 조회해  
**개인 냉장고에만** 묶여 있다.  
그룹으로 생활하는 사용자는 공유 재료 기준으로 추천을 받을 수 없다.

## Architecture

```
[클라이언트]
  GET /recipes/recommendations?scope=personal|group
  GET /recipes/ai/recommendations?scope=...&refresh=
  GET /recipes/ai/detail?scope=...&recipe_id=
       │
       ▼
┌──────────────────┐     ┌─────────────────────────┐
│ RagService /     │────▶│ IngredientScopeLoader   │
│ AiRecipeService  │     │  personal → get_ingredients
└──────────────────┘     │  group → membership + list_by_group
                         └─────────────────────────┘
       │
       ▼ (AI 목록만)
┌──────────────────┐
│ AiRecipeCache    │  list key = user_id | group:{group_id}
└──────────────────┘

그룹 재료 CRUD (GroupService)
  → commit 후 invalidate ai_recipe_list:group:{group_id}
```

### 재료 스코프 로더

RAG·AI가 공통으로 쓰는 작은 헬퍼(또는 동등한 repo/서비스 메서드).

입력: `user`, `scope`  
출력: `(ingredients, cache_owner)`

| scope | ingredients | cache_owner |
|-------|-------------|-------------|
| `personal` | `get_ingredients(user_id)` | `user_id` |
| `group` | 멤버십 확인 후 `list_by_group(group_id)` | `group_id` |

- `scope=group`이고 멤버십 없음 → `NotFoundException(GROUP_NOT_FOUND)`  
  (`GroupService._require_membership`과 동일 메시지/코드)
- 추천·분류·urgency 로직은 **재료 리스트만** 스코프에 따라 바뀌고, 나머지 파이프라인은 재사용

### API

| 엔드포인트 | 추가 파라미터 | 비고 |
|------------|---------------|------|
| `GET /api/v1/recipes/recommendations` | `scope` | 기본 `personal` |
| `GET /api/v1/recipes/ai/recommendations` | `scope`, 기존 `refresh` | 기본 `personal` |
| `GET /api/v1/recipes/ai/detail` | `scope`, 기존 `recipe_id` | expand 시 재료 로드에 `scope` 반영 |

`scope`는 enum(`personal` \| `group`). 잘못된 값 → FastAPI **422**.

응답 스키마는 변경하지 않는다. `ingredients_used` 등은 로드된 스코프 재료를 반영한다.

### AI 캐시

| 스코프 | 목록 키 |
|--------|---------|
| personal | `ai_recipe_list:{user_id}` (기존) |
| group | `ai_recipe_list:group:{group_id}` |

- 목록 get/set/invalidate는 `cache_owner`(+ 스코프 구분) 기준으로 확장
- 개별 레시피 본문 키 `ai_recipe:{recipe_id}`는 **유지**
- 상세 expand는 해당 `scope`로 재료를 다시 로드해 owned/missing·프롬프트에 반영
- 개인 재료 CRUD → 개인 목록 캐시 무효화 (기존 `IngredientService`)
- **그룹 재료 CRUD** (`GroupService` add/update/delete/delete-all, 필요 시 merge로 그룹 재료가 바뀌는 경로) → `ai_recipe_list:group:{group_id}` 무효화  
  (개인 CRUD와 같은 commit-after 패턴 권장)

### 권한

- `scope=group`: 현재 유저가 속한 그룹의 멤버면 호출 가능 (`owner` / `member` 동일)
- 유저당 활성 그룹 최대 1개이므로 `group_id` 선택 파라미터는 **두지 않음**

## Error Handling

| 상황 | 응답 |
|------|------|
| `scope` 값 오류 | 422 |
| `scope=group` + 미가입 | 404 `GROUP_NOT_FOUND` |
| 재료 없음 | 200 + 빈 목록 |
| AI/외부 실패 | 기존 `ExternalServiceException` |
| AI 상세 캐시 miss | 기존 `NotFoundException` |

## Testing

최소 검증:

1. `scope=personal` (또는 생략) — 기존 RAG/AI 회귀
2. `scope=group` + 멤버 + 그룹 재료 — 그룹 재료만 반영된 추천
3. `scope=group` + 미가입 — 404
4. `scope=group` + 그룹 재료 비어 있음 (개인 재료만 존재) — 빈 추천
5. 그룹 재료 변경 후 AI 목록 캐시가 무효화되어 재생성됨

## Supersedes (부분)

`2026-07-21-household-group-design.md`의 다음 항목을 본 스펙이 대체한다.

- Decisions: 「추천(RAG/AI): MVP는 개인 냉장고만」
- Out of Scope: 「그룹 냉장고 기반 레시피 추천」
