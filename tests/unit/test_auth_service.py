from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import uuid6

from core import security
from core.exception.codes import ErrorCode
from core.exception.exceptions import (
    BadRequestException,
    InvalidTokenException,
    UnAuthorizedException,
)
from domains.auth.schemas import (
    EmailVerifyRequest,
    KakaoCompleteRequest,
    PasswordResetConfirmRequest,
)
from domains.auth.service import AuthService
from domains.auth.verification_store import PURPOSE_PASSWORD_RESET, PURPOSE_SIGNUP
from domains.user.model import User
from domains.user.schemas import LogInRequest


@pytest.fixture
def user_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def refresh_store() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def verification_store() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def email_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def auth_service(
    user_repo: AsyncMock,
    refresh_store: AsyncMock,
    verification_store: AsyncMock,
    email_service: AsyncMock,
) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        refresh_store=refresh_store,
        verification_store=verification_store,
        email_service=email_service,
    )


@pytest.fixture
def existing_user() -> User:
    return User(
        id=uuid6.uuid7(),
        email="test@example.com",
        password=security.hash_password("password123"),
        nickname="testuser",
        is_email_verified=True,
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


async def test_login_rejects_unverified_email_user(
    auth_service: AuthService, user_repo: AsyncMock
):
    unverified = User(
        id=uuid6.uuid7(),
        email="unverified@example.com",
        password=security.hash_password("password123"),
        nickname="unverified",
        is_email_verified=False,
    )
    user_repo.get_user_by_email.return_value = unverified

    with pytest.raises(UnAuthorizedException) as exc_info:
        await auth_service.login(
            LogInRequest(email="unverified@example.com", password="password123")
        )

    assert exc_info.value.code == ErrorCode.EMAIL_NOT_VERIFIED


async def test_verify_email_issues_tokens(
    auth_service: AuthService,
    user_repo: AsyncMock,
    refresh_store: AsyncMock,
    verification_store: AsyncMock,
):
    user = User(
        id=uuid6.uuid7(),
        email="verify@example.com",
        password=security.hash_password("password123"),
        nickname="verifyme",
        is_email_verified=False,
    )
    user_repo.get_user_by_email.return_value = user
    user_repo.save.side_effect = lambda saved_user: saved_user
    verification_store.verify.return_value = None

    response = await auth_service.verify_email(
        EmailVerifyRequest(email="verify@example.com", code="123456")
    )

    assert user.is_email_verified is True
    assert response.access_token
    assert response.refresh_token
    assert response.info.email == "verify@example.com"
    verification_store.verify.assert_awaited_once_with(
        PURPOSE_SIGNUP, "verify@example.com", "123456"
    )
    user_repo.save.assert_awaited_once_with(user)
    refresh_store.save.assert_awaited_once()


async def test_login_restores_soft_deleted_within_grace(
    auth_service: AuthService, user_repo: AsyncMock
):
    user = User(
        id=uuid6.uuid7(),
        email="a@example.com",
        password=security.hash_password("password123"),
        nickname="a",
        is_email_verified=True,
    )
    user.deleted_at = datetime.now(timezone.utc) - timedelta(days=3)
    user_repo.get_user_by_email.return_value = user
    user_repo.save.side_effect = lambda saved_user: saved_user

    response = await auth_service.login(
        LogInRequest(email="a@example.com", password="password123")
    )

    assert user.deleted_at is None
    assert response.access_token
    user_repo.save.assert_awaited_once_with(user)


async def test_login_rejects_soft_deleted_after_grace(
    auth_service: AuthService, user_repo: AsyncMock
):
    user = User(
        id=uuid6.uuid7(),
        email="a@example.com",
        password=security.hash_password("password123"),
        nickname="a",
        is_email_verified=True,
    )
    user.deleted_at = datetime.now(timezone.utc) - timedelta(days=8)
    user_repo.get_user_by_email.return_value = user

    with pytest.raises(
        UnAuthorizedException,
        match="이메일 또는 비밀번호가 올바르지 않습니다",
    ) as exc_info:
        await auth_service.login(
            LogInRequest(email="a@example.com", password="password123")
        )

    assert "탈퇴" not in exc_info.value.detail
    user_repo.save.assert_not_awaited()


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


async def test_kakao_login_restores_within_grace(
    auth_service: AuthService,
    user_repo: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    user = User(
        id=uuid6.uuid7(),
        email="k@example.com",
        password=None,
        kakao_id="99",
        nickname="k",
    )
    user.deleted_at = datetime.now(timezone.utc) - timedelta(days=1)
    user_repo.get_user_by_kakao_id.return_value = user
    user_repo.save.side_effect = lambda saved_user: saved_user
    monkeypatch.setattr(
        "domains.auth.kakao_client.fetch_kakao_user_id",
        AsyncMock(return_value="99"),
    )

    response = await auth_service.login_with_kakao("kakao-token")

    assert user.deleted_at is None
    assert response.access_token
    user_repo.save.assert_awaited_once_with(user)


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
        is_email_verified=True,
    )
    user_repo.add_user.return_value = created

    signup_token = security.create_kakao_signup_token("999888777")

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
    added_user = user_repo.add_user.await_args.args[0]
    assert added_user.is_email_verified is True
    refresh_store.save.assert_awaited_once()


async def test_complete_kakao_sets_verified_true(
    auth_service: AuthService,
    user_repo: AsyncMock,
):
    user_repo.get_user_by_kakao_id.return_value = None
    user_repo.get_user_by_email.return_value = None
    user_repo.get_user_by_nickname.return_value = None

    def _add_user(user: User) -> User:
        user.id = uuid6.uuid7()
        return user

    user_repo.add_user.side_effect = _add_user

    await auth_service.complete_kakao_signup(
        KakaoCompleteRequest(
            signup_token=security.create_kakao_signup_token("111222333"),
            nickname="kakaoverified",
            email="verified@example.com",
        )
    )

    added_user = user_repo.add_user.await_args.args[0]
    assert added_user.is_email_verified is True


async def test_complete_kakao_signup_restores_existing_user_within_grace(
    auth_service: AuthService,
    user_repo: AsyncMock,
):
    user = User(
        id=uuid6.uuid7(),
        email="k@example.com",
        password=None,
        kakao_id="99",
        nickname="k",
    )
    user.deleted_at = datetime.now(timezone.utc) - timedelta(days=1)
    user_repo.get_user_by_kakao_id.return_value = user
    user_repo.save.side_effect = lambda saved_user: saved_user

    response = await auth_service.complete_kakao_signup(
        KakaoCompleteRequest(
            signup_token=security.create_kakao_signup_token("99"),
            nickname="ignored",
            email="ignored@example.com",
        )
    )

    assert user.deleted_at is None
    assert response.status == "authenticated"
    user_repo.save.assert_awaited_once_with(user)


async def test_complete_kakao_signup_rejects_expired_existing_user_generically(
    auth_service: AuthService,
    user_repo: AsyncMock,
):
    user = User(
        id=uuid6.uuid7(),
        email="k@example.com",
        password=None,
        kakao_id="99",
        nickname="k",
    )
    user.deleted_at = datetime.now(timezone.utc) - timedelta(days=8)
    user_repo.get_user_by_kakao_id.return_value = user

    with pytest.raises(UnAuthorizedException) as exc_info:
        await auth_service.complete_kakao_signup(
            KakaoCompleteRequest(
                signup_token=security.create_kakao_signup_token("99"),
                nickname="ignored",
                email="ignored@example.com",
            )
        )

    assert exc_info.value.detail == "이메일 또는 비밀번호가 올바르지 않습니다."


async def test_complete_kakao_signup_rejects_email_conflict(
    auth_service: AuthService, user_repo: AsyncMock
):
    from core.exception.exceptions import ConflictException

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


async def test_refresh_rejects_soft_deleted(
    auth_service: AuthService,
    user_repo: AsyncMock,
    refresh_store: AsyncMock,
    existing_user: User,
):
    existing_user.deleted_at = datetime.now(timezone.utc)
    refresh_store.pop_user_id.return_value = existing_user.id
    user_repo.get_user_by_id.return_value = existing_user

    with pytest.raises(
        InvalidTokenException, match="유효하지 않은 리프레시 토큰입니다"
    ):
        await auth_service.refresh("withdrawn-refresh")

    user_repo.save.assert_not_awaited()
    refresh_store.save.assert_not_awaited()


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


async def test_get_user_by_token_rejects_soft_deleted(
    auth_service: AuthService, user_repo: AsyncMock, existing_user: User
):
    existing_user.deleted_at = datetime.now(timezone.utc)
    token = security.create_jwt(existing_user.id)
    user_repo.get_user_by_id.return_value = existing_user

    with pytest.raises(UnAuthorizedException, match="사용자를 찾을 수 없습니다"):
        await auth_service.get_user_by_token(token)

    user_repo.save.assert_not_awaited()


async def test_request_password_reset_always_ok_even_if_missing(
    auth_service: AuthService,
    user_repo: AsyncMock,
    email_service: AsyncMock,
    verification_store: AsyncMock,
):
    user_repo.get_user_by_email.return_value = None

    result = await auth_service.request_password_reset("no@example.com")

    assert result == {"ok": True, "message": "password_reset_email_sent"}
    verification_store.issue.assert_not_awaited()
    email_service.send_verification_code.assert_not_awaited()


async def test_request_password_reset_skips_kakao_only_user(
    auth_service: AuthService,
    user_repo: AsyncMock,
    email_service: AsyncMock,
    verification_store: AsyncMock,
):
    user_repo.get_user_by_email.return_value = User(
        id=uuid6.uuid7(),
        email="kakao@example.com",
        password=None,
        kakao_id="123",
        nickname="kakao",
        is_email_verified=True,
    )

    result = await auth_service.request_password_reset("kakao@example.com")

    assert result == {"ok": True, "message": "password_reset_email_sent"}
    verification_store.issue.assert_not_awaited()
    email_service.send_verification_code.assert_not_awaited()


async def test_request_password_reset_sends_code_for_password_user(
    auth_service: AuthService,
    user_repo: AsyncMock,
    email_service: AsyncMock,
    verification_store: AsyncMock,
    existing_user: User,
):
    user_repo.get_user_by_email.return_value = existing_user
    verification_store.issue.return_value = "654321"

    result = await auth_service.request_password_reset("test@example.com")

    assert result == {"ok": True, "message": "password_reset_email_sent"}
    verification_store.issue.assert_awaited_once_with(
        PURPOSE_PASSWORD_RESET, "test@example.com"
    )
    email_service.send_verification_code.assert_awaited_once_with(
        "test@example.com", "654321", PURPOSE_PASSWORD_RESET
    )


async def test_confirm_password_reset_updates_password(
    auth_service: AuthService,
    user_repo: AsyncMock,
    verification_store: AsyncMock,
):
    user = User(
        id=uuid6.uuid7(),
        email="reset@example.com",
        password=security.hash_password("oldpass12"),
        nickname="resetuser",
        is_email_verified=True,
    )
    user_repo.get_user_by_email.return_value = user
    user_repo.save.side_effect = lambda saved_user: saved_user
    verification_store.verify.return_value = None

    result = await auth_service.confirm_password_reset(
        PasswordResetConfirmRequest(
            email="reset@example.com",
            code="123456",
            password="newpass12",
            checked_password="newpass12",
        )
    )

    assert result == {"ok": True}
    verification_store.verify.assert_awaited_once_with(
        PURPOSE_PASSWORD_RESET, "reset@example.com", "123456"
    )
    user_repo.save.assert_awaited_once_with(user)
    assert security.verify_password("newpass12", user.password)


async def test_confirm_password_reset_hides_missing_user(
    auth_service: AuthService,
    user_repo: AsyncMock,
    verification_store: AsyncMock,
):
    user_repo.get_user_by_email.return_value = None

    with pytest.raises(BadRequestException) as exc_info:
        await auth_service.confirm_password_reset(
            PasswordResetConfirmRequest(
                email="missing@example.com",
                code="123456",
                password="newpass12",
                checked_password="newpass12",
            )
        )

    assert exc_info.value.code == ErrorCode.INVALID_VERIFICATION_CODE
    verification_store.verify.assert_not_awaited()


async def test_confirm_password_reset_hides_kakao_only_user(
    auth_service: AuthService,
    user_repo: AsyncMock,
    verification_store: AsyncMock,
):
    user_repo.get_user_by_email.return_value = User(
        id=uuid6.uuid7(),
        email="kakao@example.com",
        password=None,
        kakao_id="123",
        nickname="kakao",
        is_email_verified=True,
    )

    with pytest.raises(BadRequestException) as exc_info:
        await auth_service.confirm_password_reset(
            PasswordResetConfirmRequest(
                email="kakao@example.com",
                code="123456",
                password="newpass12",
                checked_password="newpass12",
            )
        )

    assert exc_info.value.code == ErrorCode.INVALID_VERIFICATION_CODE
    verification_store.verify.assert_not_awaited()
