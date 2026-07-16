from datetime import date

import pytest
from httpx import AsyncClient

from core.exception.codes import ErrorCode


async def test_add_ingredients_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/ingredients",
        json={"ingredients": ["양파"]},
    )

    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_add_and_list_ingredients(client: AsyncClient, auth_headers: dict[str, str]):
    add_response = await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={
            "ingredients": ["양파", "당근"],
            "purchase_date": date.today().isoformat(),
        },
    )

    assert add_response.status_code == 201
    added = add_response.json()
    assert len(added) == 2
    assert added[0]["ingredient_name"] == "양파"
    assert added[1]["ingredient_name"] == "당근"

    list_response = await client.get("/api/v1/ingredients", headers=auth_headers)

    assert list_response.status_code == 200
    ingredients = list_response.json()
    assert len(ingredients) == 2
    assert {item["ingredient_name"] for item in ingredients} == {"양파", "당근"}


async def test_delete_ingredient(client: AsyncClient, auth_headers: dict[str, str]):
    add_response = await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={"ingredients": ["대파"]},
    )
    ingredient_id = add_response.json()[0]["id"]

    delete_response = await client.delete(
        f"/api/v1/ingredients/{ingredient_id}",
        headers=auth_headers,
    )

    assert delete_response.status_code == 204

    list_response = await client.get("/api/v1/ingredients", headers=auth_headers)
    assert list_response.json() == []


async def test_delete_ingredient_returns_not_found(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.delete(
        "/api/v1/ingredients/99999",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.INGREDIENT_NOT_FOUND


async def test_delete_all_ingredients_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/ingredients/all-delete")

    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_delete_all_ingredients_clears_all(
    client: AsyncClient, auth_headers: dict[str, str]
):
    await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={"ingredients": ["양파", "당근", "대파"]},
    )

    delete_response = await client.get(
        "/api/v1/ingredients/all-delete",
        headers=auth_headers,
    )

    assert delete_response.status_code == 204

    list_response = await client.get("/api/v1/ingredients", headers=auth_headers)
    assert list_response.json() == []


async def test_delete_all_ingredients_returns_not_found_when_empty(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.get(
        "/api/v1/ingredients/all-delete",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.INGREDIENT_NOT_FOUND
    assert response.json()["detail"] == (
        "삭제할 식재료가 존재하지 않거나 이미 비어있는 냉장고 입니다."
    )
