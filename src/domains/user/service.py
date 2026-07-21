from uuid import UUID

from core import security
from core.exception.exceptions import (
    ConflictException,
    BadRequestException,
    UserNotFoundException,
)
from core.exception.codes import ErrorCode

from domains.user.repository import UserRepository
from domains.user.schemas import SignUpRequest, UserInfoResponse
from domains.user.model import User


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
