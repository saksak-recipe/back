from dataclasses import dataclass
from uuid import UUID

from core import security
from core.exception.exceptions import InvalidTokenException, UnAuthorizedException
from domains.auth.refresh_store import RefreshTokenStore
from domains.user.model import User
from domains.user.repository import UserRepository
from domains.user.schemas import LogInRequest, LogInResponse, UserInfoResponse


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(
        self, user_repo: UserRepository, refresh_store: RefreshTokenStore
    ) -> None:
        self.user_repo = user_repo
        self.refresh_store = refresh_store

    async def issue_tokens(self, user: User) -> TokenPair:
        access_token = security.create_jwt(user.id)
        refresh_token = security.create_refresh_token()
        await self.refresh_store.save(refresh_token, user.id)
        return TokenPair(access_token=access_token, refresh_token=refresh_token)

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
        tokens = await self.issue_tokens(user)
        return LogInResponse(
            info=UserInfoResponse.model_validate(user),
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        )

    async def refresh(self, refresh_token: str) -> LogInResponse:
        user_id = await self.refresh_store.pop_user_id(refresh_token)
        if user_id is None:
            raise InvalidTokenException(detail="유효하지 않은 리프레시 토큰입니다.")
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            raise InvalidTokenException(detail="유효하지 않은 리프레시 토큰입니다.")
        tokens = await self.issue_tokens(user)
        return LogInResponse(
            info=UserInfoResponse.model_validate(user),
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        )

    async def logout(self, refresh_token: str) -> None:
        await self.refresh_store.delete(refresh_token)

    async def get_user_by_token(self, access_token: str) -> User:
        user_id = UUID(security.decode_jwt(access_token))
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            raise UnAuthorizedException(detail="사용자를 찾을 수 없습니다.")
        return user
