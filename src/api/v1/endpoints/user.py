from fastapi import APIRouter, status, Depends

from api.deps import get_auth_service, get_current_user, get_user_service
from domains.user.model import User
from domains.user.schemas import (
    SignUpRequest,
    SignUpResponse,
    UpdateMeRequest,
    UpdatePasswordRequest,
    UserInfoResponse,
)
from domains.user.service import UserService
from domains.auth.service import AuthService

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "/signup", status_code=status.HTTP_201_CREATED, response_model=SignUpResponse
)
async def signup(
    request: SignUpRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> SignUpResponse:
    result = await auth_service.signup(request)
    return SignUpResponse(**result)


@router.get("/me", response_model=UserInfoResponse)
async def get_me(user: User = Depends(get_current_user)) -> UserInfoResponse:
    return UserInfoResponse.from_user(user)


@router.patch("/me", response_model=UserInfoResponse)
async def update_me(
    request: UpdateMeRequest,
    user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserInfoResponse:
    return await user_service.update_me(user, request)


@router.patch("/me/password", response_model=UserInfoResponse)
async def update_password(
    request: UpdatePasswordRequest,
    user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserInfoResponse:
    return await user_service.update_password(user, request)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw(
    user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> None:
    await user_service.withdraw(user)
