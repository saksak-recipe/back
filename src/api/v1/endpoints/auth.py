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

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=LogInResponse,
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
    responses=create_error_response(InvalidTokenException),
)
async def refresh(
    request: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> LogInResponse:
    return await auth_service.refresh(request.refresh_token)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, bool]:
    await auth_service.logout(request.refresh_token)
    return {"ok": True}
