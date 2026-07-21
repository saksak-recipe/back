# 장보기 리스트 (Shopping List)

날짜: 2026-07-21  
상태: Approved (대화에서 섹션별 승인 완료)

## Goal

레시피 추천/상세의 `missing_ingredients`를 유저당 **하나의 장보기 리스트**에 모아 두고,  
체크한 뒤 선택적으로 냉장고(`ingredients`)에 옮길 수 있게 한다.

이번 범위는 **백엔드 API + DB만** 포함한다.

## Decisions

| 항목 | 선택 |
|------|------|
| 핵심 용도 | 레시피 부족 재료 → 장보기 (요리 계획 기반) |
| 리스트 구조 | 유저당 **암묵적 리스트 하나** (`shopping_items`만) |
| 항목 추가 | 클라이언트가 `missing_ingredients` 이름 배열을 `POST`로 전달 |
| 중복 | `(user_id, name)` UNIQUE — 같은 이름은 **하나로 합침** (skip) |
| 출처 레시피 | 저장하지 않음 |
| 수량·단위 | MVP는 **이름만** |
| 완료 후 | `is_checked` 체크 → 선택적으로 `to-ingredient`로 냉장고 추가 |
| 아키텍처 | 단일 `shopping_items` 테이블 + `domains/shopping/` |

## Out of Scope

- 프론트엔드 UI
- 수량·단위
- 레시피 출처 추적 / 레시피별 리스트
- 다중 장보기 리스트
- 서버가 냉장고와 비교해 missing을 자동 계산해 넣는 동작
- 수동 자유 입력 전용 UX (API상 `names`로 동일 엔드포인트 사용 가능하나, 제품 포커스는 missing 추가)

## Problem

RAG/AI 레시피는 `missing_ingredients`를 응답하지만, 이를 모아 두고 장을 볼 영속 저장소가 없다.  
냉장고(`ingredients`)와 섞으면 유통기한·보유 재료 도메인이 오염된다.

## Architecture

```
[클라이언트 — 추천/상세]
  POST /api/v1/shopping-items  { "names": ["대파", "계란"] }
       ↓
[ShoppingService]
  1. 이름 trim / 빈값·길이 검증
  2. 유저 기존 항목과 비교 → 신규만 insert
  3. 201 + 새로 생성된 항목 목록

[조회]
  GET /api/v1/shopping-items
      → is_checked=false 우선, 그다음 created_at

[체크]
  PATCH /api/v1/shopping-items/{id}  { "is_checked": true }

[냉장고로 이동]
  POST /api/v1/shopping-items/{id}/to-ingredient
       ↓
  1. 소유권 확인 (`is_checked` 여부와 무관 — 이동은 명시적 액션)
  2. IngredientRepository로 ingredient 생성
     (purchase_date=today, expiration_date=null)
  3. shopping item 삭제
  4. 생성된 ingredient를 AddIngredientResponse로 반환
  (체크는 UX용 상태이며, to-ingredient의 전제 조건이 아니다)

[삭제]
  DELETE /api/v1/shopping-items/{id}
  DELETE /api/v1/shopping-items          # 전체 삭제
```

### Domain layout

기존 `ingredient` 패턴을 따른다.

```
src/domains/shopping/
  model.py
  repository.py
  service.py
  schemas.py

src/api/v1/endpoints/shopping.py
src/api/deps.py          # get_shopping_service
src/api/api.py           # include router
alembic/versions/..._add_shopping_items.py
```

### Data model — `shopping_items`

| 컬럼 | 타입 | 제약 |
|------|------|------|
| `id` | BigInt | PK, autoincrement |
| `user_id` | UUID | FK → `users.id` ON DELETE CASCADE, index |
| `name` | String(45) | NOT NULL |
| `is_checked` | Boolean | NOT NULL, default false |
| `created_at` | DateTime(tz) | server_default now() |

UNIQUE `(user_id, name)`.

이름 길이는 `ingredients.ingredient_name`과 동일하게 45자로 맞춘다.

## API

베이스: `/api/v1/shopping-items` (JWT 필수)

| Method | Path | Status | 설명 |
|--------|------|--------|------|
| GET | `/shopping-items` | 200 | 내 항목 목록 |
| POST | `/shopping-items` | 201 | `names: list[str]` 추가 (중복 skip, 신규만 반환) |
| PATCH | `/shopping-items/{id}` | 200 | `is_checked` 갱신 |
| POST | `/shopping-items/{id}/to-ingredient` | 201 | 냉장고 추가 후 리스트에서 제거 |
| DELETE | `/shopping-items/{id}` | 204 | 단건 삭제 |
| DELETE | `/shopping-items` | 204 | 전체 삭제 |

### Request / Response (요약)

**AddShoppingItemsRequest**
```json
{ "names": ["대파", "계란", "간장"] }
```

- 각 이름: strip 후 비어 있으면 400, 45자 초과면 400
- `names`가 비어 있으면 400
- 요청 내 중복 이름은 한 번만 처리

**ShoppingItemResponse**
```json
{ "id": 1, "name": "대파", "is_checked": false, "created_at": "..." }
```

**UpdateShoppingItemRequest**
```json
{ "is_checked": true }
```

**to-ingredient 응답:** 기존 `AddIngredientResponse` 단건.

## Error handling

| 상황 | 결과 |
|------|------|
| 미인증 | 401 UnAuthorized |
| 빈/잘못된 이름, 빈 names | 400 BadRequest |
| 없는 id / 타 유저 항목 | 404 `ShoppingItemNotFoundException` (`SHOPPING_ITEM_NOT_FOUND`) |
| DB 오류 | DatabaseException (기존 래핑) |

중복 이름은 에러가 아니다. skip 후 신규만 201로 반환한다.  
요청의 모든 이름이 이미 있으면 **201 + 빈 배열**을 반환한다.

## Testing

- `tests/unit/test_shopping_service.py`
  - 신규 추가 / 중복 skip / 요청 내 중복 정규화
  - 체크 PATCH
  - to-ingredient → ingredient 생성 + shopping 삭제
  - 타 유저/없는 id → 404
- `tests/api/test_shopping_api.py`
  - 인증 필요
  - CRUD 라운드트립
  - 중복 POST
  - to-ingredient 후 `GET /ingredients`에 존재, shopping 목록에서 사라짐

## Implementation order

1. Alembic: `shopping_items` + UNIQUE
2. `domains/shopping/` model · schemas · repository · service
3. Exception/ErrorCode + endpoint + deps + router
4. Unit / API tests
5. `ShoppingService`가 `to-ingredient` 시 `IngredientRepository`(또는 동일 session의 ingredient insert)를 직접 호출해 냉장고 항목을 만든다. 순환 DI를 피하기 위해 `IngredientService` 전체 DI는 쓰지 않는다.

## Future (명시적으로 미구현)

- 다중 리스트 (`shopping_lists` 테이블)
- 수량·단위 컬럼
- 출처 레시피 ID 배열
- missing 자동 동기화
