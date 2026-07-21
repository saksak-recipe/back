from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from api.deps import get_ai_recipe_service
from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException, NotFoundException
from domains.ai_recipe.schemas import (
    AiRecipeDetailResponse,
    AiRecipeRecommendation,
    AiRecipeRecommendationResponse,
)
from domains.ingredient.scope import RecipeScope
from main import app


async def test_ai_recommendations_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/recipes/ai/recommendations")

    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_ai_recommendations_empty(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock = MagicMock()
    mock.recommend = AsyncMock(
        return_value=AiRecipeRecommendationResponse(
            ingredients_used=[],
            recipes=[],
        )
    )
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/recommendations",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["recipes"] == []
        mock.recommend.assert_awaited_once_with(
            refresh=False, scope=RecipeScope.personal
        )
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)


async def test_ai_recommendations_success(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock = MagicMock()
    mock.recommend = AsyncMock(
        return_value=AiRecipeRecommendationResponse(
            ingredients_used=["계란"],
            recipes=[
                AiRecipeRecommendation(
                    recipe_id="rid",
                    recipe_name="계란볶음밥",
                    owned_ingredients=["계란"],
                    missing_ingredients=["밥"],
                    recipe_difficulty="초급",
                    time="10분",
                )
            ],
        )
    )
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/recommendations",
            headers=auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["recipes"][0]["source"] == "ai"
        assert body["recipes"][0]["recipe_id"] == "rid"
        mock.recommend.assert_awaited_once_with(
            refresh=False, scope=RecipeScope.personal
        )
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)


async def test_ai_recommendations_passes_refresh(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock = MagicMock()
    mock.recommend = AsyncMock(
        return_value=AiRecipeRecommendationResponse(
            ingredients_used=[],
            recipes=[],
        )
    )
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/recommendations",
            headers=auth_headers,
            params={"refresh": "true"},
        )

        assert response.status_code == 200
        mock.recommend.assert_awaited_once_with(
            refresh=True, scope=RecipeScope.personal
        )
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)


async def test_ai_recommendations_passes_group_scope(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock = MagicMock()
    mock.recommend = AsyncMock(
        return_value=AiRecipeRecommendationResponse(ingredients_used=[], recipes=[])
    )
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/recommendations",
            headers=auth_headers,
            params={"scope": "group", "refresh": "true"},
        )
        assert response.status_code == 200
        mock.recommend.assert_awaited_once_with(
            refresh=True, scope=RecipeScope.group
        )
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)


async def test_ai_detail_404(client: AsyncClient, auth_headers: dict[str, str]):
    mock = MagicMock()
    mock.get_detail = AsyncMock(
        side_effect=NotFoundException(detail="AI 레시피를 찾지 못했습니다.")
    )
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/detail",
            headers=auth_headers,
            params={"recipe_id": "missing"},
        )

        assert response.status_code == 404
        assert response.json()["code"] == ErrorCode.NOT_FOUND
        mock.get_detail.assert_awaited_once_with(
            "missing", scope=RecipeScope.personal
        )
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)


async def test_ai_detail_502(client: AsyncClient, auth_headers: dict[str, str]):
    mock = MagicMock()
    mock.get_detail = AsyncMock(side_effect=ExternalServiceException())
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/detail",
            headers=auth_headers,
            params={"recipe_id": "rid"},
        )

        assert response.status_code == 502
        mock.get_detail.assert_awaited_once_with("rid", scope=RecipeScope.personal)
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)


async def test_ai_detail_success(client: AsyncClient, auth_headers: dict[str, str]):
    mock = MagicMock()
    mock.get_detail = AsyncMock(
        return_value=AiRecipeDetailResponse(
            recipe_id="rid",
            recipe_name="계란볶음밥",
            ingredients=[],
            steps=[],
            tips=[],
            owned_ingredients=["계란"],
            missing_ingredients=[],
            cached=True,
        )
    )
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/detail",
            headers=auth_headers,
            params={"recipe_id": "rid"},
        )

        assert response.status_code == 200
        assert response.json()["cached"] is True
        assert response.json()["source"] == "ai"
        mock.get_detail.assert_awaited_once_with("rid", scope=RecipeScope.personal)
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)


async def test_ai_detail_passes_group_scope(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock = MagicMock()
    mock.get_detail = AsyncMock(
        return_value=AiRecipeDetailResponse(
            recipe_id="rid",
            recipe_name="계란볶음밥",
            ingredients=[],
            steps=[],
            tips=[],
            owned_ingredients=["계란"],
            missing_ingredients=[],
            cached=True,
        )
    )
    app.dependency_overrides[get_ai_recipe_service] = lambda: mock
    try:
        response = await client.get(
            "/api/v1/recipes/ai/detail",
            headers=auth_headers,
            params={"recipe_id": "rid", "scope": "group"},
        )
        assert response.status_code == 200
        mock.get_detail.assert_awaited_once_with("rid", scope=RecipeScope.group)
    finally:
        app.dependency_overrides.pop(get_ai_recipe_service, None)
