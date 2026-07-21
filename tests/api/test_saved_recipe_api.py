from unittest.mock import AsyncMock

from httpx import AsyncClient

from api.deps import get_recipe_detail_service
from core.exception.codes import ErrorCode
from domains.recipe_detail.schemas import RecipeDetailResponse, RecipeIngredient, RecipeStep
from main import app


def _override_mangae_detail():
    mock = AsyncMock()
    mock.get_detail.return_value = RecipeDetailResponse(
        board_name="김치볶음밥",
        author_name="요리왕",
        recipe_name="김치볶음밥",
        source_url="https://example.com/1",
        main_image_url=None,
        ingredients=[RecipeIngredient(name="김치", amount="1컵")],
        steps=[RecipeStep(order=1, description="볶는다")],
        tips=["중불"],
    )
    return mock


async def test_saved_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/recipes/saved")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_save_list_detail_delete_mangae(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mangae_mock = _override_mangae_detail()
    app.dependency_overrides[get_recipe_detail_service] = lambda: mangae_mock
    try:
        save = await client.post(
            "/api/v1/recipes/saved",
            headers=auth_headers,
            json={"source": "mangae", "source_id": "김치볶음밥|요리왕"},
        )
        assert save.status_code == 201
        body = save.json()
        assert body["recipe_name"] == "김치볶음밥"
        assert body["source"] == "mangae"
        saved_id = body["id"]

        dup = await client.post(
            "/api/v1/recipes/saved",
            headers=auth_headers,
            json={"source": "mangae", "source_id": "김치볶음밥|요리왕"},
        )
        assert dup.status_code == 409
        assert dup.json()["code"] == ErrorCode.CONFLICT

        status = await client.get(
            "/api/v1/recipes/saved/status",
            headers=auth_headers,
            params={"source": "mangae", "source_id": "김치볶음밥|요리왕"},
        )
        assert status.status_code == 200
        assert status.json() == {"saved": True, "id": saved_id}

        listing = await client.get("/api/v1/recipes/saved", headers=auth_headers)
        assert listing.status_code == 200
        assert len(listing.json()) == 1
        assert "snapshot" not in listing.json()[0]

        detail = await client.get(
            f"/api/v1/recipes/saved/{saved_id}", headers=auth_headers
        )
        assert detail.status_code == 200
        assert detail.json()["snapshot"]["tips"] == ["중불"]

        deleted = await client.delete(
            f"/api/v1/recipes/saved/{saved_id}", headers=auth_headers
        )
        assert deleted.status_code == 204

        missing = await client.get(
            f"/api/v1/recipes/saved/{saved_id}", headers=auth_headers
        )
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.pop(get_recipe_detail_service, None)


async def test_save_mangae(client: AsyncClient, auth_headers: dict[str, str]):
    mangae_mock = _override_mangae_detail()
    app.dependency_overrides[get_recipe_detail_service] = lambda: mangae_mock
    try:
        save = await client.post(
            "/api/v1/recipes/saved",
            headers=auth_headers,
            json={"source": "mangae", "source_id": "김치볶음밥|요리왕"},
        )
        assert save.status_code == 201
        assert save.json()["source"] == "mangae"
        mangae_mock.get_detail.assert_awaited_once_with("김치볶음밥", "요리왕")
    finally:
        app.dependency_overrides.pop(get_recipe_detail_service, None)


async def test_save_rejects_ai_source(client: AsyncClient, auth_headers: dict[str, str]):
    response = await client.post(
        "/api/v1/recipes/saved",
        headers=auth_headers,
        json={"source": "ai", "source_id": "ai-1"},
    )
    assert response.status_code == 422


async def test_status_not_saved(client: AsyncClient, auth_headers: dict[str, str]):
    response = await client.get(
        "/api/v1/recipes/saved/status",
        headers=auth_headers,
        params={"source": "mangae", "source_id": "없음|작성자"},
    )
    assert response.status_code == 200
    assert response.json() == {"saved": False, "id": None}


async def test_status_rejects_ai_source(client: AsyncClient, auth_headers: dict[str, str]):
    response = await client.get(
        "/api/v1/recipes/saved/status",
        headers=auth_headers,
        params={"source": "ai", "source_id": "ai-1"},
    )
    assert response.status_code == 400
