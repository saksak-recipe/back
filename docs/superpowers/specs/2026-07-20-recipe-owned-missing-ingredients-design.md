# 추천 레시피 owned / missing 재료 분리

날짜: 2026-07-20  
상태: Approved (대화에서 설계 승인)

## Goal

추천 API 응답에서 `parsed_ingredients` 문자열 대신, 사용자 보유 식재료와 레시피 필요 재료를 비교해  
`owned_ingredients` / `missing_ingredients`로 나눠 반환하고, 앱 목록 카드에 표시한다.

## Decisions

| 항목 | 선택 |
|------|------|
| 범위 | 백엔드 + 앱 |
| `parsed_ingredients` | 제거 |
| 새 필드 | `owned_ingredients: string[]`, `missing_ingredients: string[]` |
| 매칭 | 정규화 후 완전 일치만 |
| 상세 API | 변경 없음 (Out of Scope) |

## Out of Scope

- 부분 문자열 매칭 / 동의어 사전
- 레시피 상세 API 재료 분리
- `ingredients_used`(응답 최상위 냉장고 목록) 제거

## API

`GET /api/v1/recipes/recommendations`의 각 recipe:

```json
{
  "recipe_name": "충무김밥",
  "owned_ingredients": ["김", "밥", "참기름"],
  "missing_ingredients": ["어묵", "대파", "다진마늘"],
  "board_name": "충무김밥 집에서 만들어보기",
  "author_name": "예쁜나무숲",
  "recipe_difficulty": "초급",
  "time": "60분이내",
  "score": 0.1127
}
```

응답 최상위 `ingredients_used: string[]`는 유지한다.

## Matching

1. 벡터 문서의 `parsed_ingredients`를 `,` 기준으로 split 후 trim
2. `normalize_name`: strip + casefold + 공백 제거 (기존 mapper 함수)
3. 보유 식재료 이름을 같은 방식으로 정규화한 set과 비교
4. 일치 → `owned_ingredients`, 불일치 → `missing_ingredients`
5. 레시피 쪽 원문 표기 유지, 중복은 첫 등장만 (순서 유지)

분류는 `map_document_to_recipe` 호출부(또는 mapper)에서 사용자 식재료 목록을 받아 수행한다.

## App

- `RecipeRecommendation` 타입: `parsed_ingredients` 제거, owned/missing 추가
- `RecipeCard`: 보유 / 필요 재료를 짧게 구분 표시

## Testing

- mapper: owned/missing 분류, 중복 제거, 미매칭 전부
- 서비스/API: 새 필드 존재, `parsed_ingredients` 부재
- 앱: 타입 맞춤 (카드 렌더)

## Success criteria

1. 추천 응답에 `parsed_ingredients`가 없다
2. 보유 식재료와 이름이 정규화 일치하면 owned에만 들어간다
3. 앱 목록에서 보유/필요 재료를 구분해 볼 수 있다
