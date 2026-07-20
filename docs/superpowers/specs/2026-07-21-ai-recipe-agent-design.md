# LLM 에이전트 기반 AI 레시피 (목록 + 상세)

날짜: 2026-07-21  
상태: Approved (대화에서 섹션별 승인 완료)

## Goal

만개의 레시피(RAG 추천 + 크롤 상세) 파이프라인은 **그대로 유지**하고,  
냉장고 보유 재료 기반 **OpenAI LangChain tool-calling 에이전트**로 AI 레시피 목록·상세를  
별도 서비스로 제공한다. 앱 레시피 화면에서 탭으로 두 소스를 전환한다.

## Decisions

| 항목 | 선택 |
|------|------|
| UX 진입 | 기존 `recipes` 화면 탭: 「만개의 레시피」 \| 「AI 레시피」 |
| 깊이 | 만개와 동일 — 목록 → 탭 시 상세 (둘 다 LLM/에이전트) |
| 입력 | 냉장고 보유 재료만 (스타일·시간 옵션 없음) |
| 에이전트 | LangChain tool-calling (멀티스텝·도구 사용). 단순 1회 LLM 호출 아님 |
| LLM | OpenAI (기존 `OPENAI_API_KEY`). 채팅 모델은 설정값으로 분리 (예: `gpt-4o-mini`) |
| 캐시 | Redis `ai_recipe:{uuid}`, TTL 24h. 목록에서 `recipe_id` 발급, 상세는 ID 조회 |
| 만개 API | 변경 없음 |
| 구현 접근 | Approach 1 — LangChain Tool-Calling Agent + Redis 세션 |

## Out of Scope

- 만개 RAG / 크롤 파이프라인 변경
- AI 레시피 이미지·`source_url`
- AI 레시피 DB 영속 저장
- 사용자 취향·요리 스타일·시간 제한 옵션
- LangGraph 상태 머신
- 스트리밍 응답
- 비용/사용량 한도 UI
- 크롤 실패 시 AI 폴백 (소스는 탭으로만 분리)

## Architecture

```
앱 recipes 화면
  ├─ 탭: 만개  →  GET /recipes/recommendations
  │               GET /recipes/detail?board_name=&author_name=     [기존]
  └─ 탭: AI   →  GET /recipes/ai/recommendations
                  GET /recipes/ai/detail?recipe_id=                 [신규]

domains/ai_recipe/
  service.py   — 재료 로드, 에이전트 오케스트레이션, 캐시
  agent.py     — LangChain tool-calling agent (OpenAI chat)
  tools.py     — get_user_ingredients, propose_recipe_candidates,
                 classify_owned_missing, expand_recipe_detail
  schemas.py   — DTO
  cache.py     — Redis ai_recipe:{uuid} TTL 24h
```

인증은 기존 JWT와 동일하다. 재료는 서버가 `IngredientRepository`로 조회해 에이전트에 주입한다.

### Components

| 구성 | 역할 |
|------|------|
| `AiRecipeService` | 빈 재료 short-circuit, 목록/상세 오케스트레이션, 에러 매핑 |
| `AiRecipeAgent` | OpenAI tool-calling 루프 (최대 스텝·타임아웃) |
| Tools | 재료 조회, 후보 제안, owned/missing 분류, 상세 확장 |
| Redis cache | 목록 요약 + (확장 후) 상세 필드 저장 |
| 앱 탭 UI | 소스별 query / 상세 라우트 분기 |

## API · Data Contract

### `GET /api/v1/recipes/ai/recommendations`

Auth: JWT required.

**Response**

```text
AiRecipeRecommendation:
  recipe_id: uuid
  recipe_name: str
  owned_ingredients: list[str]
  missing_ingredients: list[str]
  recipe_difficulty: str
  time: str
  source: "ai"

AiRecipeRecommendationResponse:
  ingredients_used: list[str]
  recipes: list[AiRecipeRecommendation]   # 기본 5개
```

재료가 없으면 `ingredients_used: []`, `recipes: []`를 반환하고 LLM을 호출하지 않는다 (만개 추천과 동일).

### `GET /api/v1/recipes/ai/detail?recipe_id=`

Auth: JWT required.

**Response**

```text
AiRecipeDetailResponse:
  recipe_id: uuid
  recipe_name: str
  source: "ai"
  ingredients: list[{ name, amount }]
  steps: list[{ order, description }]
  tips: list[str]
  owned_ingredients: list[str]
  missing_ingredients: list[str]
  cached: bool
```

만개 상세 필드는 없다: `board_name`, `author_name`, `source_url`, `main_image_url`.

### Redis

| 항목 | 값 |
|------|-----|
| Key | `ai_recipe:{recipe_id}` |
| Value | 목록 요약 + (상세 확장 시) ingredients / steps / tips |
| TTL | 24h |

- 목록 생성 시 UUID를 발급하고 요약만 저장한다.
- 상세 요청 시 상세가 없으면 에이전트가 `expand_recipe_detail`로 채운 뒤 캐시를 갱신한다.
- 키가 없으면 **404** (자동 재생성 없음 — 클라이언트가 목록 API를 다시 호출).

## Agent Flow

### 목록

1. `IngredientRepository.get_ingredients(user.id)` → names
2. names 비면 빈 응답 (LLM 미호출)
3. Agent 실행:
   - `get_user_ingredients` — 보유 재료
   - `propose_recipe_candidates` — 이름·재료·난이도·시간 후보 **5개** (structured)
   - `classify_owned_missing` — 만개와 동일 정규화(strip + casefold + 공백 제거, 완전 일치)로 owned/missing
4. 후보마다 `recipe_id` 발급 → Redis 저장 → DTO 반환

### 상세

1. Redis `ai_recipe:{recipe_id}` 조회 → 없으면 404
2. 상세 필드가 이미 있으면 `cached=true`로 반환
3. 없으면 Agent `expand_recipe_detail` → Redis 갱신 → `cached=false`

### Constraints

- 채팅 모델: settings (예: `AI_RECIPE_MODEL=gpt-4o-mini`)
- 최대 tool-calling 루프: **8**
- 에이전트 전체 타임아웃: **60s**
- OpenAI·에이전트 실패 → 502 (`ExternalServiceException`)

## Frontend

| 영역 | 변경 |
|------|------|
| `recipes/index.tsx` | 상단 탭 「만개의 레시피」 \| 「AI 레시피」. 탭별 TanStack Query |
| `RecipeCard` | 공통 재사용. AI는 `board_name`/`author_name` 없음 |
| 상세 | 기존 `detail` 화면에서 `source=ai` + `recipe_id`로 분기 (출처·이미지·URL UI 숨김) |
| `src/api/recipes.ts` | `getAiRecipeRecommendations`, `getAiRecipeDetail` |
| `src/types/api.ts` | `AiRecipeRecommendation`, `AiRecipeDetail` |

만개 탭 동작·API 호출은 기존과 동일하다.

## Error Handling

| 상황 | HTTP / FE |
|------|-----------|
| 재료 없음 | 200 + 빈 `recipes` |
| Redis 미스 (detail) | 404 — FE 재시도 숨김 |
| OpenAI / 에이전트 실패·타임아웃 | 502 — FE 재시도 노출 |
| 네트워크 오류 | FE 재시도 노출 |

## Testing

**Backend**
- 단위: tools, owned/missing 분류, cache key/TTL, agent mock
- API: 빈 재료, 목록 성공, 상세 성공(캐시 hit/miss expand), 404, 502

**Frontend**
- 탭 전환 시 올바른 query 호출
- AI 상세 분기 (`recipe_id`, 이미지/URL 미표시)
- 404/502 UX (기존 패턴)

## Success Criteria

1. 만개 탭·API가 기존과 동일하게 동작한다.
2. AI 탭에서 냉장고 재료 기반 추천 카드 5개(기본)를 볼 수 있다.
3. AI 카드 탭 시 `recipe_id`로 재료량·조리 단계·팁 상세를 볼 수 있다.
4. 동일 `recipe_id` 재조회는 Redis 캐시 hit (`cached=true`).
5. 재료 없을 때 LLM을 호출하지 않는다.
6. OpenAI 장애 시 502, 만료/없는 ID는 404.
