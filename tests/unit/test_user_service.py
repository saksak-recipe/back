from unittest.mock import AsyncMock

import pytest
import uuid6

from core.exception.codes import ErrorCode
from core.exception.exceptions import BadRequestException, ConflictException
from domains.user.model import User
from domains.user.schemas import SignUpRequest
from domains.user.service import UserService


@pytest.fixture
def user_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def user_service(user_repo: AsyncMock) -> UserService:
    return UserService(user_repo=user_repo)


async def test_sign_up_creates_user(user_service: UserService, user_repo: AsyncMock):
    user_repo.get_user_by_email.return_value = None
    user_repo.get_user_by_nickname.return_value = None
    user_repo.add_user.side_effect = lambda user: user

    request = SignUpRequest(
        email="new@example.com",
        password="password123",
        checked_password="password123",
        nickname="newuser",
    )

    user = await user_service.sign_up(request)

    assert user.email == "new@example.com"
    assert user.nickname == "newuser"
    assert user.password != "password123"
    user_repo.add_user.assert_awaited_once()


async def test_sign_up_raises_on_duplicate_email(
    user_service: UserService, user_repo: AsyncMock
):
    user_repo.get_user_by_email.return_value = User(
        email="exists@example.com",
        password="hashed",
        nickname="exists",
    )

    request = SignUpRequest(
        email="exists@example.com",
        password="password123",
        checked_password="password123",
        nickname="newuser",
    )

    with pytest.raises(ConflictException) as exc_info:
        await user_service.sign_up(request)

    assert exc_info.value.code == ErrorCode.EMAIL_CONFLICT


async def test_sign_up_raises_on_duplicate_nickname(
    user_service: UserService, user_repo: AsyncMock
):
    user_repo.get_user_by_email.return_value = None
    user_repo.get_user_by_nickname.return_value = User(
        email="other@example.com",
        password="hashed",
        nickname="Taken",
    )

    request = SignUpRequest(
        email="new@example.com",
        password="password123",
        checked_password="password123",
        nickname="taken",
    )

    with pytest.raises(ConflictException) as exc_info:
        await user_service.sign_up(request)

    assert exc_info.value.code == ErrorCode.NICKNAME_CONFLICT


async def test_sign_up_raises_on_password_mismatch(
    user_service: UserService, user_repo: AsyncMock
):
    user_repo.get_user_by_email.return_value = None
    user_repo.get_user_by_nickname.return_value = None

    request = SignUpRequest.model_construct(
        email="new@example.com",
        password="password123",
        checked_password="different123",
        nickname="newuser",
    )

    with pytest.raises(BadRequestException) as exc_info:
        await user_service.sign_up(request)

    assert exc_info.value.code == ErrorCode.PASSWORD_MISMATCH
