from __future__ import annotations

from datetime import date
from uuid import UUID

import uuid6

from core.exception.exceptions import NotificationNotFoundException
from domains.group.repository import GroupRepository
from domains.ingredient.model import Ingredient
from domains.ingredient.repository import IngredientRepository
from domains.ingredient.service import compute_status
from domains.notification.model import Notification
from domains.notification.repository import NotificationRepository
from domains.notification.schemas import NotificationResponse, UnreadCountResponse
from domains.user.model import User


class NotificationService:
    def __init__(
        self,
        user: User,
        notification_repo: NotificationRepository,
        ingredient_repo: IngredientRepository,
        group_repo: GroupRepository,
    ) -> None:
        self.user = user
        self.notification_repo = notification_repo
        self.ingredient_repo = ingredient_repo
        self.group_repo = group_repo

    async def create_group_invite_notification(
        self,
        *,
        invitee_id: UUID,
        invite_id: UUID,
        group_id: UUID,
        group_name: str,
        inviter_nickname: str,
    ) -> Notification | None:
        body = f"{inviter_nickname}님이 '{group_name}'에 초대했습니다"
        return await self.notification_repo.create_if_absent(
            Notification(
                id=uuid6.uuid7(),
                user_id=invitee_id,
                type="group_invite",
                title="그룹 초대",
                body=body,
                reference_key=f"group_invite:{invite_id}",
                payload={
                    "invite_id": str(invite_id),
                    "group_id": str(group_id),
                    "group_name": group_name,
                    "inviter_nickname": inviter_nickname,
                },
            )
        )

    async def sync_expiry_notifications(self, today: date | None = None) -> None:
        today = today or date.today()
        ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
        membership = await self.group_repo.get_membership(self.user.id)
        if membership is not None:
            ingredients = [
                *ingredients,
                *await self.ingredient_repo.list_by_group(membership.group_id),
            ]
        for ingredient in ingredients:
            await self._maybe_create_expiry(ingredient, today)

    async def _maybe_create_expiry(
        self, ingredient: Ingredient, today: date
    ) -> None:
        status = compute_status(ingredient.expiration_date, today=today)
        if status == "soon":
            ntype = "expiry_soon"
            title = "유통기한 임박"
            body = (
                f"{ingredient.ingredient_name} 유통기한이 "
                f"{ingredient.expiration_date.isoformat()}까지입니다"
            )
        elif status == "expired":
            ntype = "expiry_expired"
            title = "유통기한 만료"
            body = f"{ingredient.ingredient_name} 유통기한이 지났습니다"
        else:
            return

        await self.notification_repo.create_if_absent(
            Notification(
                id=uuid6.uuid7(),
                user_id=self.user.id,
                type=ntype,
                title=title,
                body=body,
                reference_key=f"{ntype}:{ingredient.id}",
                payload={
                    "ingredient_id": ingredient.id,
                    "ingredient_name": ingredient.ingredient_name,
                    "expiration_date": (
                        ingredient.expiration_date.isoformat()
                        if ingredient.expiration_date
                        else None
                    ),
                    "group_id": str(ingredient.group_id)
                    if ingredient.group_id
                    else None,
                },
            )
        )

    async def list_notifications(
        self, today: date | None = None
    ) -> list[NotificationResponse]:
        await self.sync_expiry_notifications(today=today)
        rows = await self.notification_repo.list_by_user(self.user.id)
        return [NotificationResponse.model_validate(r) for r in rows]

    async def unread_count(
        self, today: date | None = None
    ) -> UnreadCountResponse:
        await self.sync_expiry_notifications(today=today)
        count = await self.notification_repo.count_unread(self.user.id)
        return UnreadCountResponse(count=count)

    async def mark_read(self, notification_id: UUID) -> NotificationResponse:
        row = await self.notification_repo.get_by_id_for_user(
            notification_id, self.user.id
        )
        if row is None:
            raise NotificationNotFoundException()
        row = await self.notification_repo.mark_read(row)
        return NotificationResponse.model_validate(row)

    async def mark_all_read(self) -> None:
        await self.notification_repo.mark_all_read(self.user.id)
