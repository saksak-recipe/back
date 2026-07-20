from unittest.mock import MagicMock

from httpx import AsyncClient
from langchain_core.documents import Document

from api.deps import get_rag_retriever
from core.exception.codes import ErrorCode
from main import app


async def test_recommendations_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/recipes/recommendations")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_recommendations_empty_when_no_ingredients(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock_retriever = MagicMock()
    app.dependency_overrides[get_rag_retriever] = lambda: mock_retriever
    try:
        response = await client.get(
            "/api/v1/recipes/recommendations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ingredients_used"] == []
        assert body["recipes"] == []
        mock_retriever.search.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_rag_retriever, None)


async def test_recommendations_returns_mapped_recipes(
    client: AsyncClient, auth_headers: dict[str, str]
):
    await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={"ingredients": ["계란", "양파"]},
    )

    mock_retriever = MagicMock()
    mock_retriever.search.return_value = [
        (
            Document(
                page_content="recipe_name: 계란볶음밥\nparsed_ingredients: 계란, 양파, 밥",
                metadata={
                    "board_name": "한식",
                    "author_name": "kim",
                    "recipe_difficulty": "초급",
                    "time": "15분",
                },
            ),
            0.25,
        )
    ]
    app.dependency_overrides[get_rag_retriever] = lambda: mock_retriever
    try:
        response = await client.get(
            "/api/v1/recipes/recommendations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body["ingredients_used"]) == {"계란", "양파"}
        assert len(body["recipes"]) == 1
        assert body["recipes"][0]["recipe_name"] == "계란볶음밥"
        assert body["recipes"][0]["score"] == 0.25
        mock_retriever.search.assert_called_once()
        called_query = mock_retriever.search.call_args.args[0]
        assert "계란" in called_query and "양파" in called_query
    finally:
        app.dependency_overrides.pop(get_rag_retriever, None)
