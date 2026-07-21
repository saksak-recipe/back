from datetime import date, timedelta

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
    assert added[0]["expiration_date"] is None
    assert added[0]["status"] == "unknown"

    list_response = await client.get("/api/v1/ingredients", headers=auth_headers)

    assert list_response.status_code == 200
    ingredients = list_response.json()
    assert len(ingredients) == 2
    assert {item["ingredient_name"] for item in ingredients} == {"양파", "당근"}
    assert all(item["status"] == "unknown" for item in ingredients)


async def test_add_ingredients_with_expiration_date(
    client: AsyncClient, auth_headers: dict[str, str]
):
    purchase = date.today()
    expiration = purchase + timedelta(days=7)

    add_response = await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={
            "ingredients": ["우유"],
            "purchase_date": purchase.isoformat(),
            "expiration_date": expiration.isoformat(),
        },
    )

    assert add_response.status_code == 201
    body = add_response.json()
    assert body[0]["expiration_date"] == expiration.isoformat()
    assert body[0]["status"] == "ok"


async def test_list_ingredients_status_boundaries_and_sort(
    client: AsyncClient, auth_headers: dict[str, str]
):
    today = date.today()
    cases = [
        ("만료", today - timedelta(days=1)),
        ("오늘임박", today),
        ("D3임박", today + timedelta(days=3)),
        ("여유", today + timedelta(days=4)),
        ("미설정", None),
    ]
    for name, expiration in cases:
        payload: dict = {
            "ingredients": [name],
            "purchase_date": (today - timedelta(days=10)).isoformat(),
        }
        if expiration is not None:
            payload["expiration_date"] = expiration.isoformat()
        response = await client.post(
            "/api/v1/ingredients",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 201

    list_response = await client.get("/api/v1/ingredients", headers=auth_headers)
    assert list_response.status_code == 200
    items = list_response.json()
    assert [item["ingredient_name"] for item in items] == [
        "만료",
        "오늘임박",
        "D3임박",
        "여유",
        "미설정",
    ]
    assert [item["status"] for item in items] == [
        "expired",
        "soon",
        "soon",
        "ok",
        "unknown",
    ]


async def test_add_ingredients_rejects_expiration_before_purchase(
    client: AsyncClient, auth_headers: dict[str, str]
):
    purchase = date.today()
    expiration = purchase - timedelta(days=1)

    response = await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={
            "ingredients": ["우유"],
            "purchase_date": purchase.isoformat(),
            "expiration_date": expiration.isoformat(),
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == ErrorCode.BAD_REQUEST
    assert response.json()["detail"] == "유통기한은 구매일 이후여야 합니다."


async def test_update_ingredient(client: AsyncClient, auth_headers: dict[str, str]):
    add_response = await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={"ingredients": ["양파"]},
    )
    ingredient_id = add_response.json()[0]["id"]
    expiration = (date.today() + timedelta(days=3)).isoformat()

    patch_response = await client.patch(
        f"/api/v1/ingredients/{ingredient_id}",
        headers=auth_headers,
        json={
            "ingredient_name": "빨간양파",
            "expiration_date": expiration,
        },
    )

    assert patch_response.status_code == 200
    body = patch_response.json()
    assert body["ingredient_name"] == "빨간양파"
    assert body["expiration_date"] == expiration
    assert body["status"] == "soon"


async def test_update_ingredient_clears_expiration(
    client: AsyncClient, auth_headers: dict[str, str]
):
    purchase = date.today()
    expiration = purchase + timedelta(days=5)
    add_response = await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={
            "ingredients": ["두부"],
            "purchase_date": purchase.isoformat(),
            "expiration_date": expiration.isoformat(),
        },
    )
    ingredient_id = add_response.json()[0]["id"]

    patch_response = await client.patch(
        f"/api/v1/ingredients/{ingredient_id}",
        headers=auth_headers,
        json={"expiration_date": None},
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["expiration_date"] is None
    assert patch_response.json()["status"] == "unknown"


async def test_update_ingredient_empty_body_returns_bad_request(
    client: AsyncClient, auth_headers: dict[str, str]
):
    add_response = await client.post(
        "/api/v1/ingredients",
        headers=auth_headers,
        json={"ingredients": ["양파"]},
    )
    ingredient_id = add_response.json()[0]["id"]

    response = await client.patch(
        f"/api/v1/ingredients/{ingredient_id}",
        headers=auth_headers,
        json={},
    )

    assert response.status_code == 400
    assert response.json()["code"] == ErrorCode.BAD_REQUEST


async def test_update_ingredient_returns_not_found(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.patch(
        "/api/v1/ingredients/99999",
        headers=auth_headers,
        json={"ingredient_name": "없는재료"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.INGREDIENT_NOT_FOUND


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
    response = await client.delete("/api/v1/ingredients")

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

    delete_response = await client.delete(
        "/api/v1/ingredients",
        headers=auth_headers,
    )

    assert delete_response.status_code == 204

    list_response = await client.get("/api/v1/ingredients", headers=auth_headers)
    assert list_response.json() == []


async def test_delete_all_ingredients_returns_not_found_when_empty(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.delete(
        "/api/v1/ingredients",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.INGREDIENT_NOT_FOUND
    assert response.json()["detail"] == (
        "삭제할 식재료가 존재하지 않거나 이미 비어있는 냉장고 입니다."
    )
