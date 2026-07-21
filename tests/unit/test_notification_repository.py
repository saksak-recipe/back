from uuid import uuid4

import pytest

from domains.notification.model import Notification
from domains.notification.repository import NotificationRepository


@pytest.mark.asyncio
async def test_create_if_absent_is_idempotent(db_session, test_user):
    repo = NotificationRepository(db_session)
    key = f"expiry_soon:1"
    first = await repo.create_if_absent(
        Notification(
            user_id=test_user.id,
            type="expiry_soon",
            title="유통기한 임박",
            body="양파 유통기한이 2026-07-24까지입니다",
            reference_key=key,
            payload={"ingredient_id": 1},
        )
    )
    second = await repo.create_if_absent(
        Notification(
            user_id=test_user.id,
            type="expiry_soon",
            title="유통기한 임박",
            body="양파 유통기한이 2026-07-24까지입니다",
            reference_key=key,
            payload={"ingredient_id": 1},
        )
    )
    assert first is not None
    assert second is None
    listed = await repo.list_by_user(test_user.id)
    assert len(listed) == 1


@pytest.mark.asyncio
async def test_mark_read_and_unread_count(db_session, test_user):
    repo = NotificationRepository(db_session)
    n = await repo.create_if_absent(
        Notification(
            user_id=test_user.id,
            type="group_invite",
            title="그룹 초대",
            body="누군가 초대",
            reference_key=f"group_invite:{uuid4()}",
            payload={},
        )
    )
    assert n is not None
    assert await repo.count_unread(test_user.id) == 1
    await repo.mark_read(n)
    assert await repo.count_unread(test_user.id) == 0
