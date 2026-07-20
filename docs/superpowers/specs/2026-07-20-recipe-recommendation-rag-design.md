# 식재료 기반 레시피 추천 (RAG 검색)

날짜: 2026-07-20  
상태: Approved (대화에서 섹션별 승인 완료)

## Goal

로그인한 사용자의 보유 식재료로 `saksak_rag.recipe_vectors`에서 유사 레시피 top-5를 찾아  
`GET` API로 반환한다. LLM 생성 없이 벡터 유사도 검색만 사용한다.

## Decisions

| 항목 | 선택 |
|------|------|
| 검색 방식 | LangChain PGVector `similarity_search_with_score` (임베딩 적재와 동일 스택) |
| LLM | 없음 (임베딩 API만 사용) |
| 반환 개수 | 고정 5개 |
| 범위 | 백엔드 API만 (프론트 제외) |
| score | 응답에 포함 |
| 빈 식재료 | 200 + 빈 `recipes` (외부 호출 없음) |

## Out of Scope

- 프론트엔드 UI / API 클라이언트
- LLM으로 요리법·부족 재료 설명 생성
- 재료 교집합 재랭킹(하이브리드)
- `limit` 쿼리 파라미터
- 레시피 상세 CRUD / 원본 CSV 조인

## Architecture

```
Client
  GET /api/v1/recipes/recommendations  (Bearer JWT)
       │
       ▼
rag endpoint → RagService
       │
       ├─ IngredientRepository: 현재 유저 식재료 조회 (앱 DB: saksak)
       ├─ 쿼리 문자열 빌드
       │    "parsed_ingredients: 계란, 양파, 대파"
       ├─ OpenAIEmbeddings(model=text-embedding-3-small)
       ├─ PGVector(collection_name=recipe_vectors, DB=saksak_rag)
       ├─ similarity_search_with_score(k=5)
       └─ Document → RecipeRecommendation DTO
```

### Databases

| DB | 용도 | 접근 |
|----|------|------|
| `saksak` | users, ingredients | 기존 async SQLAlchemy (`asyncpg`) |
| `saksak_rag` | `recipe_vectors` (적재 완료) | LangChain PGVector sync (`postgresql+psycopg://...`) |

Sync PGVector 호출은 `asyncio.to_thread` (또는 `run_in_executor`)로 감싸 이벤트 루프 블로킹을 피한다.

### Embedding / Collection (적재와 일치)

- Model: `text-embedding-3-small`
- Collection: `recipe_vectors`
- Document `page_content`:  
  `recipe_name: {name}\nparsed_ingredients: {ingredients}`
- Metadata: `board_name`, `author_name`, `recipe_difficulty`, `time`

검색 쿼리도 적재 포맷에 맞춰 `parsed_ingredients: ...` 형태로 맞춘다.

## API Contract

### `GET /api/v1/recipes/recommendations`

- Auth: Bearer JWT (기존 ingredient API와 동일)
- Query params: 없음
- Success: `200`

```json
{
  "ingredients_used": ["계란", "양파", "대파"],
  "recipes": [
    {
      "recipe_name": "계란볶음밥",
      "parsed_ingredients": "계란, 밥, 대파, 간장",
      "board_name": "...",
      "author_name": "...",
      "recipe_difficulty": "초급",
      "time": "15분",
      "score": 0.82
    }
  ]
}
```

### Response rules

- `recipes` 최대 5개, 유사도 높은 순
- `score`: `similarity_search_with_score`가 반환하는 거리(distance) float를 그대로 넣는다.  
  값이 작을수록 유사하다. 스키마 Field description에 이를 명시한다.  
  (클라이언트는 상대 비교용으로만 사용)
- `recipe_name` / `parsed_ingredients`: `page_content`에서 파싱
- 메타데이터 필드 누락 시 빈 문자열
- 식재료 0개: `{ "ingredients_used": [], "recipes": [] }`

### Errors

| 상황 | HTTP | 예외 |
|------|------|------|
| JWT 없음/만료 | 401 | 기존 auth 예외 |
| OpenAI 임베딩 실패 | 502 | `ExternalServiceException` |
| RAG DB / PGVector 실패 | 500 | `DatabaseException` |
| 단일 Document 파싱 실패 | — | 해당 건 스킵, 나머지 반환 |

## Components

| 파일 | 역할 |
|------|------|
| `src/api/v1/endpoints/rag.py` | 라우터: prefix `/recipes`, `GET /recommendations` |
| `src/domains/rag/schemas.py` | `RecipeRecommendation`, `RecipeRecommendationResponse` |
| `src/domains/rag/service.py` | 오케스트레이션 |
| `src/domains/rag/retriever.py` | Embeddings + PGVector 팩토리/싱글톤 |
| `src/api/deps.py` | `get_rag_service` |
| `src/core/config.py` | `database_rag_sync_url` (`postgresql+psycopg://.../saksak_rag`) |

재사용: `IngredientRepository`로 유저 식재료 조회.

의존성: `psycopg[binary]` (또는 `psycopg`)가 없으면 `pyproject.toml`에 추가.  
이미 있는 `langchain-openai`, `langchain-postgres`, `OPENAI_API_KEY` 활용.

참고: `api.py`는 이미 `rag` 라우터를 import하므로 `rag.py` 생성으로 기동 깨짐을 해소한다.

## Data Flow (service)

1. JWT → `User` (deps)
2. `ingredient_repo.get_ingredients(user.id)` (또는 동등)
3. names = `[i.ingredient_name for i in ingredients]`
4. names 비면 early return
5. `query = "parsed_ingredients: " + ", ".join(names)`
6. `docs_with_scores = await to_thread(retriever.search, query, k=5)`
7. 각 Document 매핑 → `RecipeRecommendation`
8. `RecipeRecommendationResponse(ingredients_used=names, recipes=...)`

## Testing

- Unit: 쿼리 문자열 빌드, page_content 파싱, 빈 식재료 early return, score 매핑
- API: 미인증 401; 식재료 없을 때 빈 목록 (retriever mock, OpenAI/DB 실호출 없음)
- 실벡터 E2E는 선택(로컬 `saksak_rag` 있을 때만)

## Success Criteria

- 인증된 사용자가 식재료가 있을 때 최대 5개 레시피 + score 수신
- 식재료 없을 때 빈 배열, 임베딩/DB 미호출
- 적재 스크립트와 동일 모델·컬렉션으로 검색
- 프론트 변경 없음
