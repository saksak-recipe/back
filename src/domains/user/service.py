from datetime import datetime, timedelta, timezone

from core import security
from core.config import settings
from core.exception.codes import ErrorCode
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    UnAuthorizedException,
)
from domains.auth.refresh_store import RefreshTokenStore
from domains.user.model import User
from domains.user.repository import UserRepository
from domains.user.schemas import (
    UpdateMeRequest,
    UpdatePasswordRequest,
    UserInfoResponse,
)


class UserService:
    def __init__(
        self,
        user_repo: UserRepository,
        refresh_store: RefreshTokenStore | None = None,
    ):
        self.user_repo = user_repo
        self.refresh_store = refresh_store

    async def update_me(
        self, user: User, request: UpdateMeRequest
    ) -> UserInfoResponse:
        if request.nickname is not None:
            existing = await self.user_repo.get_user_by_nickname(request.nickname)
            if existing and existing.id != user.id:
                raise ConflictException(
                    code=ErrorCode.NICKNAME_CONFLICT,
                    detail="이미 사용 중인 닉네임 입니다.(대소문자 구별)",
                )
            user.nickname = request.nickname

        await self.user_repo.save(user)
        return UserInfoResponse.from_user(user)

    async def update_password(
        self, user: User, request: UpdatePasswordRequest
    ) -> UserInfoResponse:
        if user.password is not None:
            if not request.current_password:
                raise BadRequestException(
                    code=ErrorCode.BAD_REQUEST,
                    detail="현재 비밀번호가 필요합니다.",
                )
            if not security.verify_password(request.current_password, user.password):
                raise UnAuthorizedException(
                    detail="현재 비밀번호가 올바르지 않습니다."
                )

        user.password = security.hash_password(request.new_password)
        await self.user_repo.save(user)
        if self.refresh_store is not None:
            await self.refresh_store.revoke_all_for_user(user.id)
        return UserInfoResponse.from_user(user)

    async def withdraw(self, user: User) -> None:
        user.deleted_at = datetime.now(timezone.utc)
        await self.user_repo.save(user)
        if self.refresh_store is not None:
            await self.refresh_store.revoke_all_for_user(user.id)

    async def purge_expired_withdrawn_users(
        self, now: datetime | None = None
    ) -> int:
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=settings.WITHDRAWAL_GRACE_DAYS)
        users = await self.user_repo.list_withdrawn_before(cutoff)

        for user in users:
            await self.user_repo.delete_user(user)

        return len(users)

    async def purge_unverified_users(
        self,
        older_than: timedelta,
        now: datetime | None = None,
    ) -> int:
        now = now or datetime.now(timezone.utc)
        cutoff = now - older_than
        users = await self.user_repo.list_unverified_before(cutoff)

        for user in users:
            await self.user_repo.delete_user(user)

        return len(users)
