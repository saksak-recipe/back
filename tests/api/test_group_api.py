from datetime import date

from httpx import AsyncClient

from core.exception.codes import ErrorCode


async def _signup(
    client: AsyncClient, *, email: str, nickname: str, password: str = "password123"
) -> dict[str, str]:
    response = await client.post(
        "/api/v1/users/signup",
        json={
            "email": email,
            "password": password,
            "checked_password": password,
            "nickname": nickname,
        },
    )
    assert response.status_code == 201, response.text
    verified = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": email, "code": "123456"},
    )
    assert verified.status_code == 200, verified.text
    token = verified.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_group_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/groups", json={"name": "우리집"})
    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_create_invite_accept_ingredient_merge_and_leave(
    client: AsyncClient,
    fixed_email_code,
):
    owner_headers = await _signup(
        client, email="owner@example.com", nickname="owneruser"
    )
    member_headers = await _signup(
        client, email="member@example.com", nickname="memberuser"
    )

    created = await client.post(
        "/api/v1/groups",
        headers=owner_headers,
        json={"name": "우리집"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "우리집"
    assert len(body["invite_code"]) == 8
    assert any(m["role"] == "owner" for m in body["members"])

    invite = await client.post(
        "/api/v1/groups/me/invites",
        headers=owner_headers,
        json={"nickname": "memberuser"},
    )
    assert invite.status_code == 201
    invite_id = invite.json()["id"]

    pending = await client.get("/api/v1/groups/invites", headers=member_headers)
    assert pending.status_code == 200
    assert len(pending.json()) == 1

    accepted = await client.post(
        f"/api/v1/groups/invites/{invite_id}/accept",
        headers=member_headers,
    )
    assert accepted.status_code == 200
    assert len(accepted.json()["members"]) == 2

    personal = await client.post(
        "/api/v1/ingredients",
        headers=member_headers,
        json={
            "ingredients": ["양파"],
            "purchase_date": date.today().isoformat(),
            "expiration_date": None,
        },
    )
    assert personal.status_code == 201
    personal_id = personal.json()[0]["id"]

    merged = await client.post(
        "/api/v1/groups/me/merge",
        headers=member_headers,
        json={"mode": "copy", "ingredients": [personal_id], "shopping_items": []},
    )
    assert merged.status_code == 200
    assert len(merged.json()["created_ingredients"]) == 1
    assert merged.json()["deleted_ingredient_ids"] == []

    group_ings = await client.get(
        "/api/v1/groups/me/ingredients", headers=member_headers
    )
    assert group_ings.status_code == 200
    assert any(i["ingredient_name"] == "양파" for i in group_ings.json())

    added = await client.post(
        "/api/v1/groups/me/ingredients",
        headers=owner_headers,
        json={
            "ingredients": ["대파"],
            "purchase_date": date.today().isoformat(),
            "expiration_date": None,
        },
    )
    assert added.status_code == 201
    assert added.json()[0]["ingredient_name"] == "대파"

    left = await client.post("/api/v1/groups/me/leave", headers=member_headers)
    assert left.status_code == 204

    dissolved = await client.delete("/api/v1/groups/me", headers=owner_headers)
    assert dissolved.status_code == 204

    missing = await client.get("/api/v1/groups/me", headers=owner_headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == ErrorCode.GROUP_NOT_FOUND


async def test_join_by_code(client: AsyncClient, fixed_email_code):
    owner_headers = await _signup(
        client, email="codeowner@example.com", nickname="codeowner"
    )
    joiner_headers = await _signup(
        client, email="codejoiner@example.com", nickname="codejoiner"
    )

    created = await client.post(
        "/api/v1/groups",
        headers=owner_headers,
        json={"name": "코드집"},
    )
    invite_code = created.json()["invite_code"]

    joined = await client.post(
        "/api/v1/groups/join",
        headers=joiner_headers,
        json={"invite_code": invite_code},
    )
    assert joined.status_code == 200
    assert len(joined.json()["members"]) == 2
