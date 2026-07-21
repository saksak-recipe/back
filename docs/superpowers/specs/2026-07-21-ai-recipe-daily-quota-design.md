# AI 레시피 일일 호출 한도 (Redis)

날짜: 2026-07-21  
상태: Approved (대화에서 섹션별 승인 완료)  
선행 스펙: `2026-07-21-ai-recipe-agent-design.md`, `2026-07-21-group-ai-recommendations-design.md`

## Goal

OpenAI LLM이 실제로 호출되는 AI 레시피 생성에 **일일 호출 한도**를 걸어  
남용·비용 폭주를 막는다. 캐시 hit는 한도에 포함하지 않는다.

## Decisions

| 항목 | 선택 |
|------|------|
| 제한 방식 | Approach 1 — **Redis 일일 카운터** |
| 집계 단위 | LLM이 **실제로 호출될 때만** 1회 차감 |
| personal 한도 | 유저당 **15회/일** |
| group 한도 | 그룹당 **15회/일** |
| personal ↔ group | **완전 독립** (서로 차감에 영향 없음) |
| 리셋 | **KST 자정** |
| 대상 | `GET /recipes/ai/recommendations`, `GET /recipes/ai/detail`의 LLM path만 |
| 비대상 | 캐시 hit, 재료 없음 빈 응답, 만개 RAG 임베딩 |
| 초과 응답 | `429` + `ErrorCode.AI_QUOTA_EXCEEDED` |
| Redis 장애 | **fail-closed** (한도 검사 실패 시 호출 차단, 비용 보호) |
| LLM 실패 후 | 이미 차감한 카운트 **유지** (재시도 어뷰즈 방지) |
| 목록 내부 재시도 | `_generate_list` 최대 2회여도 **차감 1회** |
| 남은 횟수 API/헤더 | 이번 스코프 **없음** |

## Out of Scope

- 분당/초당 rate limit
- RAG(`text-embedding-3-small`) 호출 한도
- DB 영속 사용량 로그·빌링
- 사용량 조회 API / 응답 헤더의 remaining
- 플랜(유료)별 차등 한도
- 캡차·봇 방어

## Problem

AI 레시피 목록·상세는 JWT만 있으면 OpenAI를 호출할 수 있고,  
유저/그룹별 쿼터가 없다. `refresh=true`와 detail 미생성 경로로  
비용을 무제한 늘릴 수 있다. 기존 Redis 목록/상세 캐시는 비용을 줄이지만  
한도는 아니다.

## Architecture

```
[앱] AI 목록 / 상세
  → GET /api/v1/recipes/ai/recommendations|detail  (scope=personal|group)
       ↓
  [BE] AiRecipeService
       1. 재료 로드 / 캐시 조회 (기존과 동일)
       2. LLM이 필요한 시점에만 AiQuotaStore.consume(scope, owner_id)
            - 초과 → 429 AI_QUOTA_EXCEEDED (LLM 미호출)
            - 통과 → INCR 후 Agent 호출
       3. run_list / run_detail → Redis 캐시 갱신 → 응답
```

### Redis 키

| scope | 키 | owner |
|-------|-----|--------|
| personal | `ai_quota:personal:{user_id}:{YYYYMMDD}` | `user.id` |
| group | `ai_quota:group:{group_id}:{YYYYMMDD}` | `membership.group_id` |

- `{YYYYMMDD}`는 **Asia/Seoul** 기준 날짜
- `owner_id`는 기존 `ScopedIngredients.cache_owner_id`와 동일
- 키 최초 생성 시 TTL = **다음 KST 자정까지** 남은 초

### consume 알고리즘

1. `INCR key`
2. 값이 `1`이면 `EXPIRE`를 KST 다음날 00:00까지 설정
3. 값이 `AI_QUOTA_DAILY_LIMIT`(기본 15) **초과**면 `DECR` 후 `TooManyRequestsException` (429)
4. 그 외 통과

목록 `_generate_list`의 내부 2회 재시도는 consume **바깥**에서 한 번만 호출한다.

### Backend 변경

| 구성 | 변경 |
|------|------|
| `domains/ai_recipe/quota.py` | `AiQuotaStore` 신규 (키·KST TTL·consume) |
| `domains/ai_recipe/service.py` | LLM 직전 `quota.consume`; DI에 quota 추가 |
| `core/config.py` | `AI_QUOTA_DAILY_LIMIT: int = 15` |
| `core/exception/codes.py` | `AI_QUOTA_EXCEEDED` |
| `core/exception/exceptions.py` | `TooManyRequestsException` (status 429) |
| `api/deps.py` | `AiQuotaStore` 조립 후 `AiRecipeService`에 주입 |
| API 라우트/스키마 | **변경 없음** |

### Error

| status | code | detail (예) |
|--------|------|-------------|
| 429 | `AI_QUOTA_EXCEEDED` | `오늘 AI 레시피 생성 한도(15회)를 초과했습니다.` |

Redis 장애 시: 기존 verification store와 같이 `ExternalServiceException`(또는 동등)으로 실패 — **LLM은 호출하지 않음**.

## Testing

| 케이스 | 기대 |
|--------|------|
| 목록 캐시 hit | 카운트 증가 없음, 200 |
| detail 이미 있음 | 카운트 증가 없음, 200 |
| 재료 없음 | 카운트 증가 없음, 빈 배열 200 |
| LLM 목록 1회 | personal(또는 group) 카운트 +1 |
| 같은 날 15회 후 16번째 | 429 `AI_QUOTA_EXCEEDED`, LLM 미호출 |
| personal 15회 소진 후 group LLM | group은 별도 15회 가능 |
| group 15회 소진 후 personal LLM | personal은 별도 15회 가능 |
| `_generate_list` 내부 재시도 2회 | 차감 1회만 |
| LLM 실패 후 재요청 | 이전에 차감된 카운트 유지 |
| KST 날짜 키 | 자정 지나면 새 키로 카운트 0부터 |

## Success Criteria

- LLM path만 차감되고 캐시 hit는 무료
- personal / group 한도가 서로 영향 없음
- 한도 초과 시 OpenAI 미호출 + 명확한 429
- 설정값으로 한도 조정 가능 (`AI_QUOTA_DAILY_LIMIT`)
