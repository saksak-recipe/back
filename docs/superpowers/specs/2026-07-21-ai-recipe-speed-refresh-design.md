# AI 레시피 속도 개선 + 새로고침(강제 재생성)

날짜: 2026-07-21  
상태: Approved (대화에서 섹션별 승인 완료)  
선행 스펙: `2026-07-21-ai-recipe-agent-design.md`

## Goal

AI 레시피 목록 추천 체감 시간을 **15초 이내**로 줄이고,  
앱에서 **당겨서 새로고침**하면 **다른 레시피로 강제 재생성**되게 한다.

## Decisions

| 항목 | 선택 |
|------|------|
| 속도 접근 | Approach 1 — tool-calling 멀티스텝 → **1회 structured LLM 호출** |
| 목표 체감 | 목록 추천 **≤ 15초** |
| 서버 타임아웃 | 에이전트/LLM 대기 **약 20초** (앱 여유 포함) |
| 새로고침 의미 | **A. 다른 레시피로 다시 생성** (캐시된 목록 재사용 아님) |
| 새로고침 API | 별도 엔드포인트 없음. 기존 `GET /recipes/ai/recommendations` 재호출 |
| owned/missing | LLM tool 제거. 서버 `classify_ingredients`만 사용 |
| 목록 전체 캐시 | 없음 (매번 새 `recipe_id` + 새 후보). 개별 recipe Redis는 유지 |
| 모델 | `AI_RECIPE_MODEL` 설정값 유지 (코드에서 강제 교체하지 않음) |

## Out of Scope

- 스트리밍 응답
- 목록 전체 Redis 캐시 / 재료 해시 캐시
- LangGraph / 멀티에이전트
- “이전 추천 제외” 강제 로직 (프롬프트로만 다양성 유도)
- 만개 RAG / 크롤 파이프라인 변경
- AI 레시피 이미지·DB 영속 저장
- 모델명 강제 변경 배포

## Problem

현재 `AiRecipeAgent`는 LangChain tool-calling 루프(`MAX_TOOL_LOOPS=8`)로  
`get_user_ingredients` → `propose_recipe_candidates` 등을 **순차 OpenAI 왕복**한다.  
재료·분류 tool은 서버가 이미 알고 있는 정보라 왕복만 늘린다.  
실측 체감 30~50초의 주원인이다.  
앱 전역 Axios timeout(15초)과도 어긋나 있다.

## Architecture

```
[앱] AI 탭
  ├─ 최초 로드 / Pull-to-refresh
  │    → GET /api/v1/recipes/ai/recommendations  (timeout 20s)
  │         ↓
  │    [BE] AiRecipeService.recommend
  │         1. IngredientRepository로 재료 로드
  │         2. 빈 재료면 빈 배열 즉시 반환
  │         3. AiRecipeAgent.run_list — structured output 1회
  │         4. 후보마다 UUID + classify_ingredients + Redis set
  │         5. 응답 반환
  │
  └─ 상세
       → GET /api/v1/recipes/ai/detail?recipe_id=
            ↓
       [BE] Redis hit + has_detail → 즉시
            miss detail → AiRecipeAgent.run_detail — structured output 1회 → Redis 갱신
```

### Backend 변경

| 구성 | 변경 |
|------|------|
| `agent.py` | tool-calling 루프 제거. `with_structured_output`(또는 동등)으로 목록/상세 스키마 1회 호출 |
| `tools.py` | 목록/상세 생성 path에서 더 이상 사용하지 않음. 삭제 또는 dead code 정리 |
| `service.py` | `AGENT_TIMEOUT_SECONDS` ≈ 20. 오케스트레이션·캐시·classify 유지 |
| API | 경로·응답 스키마 **변경 없음** |

**목록 프롬프트 요지**

- 입력: 냉장고 재료 이름 목록
- 출력: 정확히 `TOP_K`(5)개 후보  
  (`recipe_name`, `recipe_ingredients`, `recipe_difficulty`, `time`)
- 보유 재료를 최대한 쓰는 한식/집밥 위주
- 새로고침마다 다양하게 고르도록 짧은 지시 포함

**상세 프롬프트 요지**

- 입력: 캐시된 요약(이름, 재료, 난이도, 시간)
- 출력: `ingredients[{name,amount}]`, `steps[{order,description}]`, `tips`

### Frontend 변경

| 구성 | 변경 |
|------|------|
| `recipes/index.tsx` | AI(및 만개) 목록에 `RefreshControl`. AI refetch = 강제 재생성 |
| `api/recipes.ts` | AI 목록/상세 요청만 `timeout: 20000` |
| 로딩 UX | AI 첫 로딩 시 짧은 안내 문구. refetch 중에는 목록 유지 + pull indicator |

전역 Axios timeout(15초)은 그대로 두고, AI 엔드포인트만 오버라이드한다.

## Error Handling

| 상황 | 동작 |
|------|------|
| LLM 타임아웃 / OpenAI 오류 / 스키마 불일치 | `ExternalServiceException` — “AI 레시피 생성에 실패했습니다.” |
| 상세 Redis miss | `NotFoundException` — 클라이언트가 목록을 다시 받아야 함 |
| 앱 네트워크/타임아웃 | 에러 UI + “다시 시도”. pull refresh 실패도 동일 |

## Testing

- 단위: `run_list` / `run_detail`가 mock LLM으로 structured 결과를 1회 호출해 반환
- 단위: service가 classify + Redis set 후 응답 매핑
- API: `/recipes/ai/recommendations`, `/recipes/ai/detail` 계약 유지 (기존 테스트 갱신)
- 앱: RefreshControl·AI timeout은 수동 확인 (E2E 추가 없음)

## Success Criteria

1. 콜드 목록 추천 체감 **대부분 ≤ 15초** (네트워크·모델 상태에 따라 상한 ~20초)
2. AI 탭 pull-to-refresh 시 **새로운 recipe_id / 다른 후보 세트** 반환
3. 기존 탭 UX·API 경로·응답 필드 호환 유지
4. 상세 Redis hit는 즉시, miss만 1회 LLM
