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

router = APIRouter(prefix="/notifications", tags=["알림"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=list[NotificationResponse],
    summary="알림 목록 조회",
    description="현재 사용자의 알림 목록을 조회합니다.",
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
    summary="읽지 않은 알림 수",
    description="현재 사용자의 읽지 않은 알림 개수를 반환합니다.",
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
    summary="알림 읽음 처리",
    description="특정 알림을 읽음 상태로 변경합니다.",
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
    summary="알림 전체 읽음 처리",
    description="현재 사용자의 모든 알림을 읽음 상태로 변경합니다.",
    responses=create_error_response(UnAuthorizedException),
)
async def mark_all_read(
    service: NotificationService = Depends(get_notification_service),
) -> None:
    await service.mark_all_read()


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="알림 삭제",
    description="특정 알림을 삭제합니다.",
    responses=create_error_response(
        UnAuthorizedException, NotificationNotFoundException
    ),
)
async def delete_notification(
    notification_id: UUID,
    service: NotificationService = Depends(get_notification_service),
) -> None:
    await service.delete(notification_id)
