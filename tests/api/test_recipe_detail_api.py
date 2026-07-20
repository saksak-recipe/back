from unittest.mock import AsyncMock

from httpx import AsyncClient

from api.deps import get_recipe_detail_service
from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException, NotFoundException
from domains.recipe_detail.schemas import RecipeDetailResponse
from main import app


async def test_detail_requires_auth(client: AsyncClient):
    response = await client.get(
        "/api/v1/recipes/detail",
        params={"board_name": "a", "author_name": "b"},
    )
    assert response.status_code == 401


async def test_detail_success(client: AsyncClient, auth_headers: dict[str, str]):
    mock = AsyncMock()
    mock.get_detail.return_value = RecipeDetailResponse(
        board_name="제목",
        author_name="작성자",
        recipe_name="요리",
        source_url="https://www.10000recipe.com/recipe/1",
        cached=False,
    )
    app.dependency_overrides[get_recipe_detail_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/detail",
            headers=auth_headers,
            params={"board_name": "제목", "author_name": "작성자"},
        )
        assert response.status_code == 200
        assert response.json()["recipe_name"] == "요리"
        mock.get_detail.assert_awaited_once_with("제목", "작성자")
    finally:
        app.dependency_overrides.pop(get_recipe_detail_service, None)


async def test_detail_not_found(client: AsyncClient, auth_headers: dict[str, str]):
    mock = AsyncMock()
    mock.get_detail.side_effect = NotFoundException(
        detail="해당 레시피를 찾지 못했어요"
    )
    app.dependency_overrides[get_recipe_detail_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/detail",
            headers=auth_headers,
            params={"board_name": "x", "author_name": "y"},
        )
        assert response.status_code == 404
        assert response.json()["code"] == ErrorCode.NOT_FOUND
    finally:
        app.dependency_overrides.pop(get_recipe_detail_service, None)


async def test_detail_bad_gateway(client: AsyncClient, auth_headers: dict[str, str]):
    mock = AsyncMock()
    mock.get_detail.side_effect = ExternalServiceException()
    app.dependency_overrides[get_recipe_detail_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/detail",
            headers=auth_headers,
            params={"board_name": "x", "author_name": "y"},
        )
        assert response.status_code == 502
    finally:
        app.dependency_overrides.pop(get_recipe_detail_service, None)
