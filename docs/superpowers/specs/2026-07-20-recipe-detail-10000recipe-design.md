# 만개의 레시피 상세 연동 (검색 + 크롤 + 앱 UI)

날짜: 2026-07-20  
상태: Approved (대화에서 섹션별 승인 완료)

## Goal

추천 API가 반환하는 `board_name` + `author_name`으로 만개의 레시피(https://www.10000recipe.com)에서  
해당 레시피를 검색·매칭한 뒤, 재료·조리 순서·팁·요리 사진을 가져와 앱에 표시한다.

## Decisions

| 항목 | 선택 |
|------|------|
| 레시피 식별 | `board_name` + `author_name`으로 사이트 검색 (RCP_SNO 재적재 없음) |
| 크롤 위치 | 백엔드 전용 |
| 매칭 | 제목·작성자 유사도 최고 1건 자동 선택, 실패 시 404 |
| 캐시 | 인메모리 TTL 24시간 |
| 범위 | 백엔드 상세 API + 앱 추천 목록·상세 화면 |
| 접근 | 동기 HTTP 크롤 + TTL 캐시 (비동기 job / 웹뷰 제외) |

## Out of Scope

- Redis / DB 영구 캐시
- `RCP_SNO`를 벡터 메타에 재적재
- 앱에서 만개의 레시피 직접 fetch
- 웹뷰로 원문 페이지 인앱 브라우징
- 댓글·평점·관련 레시피
- 매칭 후보 다중 선택 UI

## Architecture

```
앱
  GET /api/v1/recipes/recommendations     → 추천 목록 (기존 RAG)
  GET /api/v1/recipes/detail
       ?board_name=&author_name=          → 상세 (신규)
       │
       ▼
RecipeDetailService
  1) 캐시 키 = hash(normalize(board_name)|normalize(author_name))
  2) hit → DTO (cached=true)
  3) miss → RecipeCrawler
       a) 검색: board_name을 검색어로 사용
       b) 결과에서 author_name·제목 유사도 최고 1건 URL 선택
       c) 상세 페이지 fetch → 재료 / 순서 / 팁 / 사진 파싱
  4) TTL 24h 캐시 저장 후 DTO 반환 (cached=false)
```

### Components

| 구성 | 역할 |
|------|------|
| `RecipeCrawler` | HTTP fetch + HTML / `ld+json` 파싱 |
| 인메모리 TTL 캐시 | 프로세스 내 캐시 (재시작 시 소멸) |
| `RecipeDetailService` | 캐시 오케스트레이션 + 에러 매핑 |
| 앱 screens | 추천 목록 → 상세, TanStack Query |

기존 RAG 추천 레이어와 분리한다. 동기 외부 HTTP는 `asyncio.to_thread` 등으로 이벤트 루프 블로킹을 피한다.

## Crawling · Matching · Cache

### Search

- 검색어: `board_name` (특수문자 정리 후 사용)
- 결과 목록에서 `author_name` 정규화 일치 + 제목 유사도(단순 포함/정규화 일치 우선)를 점수화해 최고 1건 선택
- 채택 조건: 작성자 정규화 일치 **또는** 제목에 `board_name` 핵심어가 포함될 때만 채택
- 후보 0건이거나 채택 조건 불충족 → `404`

### Detail parsing (priority)

1. 페이지 내 `application/ld+json` (Recipe schema) — 재료·순서·이미지
2. 부족 필드는 HTML 셀렉터로 보완 (재료 리스트, step, tip, 단계별 사진)

### Cache

- Key: `normalize(board_name) + "|" + normalize(author_name)` 해시
- TTL: 24시간, 인메모리
- hit 시 크롤 생략, 응답 `cached: true`

### Operational constraints

- User-Agent 명시
- 요청 타임아웃: 10초
- 동시 크롤 과다 방지 (간단한 세마포어/락)
- 크롤은 백엔드만 수행

## API Contract

### `GET /api/v1/recipes/detail`

- Auth: Bearer JWT
- Query (required): `board_name`, `author_name`
- Success: `200`

```json
{
  "board_name": "아이들 영양 간식으로 좋은 닭꼬치 & 콘치즈",
  "author_name": "GP하루한끼",
  "recipe_name": "닭꼬치",
  "source_url": "https://www.10000recipe.com/recipe/6891574",
  "main_image_url": "https://...",
  "ingredients": [
    { "name": "닭가슴살", "amount": "200g" }
  ],
  "steps": [
    {
      "order": 1,
      "description": "...",
      "tip": "있을 때만",
      "image_url": "https://... 또는 null"
    }
  ],
  "tips": ["전체 팁이 있으면"],
  "cached": false
}
```

| 상황 | HTTP | 의미 |
|------|------|------|
| 매칭 실패 / 페이지 없음 | 404 | 검색·상세를 찾지 못함 |
| 사이트 타임아웃·파싱 실패 | 502 | 외부 의존 실패 |
| 파라미터 누락 | 422 | validation |

기존 `GET /api/v1/recipes/recommendations` 응답 필드는 변경하지 않는다.  
앱은 추천 카드의 `board_name` / `author_name`을 detail API에 그대로 전달한다.

## App UI

| 화면 | 경로 | 내용 |
|------|------|------|
| 추천 목록 | `(main)/recipes/index` | recommendations API → 카드 (`recipe_name`, 재료, 난이도, 시간) |
| 상세 | `(main)/recipes/detail` | query로 `board_name`/`author_name` → detail API |

- 메인 네비에 레시피 진입점 추가
- 목록 카드 탭 → `router.push`로 상세
- TanStack Query: `useRecipeRecommendations`, `useRecipeDetail`
- Axios + JWT — 식재료 API와 동일 클라이언트

### Error / loading UX

- 목록·상세 로딩: 기존 앱 패턴의 스피너/스켈레톤
- 404: “해당 레시피를 찾지 못했어요”
- 502 / 네트워크: “레시피를 불러오지 못했어요. 다시 시도해 주세요” + 재시도
- `cached` 필드는 UI에 표시하지 않음

## Testing

- 백엔드: crawler 단위 테스트(픽스처 HTML/`ld+json`), detail API 통합 테스트(캐시 hit/miss, 404/502)
- 앱: API 훅·화면은 기존 패턴에 맞춰 수동/최소 스모크 (별도 E2E 필수는 아님)

## Relation to existing RAG design

- 선행 스펙: `2026-07-20-recipe-recommendation-rag-design.md`
- 본 스펙은 추천 결과의 **상세 보강**이며, 벡터 검색·임베딩 파이프라인은 변경하지 않는다.
