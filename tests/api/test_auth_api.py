from httpx import AsyncClient

from core.exception.codes import ErrorCode


async def _signup(
    client: AsyncClient,
    *,
    email: str,
    nickname: str,
    password: str = "password123",
) -> None:
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


async def _verify(
    client: AsyncClient, *, email: str, code: str = "123456"
) -> dict:
    response = await client.post(
        "/api/v1/auth/email/verify",
        json={"email": email, "code": code},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_signup_sends_code_without_tokens(
    client: AsyncClient, fixed_email_code
):
    response = await client.post(
        "/api/v1/users/signup",
        json={
            "email": "signup@example.com",
            "password": "password123",
            "checked_password": "password123",
            "nickname": "signupuser",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "signup@example.com"
    assert body["message"] == "verification_code_sent"
    assert "access_token" not in body
    assert "refresh_token" not in body


async def test_signup_returns_conflict_for_duplicate_email(
    client: AsyncClient, fixed_email_code
):
    payload = {
        "email": "duplicate@example.com",
        "password": "password123",
        "checked_password": "password123",
        "nickname": "userone",
    }
    await client.post("/api/v1/users/signup", json=payload)

    response = await client.post(
        "/api/v1/users/signup",
        json={
            **payload,
            "nickname": "usertwo",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == ErrorCode.EMAIL_CONFLICT


async def test_login_rejects_unverified(client: AsyncClient, fixed_email_code):
    await _signup(
        client, email="unverified@example.com", nickname="unverifieduser"
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "unverified@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.EMAIL_NOT_VERIFIED


async def test_verify_then_login(client: AsyncClient, fixed_email_code):
    await _signup(client, email="verify@example.com", nickname="verifyuser")

    verified = await _verify(client, email="verify@example.com")
    assert verified["access_token"]
    assert verified["refresh_token"]
    assert verified["info"]["email"] == "verify@example.com"

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "verify@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["info"]["email"] == "verify@example.com"
    assert body["access_token"]
    assert body["refresh_token"]


async def test_login_returns_unauthorized_for_wrong_password(
    client: AsyncClient, fixed_email_code
):
    await _signup(client, email="wrongpass@example.com", nickname="wrongpassuser")
    await _verify(client, email="wrongpass@example.com")

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrongpass@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_refresh_rotates_and_rejects_reuse(
    client: AsyncClient, fixed_email_code
):
    await _signup(client, email="refresh@example.com", nickname="refreshuser")
    verified = await _verify(client, email="refresh@example.com")
    old_refresh = verified["refresh_token"]

    first = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert first.status_code == 200
    new_refresh = first.json()["refresh_token"]
    assert new_refresh != old_refresh

    reuse = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert reuse.status_code == 401
    assert reuse.json()["code"] == ErrorCode.INVALID_TOKEN


async def test_logout_invalidates_refresh(client: AsyncClient, fixed_email_code):
    await _signup(client, email="logout@example.com", nickname="logoutuser")
    verified = await _verify(client, email="logout@example.com")
    refresh = verified["refresh_token"]

    logout = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": refresh}
    )
    assert logout.status_code == 200

    again = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh}
    )
    assert again.status_code == 401


async def test_password_reset_e2e(client: AsyncClient, fixed_email_code):
    email = "reset@example.com"
    await _signup(client, email=email, nickname="resetuser", password="password123")
    await _verify(client, email=email)

    request = await client.post(
        "/api/v1/auth/password/reset/request",
        json={"email": email},
    )
    assert request.status_code == 200
    assert request.json() == {"ok": True, "message": "password_reset_email_sent"}

    confirm = await client.post(
        "/api/v1/auth/password/reset/confirm",
        json={
            "email": email,
            "code": "123456",
            "password": "newpass123",
            "checked_password": "newpass123",
        },
    )
    assert confirm.status_code == 200
    assert confirm.json() == {"ok": True}

    old_login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "newpass123"},
    )
    assert new_login.status_code == 200
    assert new_login.json()["access_token"]


async def test_password_reset_request_hides_missing_email(
    client: AsyncClient, fixed_email_code
):
    response = await client.post(
        "/api/v1/auth/password/reset/request",
        json={"email": "missing@example.com"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "password_reset_email_sent"}
