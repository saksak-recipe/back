from datetime import datetime, timedelta, timezone
from uuid import UUID

from core import security
from core.config import settings
from core.exception.codes import ErrorCode
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    UnAuthorizedException,
    UserNotFoundException,
)

from domains.user.model import User
from domains.user.repository import UserRepository
from domains.user.schemas import (
    SignUpRequest,
    UpdateMeRequest,
    UpdatePasswordRequest,
    UserInfoResponse,
)


class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def sign_up(self, request: SignUpRequest) -> User:
        if await self.user_repo.get_user_by_email(str(request.email)):
            raise ConflictException(
                code=ErrorCode.EMAIL_CONFLICT,
                detail="이미 사용 중인 이메일 입니다.",
            )
        if await self.user_repo.get_user_by_nickname(request.nickname):
            raise ConflictException(
                code=ErrorCode.NICKNAME_CONFLICT,
                detail="이미 사용 중인 닉네임 입니다.(대소문자 구별)",
            )

        if request.password != request.checked_password:
            raise BadRequestException(
                code=ErrorCode.PASSWORD_MISMATCH,
                detail="비밀번호와 비밀번호 확인이 일치하지 않습니다.",
            )

        hashed_password = security.hash_password(request.password)

        user = User(
            email=str(request.email),
            password=hashed_password,
            nickname=request.nickname,
        )

        return await self.user_repo.add_user(user)

    async def get_user_info(self, user_id: UUID) -> UserInfoResponse:
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            raise UserNotFoundException()
        return UserInfoResponse.from_user(user)

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
        return UserInfoResponse.from_user(user)

    async def withdraw(self, user: User) -> None:
        user.deleted_at = datetime.now(timezone.utc)
        await self.user_repo.save(user)

    async def purge_expired_withdrawn_users(
        self, now: datetime | None = None
    ) -> int:
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=settings.WITHDRAWAL_GRACE_DAYS)
        users = await self.user_repo.list_withdrawn_before(cutoff)

        for user in users:
            await self.user_repo.delete_user(user)

        return len(users)
