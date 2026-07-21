from datetime import date, timedelta
from uuid import uuid4

import pytest

from domains.group.repository import GroupRepository
from domains.ingredient.model import Ingredient
from domains.ingredient.repository import IngredientRepository
from domains.notification.repository import NotificationRepository
from domains.notification.service import NotificationService
from domains.user.model import User


def _notif_service(user, db_session) -> NotificationService:
    return NotificationService(
        user=user,
        notification_repo=NotificationRepository(db_session),
        ingredient_repo=IngredientRepository(db_session),
        group_repo=GroupRepository(db_session),
    )


@pytest.mark.asyncio
async def test_sync_creates_soon_once(db_session, test_user):
    today = date(2026, 7, 21)
    db_session.add(
        Ingredient(
            user_id=test_user.id,
            ingredient_name="우유",
            purchase_date=today,
            expiration_date=today + timedelta(days=2),
        )
    )
    await db_session.flush()

    service = _notif_service(test_user, db_session)
    first = await service.list_notifications(today=today)
    second = await service.list_notifications(today=today)
    soon = [n for n in first if n.type == "expiry_soon"]
    assert len(soon) == 1
    assert soon[0].title == "유통기한 임박"
    assert len([n for n in second if n.type == "expiry_soon"]) == 1


@pytest.mark.asyncio
async def test_soon_then_expired_creates_second(db_session, test_user):
    soon_day = date(2026, 7, 21)
    expired_day = date(2026, 7, 25)
    db_session.add(
        Ingredient(
            user_id=test_user.id,
            ingredient_name="우유",
            purchase_date=soon_day,
            expiration_date=date(2026, 7, 23),
        )
    )
    await db_session.flush()

    service = _notif_service(test_user, db_session)
    await service.list_notifications(today=soon_day)
    listed = await service.list_notifications(today=expired_day)
    types = {n.type for n in listed}
    assert "expiry_soon" in types
    assert "expiry_expired" in types


@pytest.mark.asyncio
async def test_create_group_invite_notification_for_invitee(db_session, test_user):
    invitee = User(
        email="invitee@example.com",
        password="hashed",
        nickname="invitee",
    )
    db_session.add(invitee)
    await db_session.flush()

    invite_id = uuid4()
    service = _notif_service(test_user, db_session)
    created = await service.create_group_invite_notification(
        invitee_id=invitee.id,
        invite_id=invite_id,
        group_id=uuid4(),
        group_name="우리집",
        inviter_nickname=test_user.nickname,
    )
    assert created is not None
    invitee_list = await _notif_service(invitee, db_session).list_notifications()
    assert len(invitee_list) == 1
    assert invitee_list[0].type == "group_invite"
    assert invitee_list[0].payload["invite_id"] == str(invite_id)
    owner_list = await service.list_notifications()
    assert all(n.type != "group_invite" for n in owner_list)
