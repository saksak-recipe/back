from core import security
from domains.user.model import User


async def test_get_me(client, auth_headers, test_user):
    response = await client.get("/api/v1/users/me", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == test_user.email
    assert body["has_password"] is True
    assert body["has_kakao"] is False


async def test_patch_me_nickname(client, auth_headers):
    response = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers,
        json={"nickname": "newnick"},
    )

    assert response.status_code == 200
    assert response.json()["nickname"] == "newnick"


async def test_patch_me_rejects_email_field(client, auth_headers):
    response = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers,
        json={"email": "other@example.com", "nickname": "newnick2"},
    )

    assert response.status_code in (200, 422)
    me = await client.get("/api/v1/users/me", headers=auth_headers)
    assert me.status_code == 200
    assert me.json()["email"] == "test@example.com"


async def test_set_password_for_kakao_user_then_email_login(client, db_session):
    user = User(
        email="kakao@example.com",
        password=None,
        kakao_id="k1",
        nickname="kakao1",
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    headers = {"Authorization": f"Bearer {security.create_jwt(user.id)}"}

    response = await client.patch(
        "/api/v1/users/me/password",
        headers=headers,
        json={
            "new_password": "password123",
            "checked_password": "password123",
        },
    )

    assert response.status_code == 200
    assert response.json()["has_password"] is True
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "kakao@example.com", "password": "password123"},
    )
    assert login.status_code == 200


async def test_withdraw_blocks_me(client, auth_headers):
    response = await client.delete("/api/v1/users/me", headers=auth_headers)

    assert response.status_code == 204
    me = await client.get("/api/v1/users/me", headers=auth_headers)
    assert me.status_code == 401


async def test_login_restores_within_grace(client, auth_headers):
    await client.delete("/api/v1/users/me", headers=auth_headers)

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )

    assert login.status_code == 200
    assert login.json()["info"]["deleted_at"] is None


async def test_get_a_removed(client):
    response = await client.get("/a")

    assert response.status_code == 404
