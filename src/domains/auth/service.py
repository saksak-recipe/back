from uuid import UUID

from core import security
from core.exception.exceptions import UnAuthorizedException

from domains.user.repository import UserRepository
from domains.user.model import User
from domains.user.schemas import LogInRequest, LogInResponse, UserInfoResponse


class AuthService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def issue_tokens(self, user: User) -> str:
        access_token = security.create_jwt(user.id)
        return access_token

    async def login(self, request: LogInRequest) -> LogInResponse:
        user = await self.user_repo.get_user_by_email(str(request.email))
        if not user or not user.password:
            raise UnAuthorizedException(
                detail="이메일 또는 비밀번호가 올바르지 않습니다."
            )
        if not security.verify_password(request.password, user.password):
            raise UnAuthorizedException(
                detail="이메일 또는 비밀번호가 올바르지 않습니다."
            )

        access_token = await self.issue_tokens(user)
        return LogInResponse(
            info=UserInfoResponse.model_validate(user), access_token=access_token
        )

    async def get_user_by_token(self, access_token: str) -> User:
        user_id = UUID(security.decode_jwt(access_token))
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            raise UnAuthorizedException(detail="사용자를 찾을 수 없습니다.")
        return user
