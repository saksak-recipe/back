from fastapi import APIRouter, status, Depends

from api.deps import get_auth_service
from domains.auth.service import AuthService
from domains.user.schemas import LogInRequest, LogInResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", status_code=status.HTTP_200_OK, response_model=LogInResponse)
async def log_in(
    request: LogInRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> LogInResponse:
    return await auth_service.login(request)
