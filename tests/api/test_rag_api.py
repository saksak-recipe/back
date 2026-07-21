from datetime import date
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
        assert body["recipes"][0]["owned_ingredients"] == ["계란", "양파"]
        assert body["recipes"][0]["missing_ingredients"] == ["밥"]
        assert "parsed_ingredients" not in body["recipes"][0]
        assert body["recipes"][0]["score"] == 0.25
        mock_retriever.search.assert_called_once()
        called_query = mock_retriever.search.call_args.args[0]
        assert "계란" in called_query and "양파" in called_query
    finally:
        app.dependency_overrides.pop(get_rag_retriever, None)


async def test_recommendations_invalid_scope_422(
    client: AsyncClient, auth_headers: dict[str, str]
):
    app.dependency_overrides[get_rag_retriever] = lambda: MagicMock()
    try:
        response = await client.get(
            "/api/v1/recipes/recommendations",
            headers=auth_headers,
            params={"scope": "workspace"},
        )

        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_rag_retriever, None)


async def test_recommendations_group_without_membership_404(
    client: AsyncClient, auth_headers: dict[str, str]
):
    app.dependency_overrides[get_rag_retriever] = lambda: MagicMock()
    try:
        response = await client.get(
            "/api/v1/recipes/recommendations",
            headers=auth_headers,
            params={"scope": "group"},
        )

        assert response.status_code == 404
        assert response.json()["code"] == ErrorCode.GROUP_NOT_FOUND
    finally:
        app.dependency_overrides.pop(get_rag_retriever, None)


async def test_recommendations_group_scope_uses_group_fridge_only(
    client: AsyncClient, auth_headers: dict[str, str]
):
    await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={
            "ingredients": ["개인재료"],
            "purchase_date": date.today().isoformat(),
            "expiration_date": None,
        },
    )
    create = await client.post(
        "/api/v1/groups",
        headers=auth_headers,
        json={"name": "우리집"},
    )
    assert create.status_code == 201
    add = await client.post(
        "/api/v1/groups/me/ingredients",
        headers=auth_headers,
        json={
            "ingredients": ["그룹재료"],
            "purchase_date": date.today().isoformat(),
            "expiration_date": None,
        },
    )
    assert add.status_code == 201

    mock_retriever = MagicMock()
    mock_retriever.search.return_value = []
    app.dependency_overrides[get_rag_retriever] = lambda: mock_retriever
    try:
        response = await client.get(
            "/api/v1/recipes/recommendations",
            headers=auth_headers,
            params={"scope": "group"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ingredients_used"] == ["그룹재료"]
        called_query = mock_retriever.search.call_args.args[0]
        assert "그룹재료" in called_query
        assert "개인재료" not in called_query
    finally:
        app.dependency_overrides.pop(get_rag_retriever, None)


async def test_recommendations_group_scope_empty_ignores_personal(
    client: AsyncClient, auth_headers: dict[str, str]
):
    await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={
            "ingredients": ["개인재료"],
            "purchase_date": date.today().isoformat(),
            "expiration_date": None,
        },
    )
    create = await client.post(
        "/api/v1/groups",
        headers=auth_headers,
        json={"name": "우리집"},
    )
    assert create.status_code == 201

    mock_retriever = MagicMock()
    app.dependency_overrides[get_rag_retriever] = lambda: mock_retriever
    try:
        response = await client.get(
            "/api/v1/recipes/recommendations",
            headers=auth_headers,
            params={"scope": "group"},
        )
        assert response.status_code == 200
        assert response.json()["ingredients_used"] == []
        mock_retriever.search.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_rag_retriever, None)
