from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import uuid6
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core import security
from core.exception.codes import ErrorCode
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    UnAuthorizedException,
)
from domains.ingredient.model import Ingredient
from domains.user.model import User
from domains.user.repository import UserRepository
from domains.user.schemas import SignUpRequest, UpdateMeRequest, UpdatePasswordRequest
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
    assert user.is_email_verified is False
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


async def test_get_user_info_includes_link_flags(
    user_service: UserService, user_repo: AsyncMock
):
    user = User(
        id=uuid6.uuid7(),
        email="k@example.com",
        password=None,
        kakao_id="123",
        nickname="kakao",
    )
    user_repo.get_user_by_id.return_value = user

    info = await user_service.get_user_info(user.id)

    assert info.has_password is False
    assert info.has_kakao is True


async def test_update_me_changes_nickname(
    user_service: UserService, user_repo: AsyncMock
):
    user = User(
        id=uuid6.uuid7(),
        email="a@example.com",
        password="h",
        nickname="old",
    )
    user_repo.get_user_by_nickname.return_value = None
    user_repo.save.side_effect = lambda saved_user: saved_user

    info = await user_service.update_me(user, UpdateMeRequest(nickname="newname"))

    assert info.nickname == "newname"
    user_repo.save.assert_awaited_once()


async def test_update_password_sets_for_kakao_user(
    user_service: UserService, user_repo: AsyncMock
):
    user = User(
        id=uuid6.uuid7(),
        email="k@example.com",
        password=None,
        kakao_id="1",
        nickname="k",
    )
    user_repo.save.side_effect = lambda saved_user: saved_user
    request = UpdatePasswordRequest(
        new_password="password123",
        checked_password="password123",
        current_password=None,
    )

    info = await user_service.update_password(user, request)

    assert info.has_password is True
    assert user.password is not None
    assert security.verify_password("password123", user.password)


async def test_update_password_requires_current_when_has_password(
    user_service: UserService,
):
    user = User(
        email="a@example.com",
        password=security.hash_password("password123"),
        nickname="a",
    )
    request = UpdatePasswordRequest(
        new_password="newpass123",
        checked_password="newpass123",
        current_password=None,
    )

    with pytest.raises(BadRequestException) as exc_info:
        await user_service.update_password(user, request)

    assert exc_info.value.code == ErrorCode.BAD_REQUEST


async def test_update_password_rejects_wrong_current(user_service: UserService):
    user = User(
        email="a@example.com",
        password=security.hash_password("password123"),
        nickname="a",
    )
    request = UpdatePasswordRequest(
        new_password="newpass123",
        checked_password="newpass123",
        current_password="wrongpass1",
    )

    with pytest.raises(UnAuthorizedException):
        await user_service.update_password(user, request)


async def test_withdraw_sets_deleted_at(
    user_service: UserService, user_repo: AsyncMock
):
    user = User(email="a@example.com", password="h", nickname="a")
    user_repo.save.side_effect = lambda saved_user: saved_user

    await user_service.withdraw(user)

    assert user.deleted_at is not None
    user_repo.save.assert_awaited_once()


async def test_purge_deletes_expired_only(
    user_service: UserService, user_repo: AsyncMock
):
    old = User(email="old@example.com", password="h", nickname="old")
    old.deleted_at = datetime.now(timezone.utc) - timedelta(days=8)
    user_repo.list_withdrawn_before.return_value = [old]

    deleted = await user_service.purge_expired_withdrawn_users()

    assert deleted == 1
    user_repo.delete_user.assert_awaited_once_with(old)


async def test_purge_unverified_deletes_only_stale_candidates(
    user_service: UserService, user_repo: AsyncMock
):
    now = datetime.now(timezone.utc)
    stale = User(
        email="stale@example.com",
        password="h",
        nickname="stale",
        is_email_verified=False,
        created_at=now - timedelta(days=3),
    )
    user_repo.list_unverified_before.return_value = [stale]

    deleted = await user_service.purge_unverified_users(
        older_than=timedelta(days=1),
        now=now,
    )

    assert deleted == 1
    user_repo.list_unverified_before.assert_awaited_once()
    user_repo.delete_user.assert_awaited_once_with(stale)


async def test_purge_unverified_hard_deletes_from_db(
    db_session: AsyncSession,
):
    now = datetime.now(timezone.utc)
    old_unverified = User(
        email="old-unverified@example.com",
        password="h",
        nickname="old-unverified",
        is_email_verified=False,
        created_at=now - timedelta(days=2),
    )
    fresh_unverified = User(
        email="fresh-unverified@example.com",
        password="h",
        nickname="fresh-unverified",
        is_email_verified=False,
        created_at=now - timedelta(hours=1),
    )
    verified = User(
        email="verified@example.com",
        password="h",
        nickname="verified",
        is_email_verified=True,
        created_at=now - timedelta(days=10),
    )
    db_session.add_all([old_unverified, fresh_unverified, verified])
    await db_session.flush()

    service = UserService(user_repo=UserRepository(db_session))
    deleted = await service.purge_unverified_users(
        older_than=timedelta(days=1),
        now=now,
    )

    assert deleted == 1
    assert await db_session.get(User, old_unverified.id) is None
    assert await db_session.get(User, fresh_unverified.id) is not None
    assert await db_session.get(User, verified.id) is not None


async def test_purge_hard_deletes_user_and_cascades_ingredients(
    db_session: AsyncSession,
):
    now = datetime.now(timezone.utc)
    user = User(
        email="expired@example.com",
        password="h",
        nickname="expired",
        deleted_at=now - timedelta(days=8),
    )
    ingredient = Ingredient(
        user=user,
        ingredient_name="양파",
        purchase_date=now.date(),
    )
    db_session.add_all([user, ingredient])
    await db_session.flush()
    user_id = user.id
    ingredient_id = ingredient.id

    service = UserService(user_repo=UserRepository(db_session))
    deleted = await service.purge_expired_withdrawn_users(now=now)

    assert deleted == 1
    assert await db_session.get(User, user_id) is None
    result = await db_session.execute(
        select(Ingredient).where(Ingredient.id == ingredient_id)
    )
    assert result.scalar_one_or_none() is None
