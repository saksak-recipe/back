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


async def test_login_rejects_kakao_only_user(
    auth_service: AuthService, user_repo: AsyncMock
):
    kakao_user = User(
        id=uuid6.uuid7(),
        email="kakao@example.com",
        password=None,
        kakao_id="1234567890",
        nickname="kakaouser",
    )
    user_repo.get_user_by_email.return_value = kakao_user

    with pytest.raises(UnAuthorizedException, match="카카오로 로그인해 주세요"):
        await auth_service.login(
            LogInRequest(email="kakao@example.com", password="password123")
        )


async def test_login_with_kakao_returns_tokens_for_existing_user(
    auth_service: AuthService,
    user_repo: AsyncMock,
    refresh_store: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    kakao_user = User(
        id=uuid6.uuid7(),
        email="kakao@example.com",
        password=None,
        kakao_id="1234567890",
        nickname="kakaouser",
    )
    user_repo.get_user_by_kakao_id.return_value = kakao_user

    async def fake_fetch(_token: str) -> str:
        return "1234567890"

    monkeypatch.setattr(
        "domains.auth.kakao_client.fetch_kakao_user_id", fake_fetch
    )

    response = await auth_service.login_with_kakao("kakao-access-token")

    assert response.status == "authenticated"
    assert response.info.email == "kakao@example.com"
    assert response.access_token
    assert response.refresh_token
    refresh_store.save.assert_awaited_once()


async def test_login_with_kakao_returns_needs_profile_for_new_user(
    auth_service: AuthService,
    user_repo: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    user_repo.get_user_by_kakao_id.return_value = None

    async def fake_fetch(_token: str) -> str:
        return "999888777"

    monkeypatch.setattr(
        "domains.auth.kakao_client.fetch_kakao_user_id", fake_fetch
    )

    response = await auth_service.login_with_kakao("kakao-access-token")

    assert response.status == "needs_profile"
    assert response.signup_token
    assert security.decode_kakao_signup_token(response.signup_token) == "999888777"


async def test_complete_kakao_signup_creates_user(
    auth_service: AuthService,
    user_repo: AsyncMock,
    refresh_store: AsyncMock,
):
    user_repo.get_user_by_kakao_id.return_value = None
    user_repo.get_user_by_email.return_value = None
    user_repo.get_user_by_nickname.return_value = None

    created = User(
        id=uuid6.uuid7(),
        email="new@example.com",
        password=None,
        kakao_id="999888777",
        nickname="newbie",
    )
    user_repo.add_user.return_value = created

    signup_token = security.create_kakao_signup_token("999888777")
    from domains.auth.schemas import KakaoCompleteRequest

    response = await auth_service.complete_kakao_signup(
        KakaoCompleteRequest(
            signup_token=signup_token,
            nickname="newbie",
            email="new@example.com",
        )
    )

    assert response.status == "authenticated"
    assert response.info.nickname == "newbie"
    user_repo.add_user.assert_awaited_once()
    refresh_store.save.assert_awaited_once()


async def test_complete_kakao_signup_rejects_email_conflict(
    auth_service: AuthService, user_repo: AsyncMock
):
    from core.exception.exceptions import ConflictException
    from domains.auth.schemas import KakaoCompleteRequest

    user_repo.get_user_by_kakao_id.return_value = None
    user_repo.get_user_by_email.return_value = User(
        id=uuid6.uuid7(),
        email="taken@example.com",
        password=security.hash_password("password123"),
        nickname="other",
    )

    signup_token = security.create_kakao_signup_token("999888777")

    with pytest.raises(ConflictException):
        await auth_service.complete_kakao_signup(
            KakaoCompleteRequest(
                signup_token=signup_token,
                nickname="newbie",
                email="taken@example.com",
            )
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
