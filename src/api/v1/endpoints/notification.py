from uuid import UUID

from fastapi import APIRouter, Depends, status

from api.deps import get_notification_service
from core.exception.exceptions import (
    NotificationNotFoundException,
    UnAuthorizedException,
)
from core.exception.openapi import create_error_response
from domains.notification.schemas import NotificationResponse, UnreadCountResponse
from domains.notification.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=list[NotificationResponse],
    responses=create_error_response(UnAuthorizedException),
)
async def list_notifications(
    service: NotificationService = Depends(get_notification_service),
) -> list[NotificationResponse]:
    return await service.list_notifications()


@router.get(
    "/unread-count",
    status_code=status.HTTP_200_OK,
    response_model=UnreadCountResponse,
    responses=create_error_response(UnAuthorizedException),
)
async def unread_count(
    service: NotificationService = Depends(get_notification_service),
) -> UnreadCountResponse:
    return await service.unread_count()


@router.patch(
    "/{notification_id}/read",
    status_code=status.HTTP_200_OK,
    response_model=NotificationResponse,
    responses=create_error_response(
        UnAuthorizedException, NotificationNotFoundException
    ),
)
async def mark_read(
    notification_id: UUID,
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    return await service.mark_read(notification_id)


@router.post(
    "/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=create_error_response(UnAuthorizedException),
)
async def mark_all_read(
    service: NotificationService = Depends(get_notification_service),
) -> None:
    await service.mark_all_read()
