from datetime import date, timedelta

from httpx import AsyncClient

from core.exception.codes import ErrorCode
from domains.ingredient.model import Ingredient
from domains.user.model import User
from core import security


async def test_notifications_require_auth(client: AsyncClient):
    response = await client.get("/api/v1/notifications")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_expiry_soon_appears_on_list(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    test_user: User,
):
    today = date.today()
    db_session.add(
        Ingredient(
            user_id=test_user.id,
            ingredient_name="우유",
            purchase_date=today,
            expiration_date=today + timedelta(days=1),
        )
    )
    await db_session.flush()

    listed = await client.get("/api/v1/notifications", headers=auth_headers)
    assert listed.status_code == 200
    body = listed.json()
    assert any(item["type"] == "expiry_soon" for item in body)

    count = await client.get(
        "/api/v1/notifications/unread-count", headers=auth_headers
    )
    assert count.status_code == 200
    assert count.json()["count"] >= 1

    notif_id = next(item["id"] for item in body if item["type"] == "expiry_soon")
    read = await client.patch(
        f"/api/v1/notifications/{notif_id}/read", headers=auth_headers
    )
    assert read.status_code == 200
    assert read.json()["is_read"] is True

    await client.post("/api/v1/notifications/read-all", headers=auth_headers)
    count2 = await client.get(
        "/api/v1/notifications/unread-count", headers=auth_headers
    )
    assert count2.json()["count"] == 0


async def test_invite_creates_notification_for_invitee(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    test_user: User,
):
    invitee = User(
        email="invitee2@example.com",
        password=security.hash_password("password123"),
        nickname="invitee2",
        is_email_verified=True,
    )
    db_session.add(invitee)
    await db_session.flush()
    invitee_headers = {
        "Authorization": f"Bearer {security.create_jwt(invitee.id)}"
    }

    created = await client.post(
        "/api/v1/groups",
        headers=auth_headers,
        json={"name": "알림그룹"},
    )
    assert created.status_code == 201

    invited = await client.post(
        "/api/v1/groups/me/invites",
        headers=auth_headers,
        json={"nickname": "invitee2"},
    )
    assert invited.status_code == 201
    invite_id = invited.json()["id"]

    listed = await client.get(
        "/api/v1/notifications", headers=invitee_headers
    )
    assert listed.status_code == 200
    invites = [n for n in listed.json() if n["type"] == "group_invite"]
    assert len(invites) == 1
    assert invites[0]["payload"]["invite_id"] == invite_id

    other = await client.get("/api/v1/notifications", headers=auth_headers)
    assert all(n["type"] != "group_invite" for n in other.json())


async def test_delete_notification_removes_from_list(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    test_user: User,
):
    today = date.today()
    db_session.add(
        Ingredient(
            user_id=test_user.id,
            ingredient_name="두부",
            purchase_date=today,
            expiration_date=today + timedelta(days=1),
        )
    )
    await db_session.flush()

    listed = await client.get("/api/v1/notifications", headers=auth_headers)
    assert listed.status_code == 200
    notif_id = next(
        item["id"] for item in listed.json() if item["type"] == "expiry_soon"
    )

    deleted = await client.delete(
        f"/api/v1/notifications/{notif_id}", headers=auth_headers
    )
    assert deleted.status_code == 204

    listed_again = await client.get(
        "/api/v1/notifications", headers=auth_headers
    )
    assert all(item["id"] != notif_id for item in listed_again.json())


async def test_read_other_users_notification_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    test_user: User,
):
    other = User(
        email="other@example.com",
        password=security.hash_password("password123"),
        nickname="otheruser",
        is_email_verified=True,
    )
    db_session.add(other)
    await db_session.flush()
    other_headers = {
        "Authorization": f"Bearer {security.create_jwt(other.id)}"
    }

    today = date.today()
    db_session.add(
        Ingredient(
            user_id=test_user.id,
            ingredient_name="계란",
            purchase_date=today,
            expiration_date=today,
        )
    )
    await db_session.flush()
    listed = await client.get("/api/v1/notifications", headers=auth_headers)
    notif_id = listed.json()[0]["id"]

    resp = await client.patch(
        f"/api/v1/notifications/{notif_id}/read",
        headers=other_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == ErrorCode.NOTIFICATION_NOT_FOUND
