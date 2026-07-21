# Task 5b: 개인 장보기 도메인 포팅

## 상태

`feat/shopping-list`의 개인 `shopping_items` 도메인과 API를
`feat/core-loop-deepening`으로 포팅했다. 장보기 항목에는 아직 `group_id`를
추가하지 않았다.

## 포함 내용

- shopping 모델·스키마·리포지토리·서비스와 `/api/v1/shopping-items` 엔드포인트
- 서비스 의존성·API 라우터·사용자 관계·장보기 전용 NotFound 예외
- shopping_items Alembic 마이그레이션 및 장보기 단위/API 테스트
- 테스트 SQLite용 `ShoppingItem.id` Integer 타입 패치
- 마이그레이션 체인: `b2c3d4e5f6a7 -> c3d4e5f6a7b8 -> d4e5f6a7b8c9`

## 검증

- `uv run pytest tests/unit/test_shopping*.py tests/api/test_shopping_api.py -v`
  - 21 passed
- `uv run pytest tests/unit/test_group_*.py tests/unit/test_ingredient_service.py tests/api/test_ingredient_api.py -v`
  - 57 passed
- `uv run alembic heads`
  - 단일 head: `d4e5f6a7b8c9`

## 우려 사항

- 셸 전역 `pytest` 명령은 설치되어 있지 않아, 프로젝트의 `uv run pytest`로 검증했다.
