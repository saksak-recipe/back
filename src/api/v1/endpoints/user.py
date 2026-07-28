from fastapi import APIRouter, status, Depends

from api.deps import get_auth_service, get_current_user, get_user_service
from core.exception.exceptions import (
    ConflictException,
    TooManyRequestsException,
    UnAuthorizedException,
)
from core.exception.openapi import create_error_response
from domains.auth.schemas import SignUpRequest, SignUpResponse
from domains.user.model import User
from domains.user.schemas import (
    UpdateMeRequest,
    UpdatePasswordRequest,
    UserInfoResponse,
)
from domains.user.service import UserService
from domains.auth.service import AuthService

router = APIRouter(prefix="/users", tags=["사용자"])


@router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    response_model=SignUpResponse,
    response_model_exclude_none=True,
    summary="회원가입",
    description="이메일·비밀번호·닉네임으로 가입하고 이메일 인증 메일을 발송합니다.",
    responses=create_error_response(ConflictException, TooManyRequestsException),
)
async def signup(
    request: SignUpRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> SignUpResponse:
    result = await auth_service.signup(request)
    return SignUpResponse(**result)


@router.get(
    "/me",
    response_model=UserInfoResponse,
    summary="내 정보 조회",
    description="현재 로그인한 사용자의 프로필 정보를 반환합니다.",
)
async def get_me(user: User = Depends(get_current_user)) -> UserInfoResponse:
    return UserInfoResponse.from_user(user)


@router.patch(
    "/me",
    response_model=UserInfoResponse,
    summary="내 정보 수정",
    description="닉네임 등 현재 사용자 프로필을 수정합니다.",
    responses=create_error_response(ConflictException),
)
async def update_me(
    request: UpdateMeRequest,
    user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserInfoResponse:
    return await user_service.update_me(user, request)


@router.patch(
    "/me/password",
    response_model=UserInfoResponse,
    summary="비밀번호 변경",
    description="현재 비밀번호 확인 후 새 비밀번호로 변경합니다.",
    responses=create_error_response(UnAuthorizedException),
)
async def update_password(
    request: UpdatePasswordRequest,
    user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserInfoResponse:
    return await user_service.update_password(user, request)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="회원 탈퇴",
    description="현재 사용자 계정을 탈퇴 처리합니다.",
)
async def withdraw(
    user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> None:
    await user_service.withdraw(user)
