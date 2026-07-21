from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from core import security
from core.config import settings
from core.exception.codes import ErrorCode
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    InvalidTokenException,
    UnAuthorizedException,
    UserNotFoundException,
)
from domains.auth import kakao_client
from domains.auth.email_service import EmailService
from domains.auth.refresh_store import RefreshTokenStore
from domains.auth.schemas import (
    EmailResendRequest,
    EmailVerifyRequest,
    KakaoAuthResponse,
    KakaoCompleteRequest,
    KakaoNeedsProfileResponse,
)
from domains.auth.verification_store import PURPOSE_SIGNUP, VerificationCodeStore
from domains.user.model import User
from domains.user.repository import UserRepository
from domains.user.schemas import LogInRequest, LogInResponse, UserInfoResponse


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        refresh_store: RefreshTokenStore,
        verification_store: VerificationCodeStore,
        email_service: EmailService,
    ) -> None:
        self.user_repo = user_repo
        self.refresh_store = refresh_store
        self.verification_store = verification_store
        self.email_service = email_service

    async def issue_tokens(self, user: User) -> TokenPair:
        access_token = security.create_jwt(user.id)
        refresh_token = security.create_refresh_token()
        await self.refresh_store.save(refresh_token, user.id)
        return TokenPair(access_token=access_token, refresh_token=refresh_token)

    def _to_auth_response(self, user: User, tokens: TokenPair) -> LogInResponse:
        return LogInResponse(
            info=UserInfoResponse.from_user(user),
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        )

    def _to_kakao_auth_response(
        self, user: User, tokens: TokenPair
    ) -> KakaoAuthResponse:
        return KakaoAuthResponse(
            info=UserInfoResponse.from_user(user),
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        )

    async def send_signup_code(self, email: str) -> None:
        code = await self.verification_store.issue(PURPOSE_SIGNUP, email)
        await self.email_service.send_verification_code(
            email, code, PURPOSE_SIGNUP
        )

    async def verify_email(self, request: EmailVerifyRequest) -> LogInResponse:
        email = str(request.email)
        user = await self.user_repo.get_user_by_email(email)
        if not user:
            raise UserNotFoundException()
        if user.is_email_verified:
            raise BadRequestException(
                code=ErrorCode.EMAIL_ALREADY_VERIFIED,
                detail="이미 인증된 이메일입니다.",
            )
        await self.verification_store.verify(PURPOSE_SIGNUP, email, request.code)
        user.is_email_verified = True
        user = await self.user_repo.save(user)
        tokens = await self.issue_tokens(user)
        return self._to_auth_response(user, tokens)

    async def resend_verification(self, request: EmailResendRequest) -> dict:
        email = str(request.email)
        user = await self.user_repo.get_user_by_email(email)
        if not user:
            raise UserNotFoundException()
        if user.is_email_verified:
            raise BadRequestException(
                code=ErrorCode.EMAIL_ALREADY_VERIFIED,
                detail="이미 인증된 이메일입니다.",
            )
        code = await self.verification_store.issue(PURPOSE_SIGNUP, email)
        await self.email_service.send_verification_code(
            email, code, PURPOSE_SIGNUP
        )
        return {"ok": True}

    async def login(self, request: LogInRequest) -> LogInResponse:
        user = await self.user_repo.get_user_by_email(str(request.email))
        if not user:
            raise UnAuthorizedException(
                detail="이메일 또는 비밀번호가 올바르지 않습니다."
            )
        if user.password is None:
            raise UnAuthorizedException(detail="카카오로 로그인해 주세요")
        if not security.verify_password(request.password, user.password):
            raise UnAuthorizedException(
                detail="이메일 또는 비밀번호가 올바르지 않습니다."
            )
        if not user.is_email_verified:
            raise UnAuthorizedException(
                code=ErrorCode.EMAIL_NOT_VERIFIED,
                detail="이메일 인증이 필요합니다.",
            )
        user = await self._restore_if_within_grace(user)
        tokens = await self.issue_tokens(user)
        return self._to_auth_response(user, tokens)

    async def login_with_kakao(
        self, access_token: str
    ) -> KakaoAuthResponse | KakaoNeedsProfileResponse:
        kakao_id = await kakao_client.fetch_kakao_user_id(access_token)
        user = await self.user_repo.get_user_by_kakao_id(kakao_id)
        if user:
            user = await self._restore_if_within_grace(user)
            tokens = await self.issue_tokens(user)
            return self._to_kakao_auth_response(user, tokens)
        signup_token = security.create_kakao_signup_token(kakao_id)
        return KakaoNeedsProfileResponse(signup_token=signup_token)

    async def complete_kakao_signup(
        self, request: KakaoCompleteRequest
    ) -> KakaoAuthResponse:
        kakao_id = security.decode_kakao_signup_token(request.signup_token)

        existing = await self.user_repo.get_user_by_kakao_id(kakao_id)
        if existing:
            existing = await self._restore_if_within_grace(existing)
            tokens = await self.issue_tokens(existing)
            return self._to_kakao_auth_response(existing, tokens)

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

        user = User(
            email=str(request.email),
            password=None,
            kakao_id=kakao_id,
            nickname=request.nickname,
            is_email_verified=True,
        )
        user = await self.user_repo.add_user(user)
        tokens = await self.issue_tokens(user)
        return self._to_kakao_auth_response(user, tokens)

    async def refresh(self, refresh_token: str) -> LogInResponse:
        user_id = await self.refresh_store.pop_user_id(refresh_token)
        if user_id is None:
            raise InvalidTokenException(detail="유효하지 않은 리프레시 토큰입니다.")
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            raise InvalidTokenException(detail="유효하지 않은 리프레시 토큰입니다.")
        if user.deleted_at is not None:
            raise InvalidTokenException(detail="유효하지 않은 리프레시 토큰입니다.")
        tokens = await self.issue_tokens(user)
        return self._to_auth_response(user, tokens)

    async def logout(self, refresh_token: str) -> None:
        await self.refresh_store.delete(refresh_token)

    async def get_user_by_token(self, access_token: str) -> User:
        user_id = UUID(security.decode_jwt(access_token))
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            raise UnAuthorizedException(detail="사용자를 찾을 수 없습니다.")
        await self._reject_if_withdrawn(user)
        return user

    def _is_within_grace(self, deleted_at: datetime, now: datetime) -> bool:
        if deleted_at.tzinfo is None:
            deleted_at = deleted_at.replace(tzinfo=timezone.utc)
        return now - deleted_at <= timedelta(days=settings.WITHDRAWAL_GRACE_DAYS)

    async def _reject_if_withdrawn(self, user: User) -> None:
        if user.deleted_at is not None:
            raise UnAuthorizedException(detail="사용자를 찾을 수 없습니다.")

    async def _restore_if_within_grace(self, user: User) -> User:
        if user.deleted_at is None:
            return user
        now = datetime.now(timezone.utc)
        if self._is_within_grace(user.deleted_at, now):
            user.deleted_at = None
            return await self.user_repo.save(user)
        raise UnAuthorizedException(
            detail="이메일 또는 비밀번호가 올바르지 않습니다."
        )
