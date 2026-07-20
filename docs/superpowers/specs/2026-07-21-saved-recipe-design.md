# 저장된 레시피 (Saved Recipe) 서비스

날짜: 2026-07-21  
상태: Approved (대화에서 섹션별 승인 완료)

## Goal

추천받은 레시피(AI + 만개)를 Postgres에 **스냅샷으로 영속 저장**하고,  
JWT 사용자가 목록·상세로 다시 꺼내보며, 중복 저장을 막고 저장 여부를 조회할 수 있게 한다.

이번 범위는 **백엔드 API + DB만** 포함한다.

## Decisions

| 항목 | 선택 |
|------|------|
| 범위 | 백엔드만 (앱 UI는 후속) |
| 저장 대상 | AI + 만개(RAG/크롤 상세) |
| 영속 방식 | 저장 시점 **스냅샷** (원본 Redis/외부 소멸과 무관) |
| 아키텍처 | 단일 `saved_recipes` 테이블 + `domains/saved_recipe/` 도메인 |
| MVP API | 저장 / 목록 / 상세 / 삭제 + 중복 방지 + 저장 여부 조회 |
| 중복 키 | `(user_id, source, source_id)` UNIQUE |
| 스냅샷 채움 | 서버가 원본 상세 서비스 조회 후 저장 (클라이언트 JSON 직접 제출 없음) |

## Out of Scope

- 프론트엔드 UI (저장 버튼, 저장 목록 화면)
- 메모·태그·폴더·공유
- 저장본 재생성/원본 동기화 (스냅샷은 immutable)
- 만개 추천 응답에 `recipe_id` 필드 추가
- 이미지 업로드·별도 미디어 스토리지
- 페이지네이션 고도화 (MVP는 단순 최신순 전체/또는 합리적 limit)

## Problem

AI 레시피는 Redis TTL 24시간만 존재하고, 만개 상세도 캐시/크롤에 의존한다.  
“추천받은 레시피를 나중에 다시 보고 싶다”는 요구를 현재 스택으로는 충족할 수 없다.  
저장/북마크 도메인도 없다.

## Architecture

```
[클라이언트]
  POST /api/v1/recipes/saved  { source, source_id }
       ↓
[SavedRecipeService]
  1. source/source_id 검증
  2. 기존 저장 여부 → 있으면 409 Conflict
  3. 원본 상세 조회
       - ai     → AiRecipeService.get_detail(recipe_id)
       - mangae → RecipeDetailService.get_detail(board_name, author_name)
  4. 메타 + snapshot JSONB insert
  5. 201 + SavedRecipeResponse

[조회]
  GET  /recipes/saved           → 목록 (스냅샷 제외)
  GET  /recipes/saved/{id}      → 상세 (스냅샷 포함, user_id 스코프)
  DELETE /recipes/saved/{id}    → 삭제
  GET  /recipes/saved/status    → { saved, id }
```

### Domain layout

기존 ingredient 패턴을 따른다.

```
src/domains/saved_recipe/
  model.py
  repository.py
  service.py
  schemas.py

src/api/v1/endpoints/saved_recipe.py
src/api/deps.py          # get_saved_recipe_service
src/api/api.py           # include router
alembic/versions/..._add_saved_recipes.py
```

### Data model — `saved_recipes`

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | UUID PK | 저장본 ID |
| `user_id` | UUID FK → users ON DELETE CASCADE | 소유자 |
| `source` | String | `"ai"` \| `"mangae"` |
| `source_id` | String | 중복 키. AI=`recipe_id`, 만개=`{board_name}\|{author_name}` |
| `recipe_name` | String | 목록용 |
| `recipe_difficulty` | String nullable | 목록용 |
| `time` | String nullable | 목록용 |
| `snapshot` | JSONB | 상세 전체 스냅샷 |
| `created_at` | timestamptz | 저장 시각 |

**제약/인덱스**

- UNIQUE `(user_id, source, source_id)`
- INDEX `(user_id, created_at DESC)`

### Snapshot shape

공통:

```json
{
  "ingredients": [{ "name": "...", "amount": "..." }],
  "steps": [{ "order": 1, "description": "..." }],
  "tips": ["..."]
}
```

소스별 부가 필드 (같은 JSON 안에 포함):

- **ai:** `owned_ingredients`, `missing_ingredients` (저장 시점 값; 이후 냉장고 변경과 재동기화하지 않음)
- **mangae:** `board_name`, `author_name`, `source_url`, `main_image_url`

목록용 메타(`recipe_name`, `recipe_difficulty`, `time`)는 컬럼에도 두고, 필요 시 snapshot에도 중복 저장해도 된다.  
응답 시에는 컬럼 메타 + snapshot을 조합해 반환한다.

### `source_id` 규칙

| source | source_id | 파싱 |
|--------|-----------|------|
| `ai` | AI `recipe_id` (UUID 문자열) | 그대로 사용 |
| `mangae` | `{board_name}\|{author_name}` | 첫 `|` 기준으로 board / author 분리. board·author 모두 non-empty |

잘못된 `source` 또는 만개 형식 불일치 → validation 에러 (400).

## API

Base: `/api/v1/recipes/saved`  
Auth: JWT 필수 (`get_current_user`)

### `POST /recipes/saved`

Request:

```json
{ "source": "ai", "source_id": "<recipe_id>" }
```

또는

```json
{ "source": "mangae", "source_id": "보드이름|작성자" }
```

Response `201`: 저장된 엔티티 (상세와 동일 스키마 — id, source, source_id, 메타, snapshot, created_at)

Errors: 401, 400(형식), 404(원본 없음), 409(이미 저장)

### `GET /recipes/saved`

Response `200`: 배열, 최신순. 각 항목은 목록용 필드만  
(`id`, `source`, `source_id`, `recipe_name`, `recipe_difficulty`, `time`, `created_at`)

### `GET /recipes/saved/{id}`

Response `200`: 목록 필드 + `snapshot`  
타인/없는 id → 404

### `DELETE /recipes/saved/{id}`

Response `204`  
타인/없는 id → 404

### `GET /recipes/saved/status`

Query: `source`, `source_id`

Response `200`:

```json
{ "saved": true, "id": "<uuid>" }
```

또는

```json
{ "saved": false, "id": null }
```

## Error handling

기존 `core.exception` 사용:

| 상황 | 예외 |
|------|------|
| JWT 없음/만료 | `UnAuthorizedException` |
| source/source_id 형식 오류 | validation / `BadRequest`(프로젝트 기존 패턴) |
| 원본 레시피 없음 (AI Redis miss, 만개 검색 실패) | `NotFoundException` |
| 이미 저장됨 | `ConflictException` |
| 내 저장본 없음 | `NotFoundException` (존재 여부 노출 최소화) |

원본 조회 중 외부 장애는 기존 상세 서비스와 동일하게 `ExternalServiceException` 등으로 전파.

## Testing

- **unit repository:** UNIQUE 제약, user_id 스코프 조회/삭제
- **unit service:** 저장 성공, 중복 409, AI/만개 source_id 파싱, 원본 404 전파, 타 유저 상세/삭제 404
- 원본 서비스(`AiRecipeService`, `RecipeDetailService`)는 mock
- **endpoint 스모크:** 201 / 409 / 404 / status 응답 형태

## Dependencies

- `AiRecipeService.get_detail` — AI 스냅샷 소스
- `RecipeDetailService.get_detail` — 만개 스냅샷 소스
- 기존 User / JWT / SQLAlchemy async / Alembic

AI 상세가 아직 확장되지 않은 캐시(목록만 있고 ingredients/steps 없음)인 경우,  
기존 `get_detail`이 상세를 생성한 뒤 반환하는 동작을 그대로 활용한다.  
저장은 **상세가 완성된 응답**을 스냅샷한다.

## Success criteria

1. 인증된 사용자가 AI·만개 레시피를 각각 저장할 수 있다.
2. Redis TTL 만료 후에도 저장본 상세 조회가 가능하다.
3. 동일 `(source, source_id)` 재저장은 409이다.
4. `status` API로 저장 여부·저장본 id를 알 수 있다.
5. 사용자는 본인 저장본만 목록/상세/삭제할 수 있다.
