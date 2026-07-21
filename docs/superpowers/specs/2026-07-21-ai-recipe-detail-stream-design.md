# AI 레시피 상세 SSE 스트리밍

날짜: 2026-07-21  
상태: Approved (대화에서 섹션별 승인 완료)  
선행 스펙: `2026-07-21-ai-recipe-agent-design.md`, `2026-07-21-ai-recipe-speed-refresh-design.md`

## Goal

`GET /recipes/ai/detail` 콜드 경로에서 LLM이 25초를 넘기기 쉬운 체감 대기 문제를 줄인다.  
**전체 생성은 25초 안에 끝내고**, 완료 전에도 **섹션 단위(재료 → 단계 → tips)** 로 앱에 먼저 보여 준다.

## Decisions

| 항목 | 선택 |
|------|------|
| 접근 | Approach 1 — SSE + LLM **1회** 스트림 + 부분 JSON 파싱 |
| 스트림 UX | **B.** 섹션 단위 (`ingredients` → `steps` → `tips`) |
| 완료 시한 | 전체 생성 **≤ 25초** (기존 `AGENT_TIMEOUT_SECONDS` / `LLM_TIMEOUT_SECONDS` 유지) |
| 전송 | SSE (`text/event-stream`) |
| 신규 경로 | `GET /api/v1/recipes/ai/detail/stream` |
| 기존 경로 | `GET /api/v1/recipes/ai/detail` **유지** (비스트림·캐시 hit용) |
| LLM 호출 | 상세 miss당 structured/JSON **1회** (섹션별 다중 호출 없음) |
| 캐시 | 전체 섹션 완성·validate 후에만 Redis 갱신. 부분 실패 시 미저장 |
| 모델 | `AI_RECIPE_MODEL` 설정값 유지 (강제 교체 없음) |

## Out of Scope

- 목록(`/ai/recommendations`) 스트리밍
- WebSocket
- 토큰/한 줄 단위 스트리밍
- 모델명 강제 변경 배포
- 부분 섹션만 Redis에 저장
- 목록 생성 시 상세 백그라운드 prefetch
- 프론트엔드 구현 세부 (이 스펙은 API 계약만)

## Problem

속도 개선 이후에도 상세는 Redis miss 시 `AiRecipeAgent.run_detail` **1회 structured invoke**에 묶여 있다.  
응답이 끝날 때까지 앱은 빈 화면을 보고, LLM이 느리면 `asyncio.wait_for(..., 25)` / OpenAI `timeout=25`에 걸려 `ExternalServiceException`이 난다.  
호출 횟수를 늘리지 않으면서(품질·일관성 유지) **첫 유의미한 UI**를 앞당길 필요가 있다.

## Architecture

```
[앱] AI 상세
  → GET /api/v1/recipes/ai/detail/stream?recipe_id=&scope=
       ↓
  [BE] AiRecipeService.stream_detail
       1. Redis get(recipe_id)
          - miss → HTTP 404 (스트림 시작 전)
          - hit + has_detail → SSE: meta → ingredients → steps → tips → done (즉시)
          - hit + no detail →
              a. SSE meta
              b. quota.consume (기존 상세와 동일)
              c. agent.stream_detail — OpenAI JSON/structured 스트림 1회
              d. 부분 파서: ingredients / steps / tips 배열이 닫힐 때 각각 SSE emit
              e. Pydantic validate → Redis set → done
              f. 실패·25초 초과 → error 후 종료 (캐시 미저장)
```

기존 `GET /ai/detail`는 `run_detail` + 일괄 응답을 그대로 둔다.  
스트림 완료 후 캐시가 채워지면 비스트림 경로도 즉시 hit한다.

### SSE 이벤트

| event | data | 시점 |
|--------|------|------|
| `meta` | `{ recipe_id, recipe_name, owned_ingredients, missing_ingredients, cached }` | 시작 직후 (또는 캐시 hit 시) |
| `ingredients` | `[{ name, amount }, ...]` | 해당 JSON 필드 완성 시 |
| `steps` | `[{ order, description }, ...]` | 동일 |
| `tips` | `string[]` | 동일 |
| `done` | `{ cached: bool }` | 캐시 hit면 즉시 / miss면 Redis 저장 후 |
| `error` | `{ detail }` | 실패 시. 이후 스트림 종료 |

이벤트 순서는 항상 `meta` → (`ingredients` → `steps` → `tips`) → `done`  
(또는 중간에 `error`). 캐시 hit에서도 동일 순서로 즉시 push해 앱 경로를 하나로 맞춘다.

### Backend 변경

| 구성 | 변경 |
|------|------|
| `agent.py` | `stream_detail` 추가. 프롬프트·스키마는 `run_detail`과 동일. `run_detail` 유지 |
| 부분 파서 | 스트림 버퍼에 JSON 누적. `ingredients` / `steps` / `tips` 배열이 **닫히는 순간** 각각 1회 yield |
| `service.py` | `stream_detail` 오케스트레이션. 타임아웃 25초. 최종 validate 후 `cache.set` |
| `rag.py` (또는 AI 라우터) | `GET /ai/detail/stream` → `StreamingResponse` / SSE |
| 스키마 | 섹션 payload는 기존 `AiRecipeIngredient` / `AiRecipeStep` / tips 재사용 |

### Frontend 계약 (앱 레포)

| 항목 | 내용 |
|------|------|
| 권장 API | AI 상세는 `/recipes/ai/detail/stream` |
| UI | `ingredients` 도착 시 재료 영역, `steps` 시 단계, `tips` 시 팁 표시 |
| 완료 | `done`에서 로딩 해제 |
| 실패 | `error` → 기존 “다시 시도” UX |
| HTTP timeout | 스트림 연결 **≥ 25초** (전역 15초면 끊김) |

## Error Handling

| 상황 | 동작 |
|------|------|
| Redis miss (`recipe_id` 없음) | HTTP **404** — 스트림 시작 전 |
| LLM 타임아웃 / OpenAI 오류 / 파싱·validate 실패 / 25초 초과 | SSE `error` + 연결 종료. **이미 emit한 섹션은 롤백하지 않음**. Redis **미저장** |
| quota 초과 | 기존 quota 예외와 동일 (가능하면 스트림 시작 전 HTTP 에러) |
| 비스트림 `/ai/detail` 실패 | 기존 `ExternalServiceException` 메시지 유지 |

## Testing

- 단위: `stream_detail`가 mock 스트림에서 섹션 순서로 yield
- 단위: 부분 파서가 불완전 JSON에서 배열 닫힘 시에만 emit
- 단위: service가 성공 시 Redis set, 실패 시 set 안 함
- API: `/ai/detail/stream` 캐시 hit / miss(mock agent) / 404
- 기존 `/ai/detail` 회귀 유지

## Success Criteria

1. 콜드 상세가 **25초 안에** `done` 또는 `error`
2. miss 시 재료 → 단계 → tips 순으로 섹션이 완료본보다 먼저 표시 가능
3. hit는 LLM 없이 즉시 동일 이벤트 순서
4. 스트림 완료 후 Redis hit면 `/ai/detail`도 즉시 응답
5. 목록 API·응답 스키마·모델 설정 강제 변경 없음
