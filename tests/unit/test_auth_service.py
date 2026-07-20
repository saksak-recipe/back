from unittest.mock import AsyncMock

import pytest
import uuid6

from core import security
from core.exception.exceptions import InvalidTokenException, UnAuthorizedException
from domains.auth.service import AuthService
from domains.user.model import User
from domains.user.schemas import LogInRequest


@pytest.fixture
def user_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def refresh_store() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def auth_service(user_repo: AsyncMock, refresh_store: AsyncMock) -> AuthService:
    return AuthService(user_repo=user_repo, refresh_store=refresh_store)


@pytest.fixture
def existing_user() -> User:
    return User(
        id=uuid6.uuid7(),
        email="test@example.com",
        password=security.hash_password("password123"),
        nickname="testuser",
    )


async def test_login_returns_access_and_refresh(
    auth_service: AuthService,
    user_repo: AsyncMock,
    refresh_store: AsyncMock,
    existing_user: User,
):
    user_repo.get_user_by_email.return_value = existing_user

    response = await auth_service.login(
        LogInRequest(email="test@example.com", password="password123")
    )

    assert response.access_token
    assert response.refresh_token
    assert response.info.email == "test@example.com"
    refresh_store.save.assert_awaited_once()


async def test_login_raises_when_user_not_found(
    auth_service: AuthService, user_repo: AsyncMock
):
    user_repo.get_user_by_email.return_value = None

    with pytest.raises(UnAuthorizedException):
        await auth_service.login(
            LogInRequest(email="missing@example.com", password="password123")
        )


async def test_login_raises_on_wrong_password(
    auth_service: AuthService, user_repo: AsyncMock, existing_user: User
):
    user_repo.get_user_by_email.return_value = existing_user

    with pytest.raises(UnAuthorizedException):
        await auth_service.login(
            LogInRequest(email="test@example.com", password="wrong-password")
        )


async def test_refresh_rotates_tokens(
    auth_service: AuthService,
    user_repo: AsyncMock,
    refresh_store: AsyncMock,
    existing_user: User,
):
    refresh_store.pop_user_id.return_value = existing_user.id
    user_repo.get_user_by_id.return_value = existing_user

    old = "old-refresh"
    response = await auth_service.refresh(old)

    assert response.access_token
    assert response.refresh_token
    assert response.refresh_token != old
    assert response.info.id == existing_user.id
    refresh_store.save.assert_awaited_once()


async def test_refresh_rejects_unknown_token(
    auth_service: AuthService, refresh_store: AsyncMock
):
    refresh_store.pop_user_id.return_value = None
    with pytest.raises(InvalidTokenException):
        await auth_service.refresh("missing")


async def test_logout_deletes_refresh(
    auth_service: AuthService, refresh_store: AsyncMock
):
    await auth_service.logout("some-refresh")
    refresh_store.delete.assert_awaited_once_with("some-refresh")


async def test_get_user_by_token_returns_user(
    auth_service: AuthService, user_repo: AsyncMock, existing_user: User
):
    token = security.create_jwt(existing_user.id)
    user_repo.get_user_by_id.return_value = existing_user

    user = await auth_service.get_user_by_token(token)

    assert user.id == existing_user.id


async def test_get_user_by_token_raises_when_user_missing(
    auth_service: AuthService, user_repo: AsyncMock, existing_user: User
):
    token = security.create_jwt(existing_user.id)
    user_repo.get_user_by_id.return_value = None

    with pytest.raises(UnAuthorizedException):
        await auth_service.get_user_by_token(token)
