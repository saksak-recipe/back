from fastapi import APIRouter, status, Depends

from api.deps import get_auth_service
from core.exception.exceptions import (
    ConflictException,
    InvalidTokenException,
    TooManyRequestsException,
    UnAuthorizedException,
    UserNotFoundException,
)
from core.exception.openapi import create_error_response
from domains.auth.schemas import (
    EmailResendRequest,
    EmailResendResponse,
    EmailVerifyRequest,
    KakaoAuthResponse,
    KakaoCompleteRequest,
    KakaoLoginRequest,
    KakaoNeedsEmailVerificationResponse,
    KakaoNeedsProfileResponse,
    LogInRequest,
    LogInResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    RefreshRequest,
)
from domains.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["인증"])


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=LogInResponse,
    summary="로그인",
    description="이메일과 비밀번호로 로그인하고 액세스·리프레시 토큰을 발급합니다.",
    responses=create_error_response(UnAuthorizedException),
)
async def log_in(
    request: LogInRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> LogInResponse:
    return await auth_service.login(request)


@router.post(
    "/email/verify",
    status_code=status.HTTP_200_OK,
    response_model=LogInResponse,
    summary="이메일 인증",
    description="회원가입 또는 카카오 가입 후 발송된 인증 코드로 이메일을 인증하고 토큰을 발급합니다.",
    responses=create_error_response(UserNotFoundException, UnAuthorizedException),
)
async def verify_email(
    request: EmailVerifyRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> LogInResponse:
    return await auth_service.verify_email(request)


@router.post(
    "/email/resend",
    status_code=status.HTTP_200_OK,
    response_model=EmailResendResponse,
    response_model_exclude_none=True,
    summary="인증 메일 재발송",
    description="이메일 인증 코드를 다시 발송합니다. 요청 횟수에 제한이 있습니다.",
    responses=create_error_response(TooManyRequestsException, UserNotFoundException),
)
async def resend_verification(
    request: EmailResendRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> EmailResendResponse:
    result = await auth_service.resend_verification(request)
    return EmailResendResponse(**result)


@router.post(
    "/password/reset/request",
    status_code=status.HTTP_200_OK,
    response_model=PasswordResetRequestResponse,
    summary="비밀번호 재설정 요청",
    description="비밀번호 재설정 메일을 발송합니다. 요청 횟수에 제한이 있습니다.",
    responses=create_error_response(TooManyRequestsException),
)
async def request_password_reset(
    request: PasswordResetRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> PasswordResetRequestResponse:
    result = await auth_service.request_password_reset(str(request.email))
    return PasswordResetRequestResponse(**result)


@router.post(
    "/password/reset/confirm",
    status_code=status.HTTP_200_OK,
    summary="비밀번호 재설정 확인",
    description="재설정 토큰과 새 비밀번호로 비밀번호를 변경합니다.",
    responses=create_error_response(UnAuthorizedException),
)
async def confirm_password_reset(
    request: PasswordResetConfirmRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    return await auth_service.confirm_password_reset(request)


@router.post(
    "/kakao",
    status_code=status.HTTP_200_OK,
    response_model=KakaoAuthResponse | KakaoNeedsProfileResponse,
    summary="카카오 로그인",
    description="카카오 액세스 토큰으로 로그인합니다. 신규 사용자는 프로필 입력이 필요할 수 있습니다.",
    responses=create_error_response(UnAuthorizedException),
)
async def kakao_login(
    request: KakaoLoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> KakaoAuthResponse | KakaoNeedsProfileResponse:
    return await auth_service.login_with_kakao(request.access_token)


@router.post(
    "/kakao/complete",
    status_code=status.HTTP_200_OK,
    response_model=KakaoAuthResponse | KakaoNeedsEmailVerificationResponse,
    summary="카카오 가입 완료",
    description="카카오 가입용 임시 토큰과 닉네임·이메일로 회원가입을 완료합니다.",
    responses=create_error_response(
        ConflictException, TooManyRequestsException, InvalidTokenException
    ),
)
async def kakao_complete(
    request: KakaoCompleteRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> KakaoAuthResponse | KakaoNeedsEmailVerificationResponse:
    return await auth_service.complete_kakao_signup(request)


@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    response_model=LogInResponse,
    summary="토큰 갱신",
    description="리프레시 토큰으로 액세스·리프레시 토큰을 재발급합니다.",
    responses=create_error_response(InvalidTokenException),
)
async def refresh(
    request: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> LogInResponse:
    return await auth_service.refresh(request.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="로그아웃",
    description="리프레시 토큰을 무효화하여 로그아웃합니다.",
)
async def logout(
    request: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, bool]:
    await auth_service.logout(request.refresh_token)
    return {"ok": True}
