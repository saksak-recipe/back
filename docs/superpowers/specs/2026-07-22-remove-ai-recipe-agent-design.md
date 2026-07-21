# AI 에이전트 레시피 기능 제거

날짜: 2026-07-22  
상태: Approved (대화에서 섹션별 승인 완료)  
관련: RAG `2026-07-20-recipe-recommendation-rag-design.md`, 크롤 `2026-07-20-recipe-detail-10000recipe-design.md`

## Goal

LLM 기반 AI 에이전트 레시피(`/recipes/ai/*`)를 백엔드에서 **완전히 제거**하고,  
**RAG 추천**과 **만개 크롤 상세**만 남긴다.  
이미 저장된 `source=ai` 레코드는 마이그레이션으로 삭제한다.

## Decisions

| 항목 | 선택 |
|------|------|
| 접근 | Approach 1 — 하드 삭제 (코드·설정·라우트·테스트) |
| 기존 AI 저장 | **C.** `DELETE FROM saved_recipes WHERE source = 'ai'` |
| Saved API | `source`는 **`mangae`만** 허용 |
| RAG / 크롤 | 경로·동작 유지 |
| `OPENAI_API_KEY` | **유지** (RAG 임베딩) |
| Redis AI 키 | 강제 flush 없음 (TTL 자연 만료) |
| 앱(프론트) | Out of Scope |

## Out of Scope

- 앱 AI 탭·`/recipes/ai/*` 호출 제거
- RAG·만개 크롤 로직/성능 변경
- embedding 모델·`OPENAI_API_KEY` 변경
- 삭제된 AI 저장 레시피 복구
- Redis `ai_recipe*` / `ai_quota*` 강제 삭제 스크립트

## Problem

AI 에이전트 상세/추천은 LLM latency로 체감·타임아웃 문제를 반복한다.  
스트리밍 등 완화책을 넣어도 제품 목표 속도를 맞추기 어렵다.  
반면 RAG 벡터 추천과 만개 크롤은 독립 파이프라인이며 유지할 가치가 있다.

## Architecture (after)

```
[앱]
  GET /api/v1/recipes/recommendations     → domains/rag/
  GET /api/v1/recipes/detail              → domains/recipe_detail/
  /api/v1/recipes/saved/*                 → domains/saved_recipe/ (mangae only)

제거됨:
  GET /recipes/ai/recommendations
  GET /recipes/ai/detail
  GET /recipes/ai/detail/stream
  domains/ai_recipe/
```

### Backend 변경

| 구성 | 변경 |
|------|------|
| `src/domains/ai_recipe/` | **디렉터리 삭제** |
| `src/api/v1/endpoints/rag.py` | `/ai/*` 3라우트·AI import 제거 |
| `src/api/deps.py` | `get_ai_recipe_service` 및 AI wiring 제거; ingredient/group/saved에서 AI 의존 제거 |
| `ingredient/service.py`, `group/service.py` | `AiRecipeCache.invalidate_list` 호출 제거 |
| `saved_recipe/service.py` | `source=="ai"` 분기·`AiRecipeService` 의존 제거 |
| `saved_recipe/schemas.py` | `Literal["mangae"]` (또는 동등) |
| `core/config.py` | `AI_RECIPE_MODEL`, `AI_QUOTA_DAILY_LIMIT` 제거 |
| `ErrorCode.AI_QUOTA_EXCEEDED` / 관련 테스트 | 다른 사용 없으면 제거 |
| Alembic | head(`h8i9j0k1l2m3`) 다음 revision: AI saved rows DELETE |
| AI 전용 테스트·문서 | 삭제 또는 AI 섹션 정리 |

### 마이그레이션

```sql
-- upgrade
DELETE FROM saved_recipes WHERE source = 'ai';
```

- `downgrade`: **no-op** (스냅샷 복구 불가 — 명시)
- DB `source` 컬럼 타입(`String(16)`)은 유지; 앱에서 `mangae`만 수락

### Saved API 계약

| 항목 | 동작 |
|------|------|
| `POST` save `source=ai` | **422** (validation) |
| `POST` save `source=mangae` | 기존과 동일 (크롤/상세 스냅샷) |
| list/get/delete/status | mangae 행만 존재 (마이그레이션 후) |

### Breaking changes (클라이언트)

- `/api/v1/recipes/ai/*` → **404**
- AI 레시피 저장 요청 → **422**
- 기존 AI 저장 목록 항목 사라짐

## Error Handling

| 상황 | 동작 |
|------|------|
| 제거된 `/ai/*` 호출 | FastAPI 404 |
| `source=ai` 저장 | Pydantic/422 |
| 마이그레이션 | 표준 Alembic; downgrade는 데이터 복구 없음 |

## Testing

- 삭제: `tests/**/test_ai_recipe*`, `test_ai_quota*`
- 수정: saved AI 케이스 제거; ingredient/group AI cache invalidate assertion 제거
- 유지·통과: RAG API/unit, recipe_detail API/unit, saved mangae 경로

## Success Criteria

1. `/recipes/ai/*` 라우트와 `domains/ai_recipe` 코드가 없음
2. `GET /recommendations`, `GET /detail`, saved mangae가 기존과 같이 동작
3. 마이그레이션 적용 후 `saved_recipes`에 `source='ai'` 행이 없음
4. `AI_RECIPE_MODEL` / `AI_QUOTA_DAILY_LIMIT` 설정 키 없음
5. AI 전용 단위·API 테스트 파일 없음; 관련 회귀 스위트 PASS
