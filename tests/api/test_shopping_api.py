from httpx import AsyncClient

from core.exception.codes import ErrorCode


async def test_add_shopping_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/shopping-items",
        json={"names": ["대파"]},
    )

    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_add_list_dedupe_and_patch(
    client: AsyncClient, auth_headers: dict[str, str]
):
    first = await client.post(
        "/api/v1/shopping-items",
        headers=auth_headers,
        json={"names": ["대파", "계란"]},
    )
    assert first.status_code == 201
    assert len(first.json()) == 2

    second = await client.post(
        "/api/v1/shopping-items",
        headers=auth_headers,
        json={"names": ["대파", "당근"]},
    )
    assert second.status_code == 201
    assert [item["name"] for item in second.json()] == ["당근"]

    listed = await client.get("/api/v1/shopping-items", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 3

    item_id = next(item["id"] for item in listed.json() if item["name"] == "대파")
    updated = await client.patch(
        f"/api/v1/shopping-items/{item_id}",
        headers=auth_headers,
        json={"is_checked": True},
    )
    assert updated.status_code == 200
    assert updated.json()["is_checked"] is True

    listed_again = await client.get("/api/v1/shopping-items", headers=auth_headers)
    checked = next(item for item in listed_again.json() if item["id"] == item_id)
    assert checked["is_checked"] is True


async def test_add_same_names_twice_returns_empty(
    client: AsyncClient, auth_headers: dict[str, str]
):
    first = await client.post(
        "/api/v1/shopping-items",
        headers=auth_headers,
        json={"names": ["대파"]},
    )
    assert first.status_code == 201
    assert len(first.json()) == 1

    second = await client.post(
        "/api/v1/shopping-items",
        headers=auth_headers,
        json={"names": ["대파"]},
    )
    assert second.status_code == 201
    assert second.json() == []


async def test_to_ingredient_moves_to_fridge(
    client: AsyncClient, auth_headers: dict[str, str]
):
    added = await client.post(
        "/api/v1/shopping-items",
        headers=auth_headers,
        json={"names": ["대파"]},
    )
    item_id = added.json()[0]["id"]

    moved = await client.post(
        f"/api/v1/shopping-items/{item_id}/to-ingredient",
        headers=auth_headers,
    )
    assert moved.status_code == 201
    assert moved.json()["ingredient_name"] == "대파"
    assert moved.json()["status"] == "unknown"

    shopping = await client.get("/api/v1/shopping-items", headers=auth_headers)
    assert shopping.json() == []

    ingredients = await client.get("/api/v1/ingredients", headers=auth_headers)
    assert any(item["ingredient_name"] == "대파" for item in ingredients.json())


async def test_delete_item_and_delete_all(
    client: AsyncClient, auth_headers: dict[str, str]
):
    added = await client.post(
        "/api/v1/shopping-items",
        headers=auth_headers,
        json={"names": ["대파", "계란"]},
    )
    item_id = added.json()[0]["id"]

    deleted = await client.delete(
        f"/api/v1/shopping-items/{item_id}",
        headers=auth_headers,
    )
    assert deleted.status_code == 204

    listed = await client.get("/api/v1/shopping-items", headers=auth_headers)
    assert len(listed.json()) == 1

    deleted_all = await client.delete(
        "/api/v1/shopping-items",
        headers=auth_headers,
    )
    assert deleted_all.status_code == 204

    listed_after = await client.get("/api/v1/shopping-items", headers=auth_headers)
    assert listed_after.json() == []

    empty_delete = await client.delete(
        "/api/v1/shopping-items",
        headers=auth_headers,
    )
    assert empty_delete.status_code == 404
    assert empty_delete.json()["code"] == ErrorCode.SHOPPING_ITEM_NOT_FOUND


async def test_update_nonexistent_item_not_found(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.patch(
        "/api/v1/shopping-items/999999",
        headers=auth_headers,
        json={"is_checked": True},
    )

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.SHOPPING_ITEM_NOT_FOUND
