# 핵심 루프 심화 — 유통기한 추천 · 동의어 매칭 · AI 속도·품질 안정화

날짜: 2026-07-21  
상태: Approved (대화에서 섹션별 승인 완료)  
관련 스펙:
- `2026-07-20-recipe-recommendation-rag-design.md`
- `2026-07-20-recipe-owned-missing-ingredients-design.md` (매칭 규칙 **이 스펙으로 대체**)
- `2026-07-21-ai-recipe-agent-design.md`
- `2026-07-21-ai-recipe-speed-refresh-design.md` (목록 생성 방식·캐시 정책 **이 스펙으로 갱신**)

## Goal

냉장고 → 추천 → owned/missing 핵심 루프를 깊게 만든다.

1. **유통기한 기반 추천:** soon·expired 재료를 쿼리/프롬프트 힌트 + 결과 재정렬로 우선 소진
2. **재료 동의어 매칭:** 정적 사전 + 최소 부분일치로 owned/missing 정확도 향상 (RAG·AI 공통)
3. **AI 속도·품질 안정화:** 목록은 structured 1회 + 단기 캐시, 상세는 기존 확장, 실패 시 1회 재시도

## Decisions

| 항목 | 선택 |
|------|------|
| 범위 | 세 축을 **하나의 스펙/에픽**으로 (구현은 플랜에서 단계 분할) |
| 아키텍처 | 공유 `ingredient_matching` 레이어 + RAG/AI 파이프라인 훅 |
| 유통기한 반영 | **힌트 + 재정렬** (검색/프롬프트 가중 + 후보 urgency 재랭킹) |
| RAG 최종 선택 | urgent ≥1이면 재정렬 상위 `TOP_K` 고정. urgent 0이면 기존 `random.sample` |
| expired 취급 | soon과 동일 — **urgent(소진 대상)** |
| 동의어 | **정적 사전 + 최소 부분일치** (사전 우선) |
| AI 목록 | structured output **1회**, 타임아웃 **~20–25초** |
| AI 상세 | 기존 detail/expand 경로 유지 |
| AI 목록 캐시 | Redis 단기 캐시 (재료 집합 해시). CRUD 시 무효화 |
| 새로고침 | `refresh=true`(또는 동등)면 캐시 우회·강제 재생성. 미지정 시 캐시 히트 가능 |
| API 브레이킹 | 없음. 기존 엔드포인트·응답 계약 유지 (optional 필드만 허용) |
| 동의어 저장소 | v1은 코드/JSON 시드. DB·어드민 없음 |
| RAG↔AI 폴백 | 하지 않음 (소스 혼동 방지) |

## Out of Scope

- 동의어 DB 관리 UI·어드민
- 임베딩/LLM 기반 유사 재료 판단
- 만개 크롤 상세의 재료 파싱 고도화
- AI↔RAG 혼합 폴백
- 스트리밍 응답
- 유통기한 알림 푸시
- 모델명 강제 변경 배포

## Problem

1. `expiration_date` / status는 목록 정렬에만 쓰이고, RAG·AI 추천은 재료 **이름만** 본다 → 임박·지난 재료가 우선 소진되지 않는다.
2. owned/missing는 `normalize_name` 후 **완전 일치만** → “계란↔달걀” 등이 missing으로 떨어진다.
3. AI는 속도 스펙(structured 1회·~20s)과 달리 멀티스텝 tool-calling·60s로 복귀해 체감·타임아웃이 불안정하다. 목록 전체 캐시가 없어 동일 재료로도 매번 풀 생성한다.

## Architecture

```
ingredients (name + expiration)
        │
        ▼
┌─────────────────────────────┐
│  ingredient_matching        │
│  - normalize_name           │
│  - synonym dict + substring │
│  - urgency (soon|expired)   │
│  - classify_owned_missing   │
└─────────────┬───────────────┘
              │
     ┌────────┴────────┐
     ▼                 ▼
  RAG 추천          AI 추천
  · 쿼리 가중        · structured 목록 1회
  · owned/missing    · urgency 힌트 프롬프트
  · urgency 재정렬   · 목록 Redis 캐시
                     · 상세는 기존 확장
                     · 실패 시 1회 재시도
```

공유 매칭 레이어 위치는 구현 시 기존 도메인 패턴에 맞춘다  
(예: `src/domains/ingredient_matching/` 또는 `ingredient` 패키지 하위 모듈).  
RAG mapper·AI tools의 exact match는 이 레이어의 `names_match` / `classify_owned_missing`로 교체한다.

## Components

### `ingredient_matching`

| 단위 | 역할 |
|------|------|
| `normalize_name` | strip · casefold · 공백 제거. 단일 진입점 |
| `synonym_dict` | canonical → aliases (예: `달걀` ← 계란, 에그) |
| `names_match(a, b)` | 정규화 후 (1) 동일 동의어 그룹 (2) 아니면 짧은 쪽이 긴 쪽에 포함. **2글자 미만 부분일치 금지** |
| `urgency_of(ingredient)` | `expired`·`soon`(≤3일, 기존 `compute_status`와 동일) → `urgent`; `ok`/`unknown` → `normal` |
| `classify_owned_missing` | 레시피 재료 vs 사용자 재료를 `names_match`로 분류. RAG·AI 공통 |

사전 로드 실패 시 빈 사전 + normalize/exact(동일 문자열)만으로 degrade. 매칭 실패는 예외가 아니라 missing.

### 유통기한 → RAG

1. 사용자 재료에서 urgent 이름 목록 추출
2. 벡터 쿼리에 urgent 이름을 앞에 두거나 반복해 **검색 가중**
3. top-N 후보에 대해 “urgent 재료를 몇 개 쓰는지”(owned ∩ urgent)로 **재정렬**
4. **선택 규칙:** urgent 재료가 1개 이상이면 재정렬 결과의 **상위 `TOP_K`를 고정 선택** (기존 `random.sample`은 urgency를 깨므로 이 경우 사용하지 않음). urgent가 0개면 기존과 동일하게 후보에서 `random.sample(TOP_K)`

### 유통기한 → AI 목록

- 프롬프트에 `우선 소진: [...]` 힌트 주입
- structured 스키마로 후보 생성 시 urgent 활용을 유도하되, owned/missing는 **서버 `classify_owned_missing`만** 신뢰 (LLM 환각 방지)
- expired는 soon과 동일하게 urgent 목록에 포함

### AI 속도·품질

| 단계 | 동작 |
|------|------|
| 목록 | `with_structured_output`(또는 동등) **1회**. 후보 정확히 `TOP_K`(5)개 |
| 타임아웃 | `AGENT_TIMEOUT_SECONDS` ≈ 20–25 |
| 캐시 | Redis `ai_recipe_list:{user_id}` (+ 재료 집합 해시). TTL 단기(예: 10–30분). 재료 CRUD 시 해당 user 키 무효화 |
| 새로고침 | 쿼리 `refresh=true`면 캐시 우회 후 재생성·캐시 갱신 |
| 상세 | 기존 Redis recipe 캐시 + detail 확장 경로 유지 |
| 재시도 | 타임아웃·파싱·개수 불일치 시 **1회 재시도**. 부분 성공(3개 등)은 폐기 |
| 최종 실패 | 기존 `ExternalServiceException`(502) |
| Redis 장애 | 캐시 없이 생성 (가용성 우선). 무효화 실패는 로그 + TTL로 해소 |
| 모델 | `AI_RECIPE_MODEL` 설정값 유지 |

목록 경로에서 tool-calling 멀티스텝 루프는 사용하지 않는다.  
`tools.py`의 목록 생성용 tool은 제거하거나 dead code로 정리한다.

## Data flow

### RAG `GET /recipes/recommendations`

1. 사용자 ingredients 로드
2. matching 레이어로 urgent 목록·정규화 이름 집합 준비
3. retriever 쿼리 구성 (urgent 가중) → top-N
4. urgency 재정렬 후 위 선택 규칙으로 `TOP_K` 확정
5. 각 후보 `classify_owned_missing` → 응답

### AI `GET /recipes/ai/recommendations`

1. 재료 로드. 빈 재료면 빈 배열
2. `refresh`가 아니고 캐시 히트(동일 재료 해시)면 캐시 반환
3. structured 목록 1회 (+ urgency 힌트). 실패 시 1회 재시도
4. 후보마다 UUID + 서버 classify + 개별 recipe Redis set
5. 목록 캐시 저장 후 응답

### AI `GET /recipes/ai/detail`

기존과 동일. 본 스펙에서 목록 경로만 구조적으로 변경.

## API

- 경로 유지: `/api/v1/recipes/recommendations`, `/api/v1/recipes/ai/recommendations`, `/api/v1/recipes/ai/detail`, ingredients CRUD
- `GET .../ai/recommendations`에 optional `refresh: bool` 쿼리 추가 (기본 false)
- 응답 스키마 브레이킹 변경 없음. optional 디버그/표시 필드(`matched_via` 등)는 필요 시만, 공개 API 필수는 아님
- ingredients CRUD 성공 시 해당 user의 AI 목록 캐시 무효화

## Error handling

| 상황 | 동작 |
|------|------|
| 동의어 사전 로드 실패 | 빈 사전 + exact/normalize degrade |
| 매칭 실패 | missing |
| expiration 없음 | urgency = normal |
| AI 1회 재시도 후 실패 | 502 |
| Redis 캐시/무효화 실패 | 생성 계속 / 로그 |
| urgent 0 | RAG·AI 힌트·재정렬 스킵 (기존 동작) |

## Testing

- **unit:** `names_match` (동의어·부분일치·2글자 가드)·`urgency_of`·`classify_owned_missing` 회귀
- **unit:** RAG 재정렬 — urgent 교집합이 큰 후보가 상위
- **unit/integration:** AI structured 목록 5개 강제·재시도·캐시 히트·`refresh=true` 미스·재료 PATCH/DELETE 후 캐시 무효화
- **회귀:** 기존 recommendations / ai recommendations / detail 응답 계약

## Success criteria

1. 동의어 그룹(예: 계란↔달걀)이면 owned로 분류된다
2. urgent(soon+expired)가 RAG 쿼리·재정렬과 AI 프롬프트 힌트에 반영된다
3. AI 목록이 structured 1회 경로로 동작하고, 타임아웃 ~20–25s·1회 재시도로 안정화된다
4. 재료 불변·`refresh` 없음이면 목록 캐시로 즉시 응답한다
5. `refresh=true`면 새 후보를 생성한다

## Implementation notes (for plan)

권장 구현 순서:

1. `ingredient_matching` + 동의어 시드 + classify 교체 (RAG·AI)
2. urgency + RAG 힌트/재정렬
3. AI structured 목록 복귀 + 타임아웃·재시도
4. 목록 캐시 + refresh + 재료 CRUD 무효화

이 순서로 매칭 회귀를 먼저 고정한 뒤 추천 품질·속도 레이어를 올린다.
