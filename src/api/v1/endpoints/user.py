from fastapi import APIRouter, status, Depends

from api.deps import get_user_service, get_auth_service
from domains.user.schemas import SignUpResponse, SignUpRequest, UserInfoResponse
from domains.user.service import UserService
from domains.auth.service import AuthService

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "/signup", status_code=status.HTTP_201_CREATED, response_model=SignUpResponse
)
async def signup(
    request: SignUpRequest,
    user_service: UserService = Depends(get_user_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> SignUpResponse:
    user = await user_service.sign_up(request)
    tokens = await auth_service.issue_tokens(user)
    return SignUpResponse(
        info=UserInfoResponse.model_validate(user),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
    )
