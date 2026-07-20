from fastapi import APIRouter, status, Depends

from api.deps import get_auth_service
from domains.auth.service import AuthService
from domains.user.schemas import LogInRequest, LogInResponse, RefreshRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", status_code=status.HTTP_200_OK, response_model=LogInResponse)
async def log_in(
    request: LogInRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> LogInResponse:
    return await auth_service.login(request)


@router.post("/refresh", status_code=status.HTTP_200_OK, response_model=LogInResponse)
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
