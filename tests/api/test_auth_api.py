import pytest
from httpx import AsyncClient

from core.exception.codes import ErrorCode


async def test_signup_returns_user_and_token(client: AsyncClient):
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
    assert body["info"]["email"] == "signup@example.com"
    assert body["info"]["nickname"] == "signupuser"
    assert body["access_token"]
    assert body["refresh_token"]


async def test_signup_returns_conflict_for_duplicate_email(client: AsyncClient):
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


async def test_login_returns_token(client: AsyncClient):
    await client.post(
        "/api/v1/users/signup",
        json={
            "email": "login@example.com",
            "password": "password123",
            "checked_password": "password123",
            "nickname": "loginuser",
        },
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "login@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["info"]["email"] == "login@example.com"
    assert body["access_token"]
    assert body["refresh_token"]


async def test_login_returns_unauthorized_for_wrong_password(client: AsyncClient):
    await client.post(
        "/api/v1/users/signup",
        json={
            "email": "wrongpass@example.com",
            "password": "password123",
            "checked_password": "password123",
            "nickname": "wrongpassuser",
        },
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrongpass@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_login_returns_refresh_token(client: AsyncClient):
    await client.post(
        "/api/v1/users/signup",
        json={
            "email": "login@example.com",
            "password": "password123",
            "checked_password": "password123",
            "nickname": "loginuser",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]


async def test_refresh_rotates_and_rejects_reuse(client: AsyncClient):
    signup = await client.post(
        "/api/v1/users/signup",
        json={
            "email": "refresh@example.com",
            "password": "password123",
            "checked_password": "password123",
            "nickname": "refreshuser",
        },
    )
    old_refresh = signup.json()["refresh_token"]

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


async def test_logout_invalidates_refresh(client: AsyncClient):
    signup = await client.post(
        "/api/v1/users/signup",
        json={
            "email": "logout@example.com",
            "password": "password123",
            "checked_password": "password123",
            "nickname": "logoutuser",
        },
    )
    refresh = signup.json()["refresh_token"]
    logout = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": refresh}
    )
    assert logout.status_code == 200

    again = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh}
    )
    assert again.status_code == 401
