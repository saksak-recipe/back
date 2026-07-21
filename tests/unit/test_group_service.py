import uuid

import pytest

from core.exception.codes import ErrorCode
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from domains.group.model import GroupMember, GroupRole
from domains.group.repository import GroupRepository
from domains.group.schemas import CreateGroupRequest, UpdateGroupRequest
from domains.group.service import GroupService
from domains.ingredient.repository import IngredientRepository
from domains.user.model import User
from domains.user.repository import UserRepository


def _service(user: User, db_session) -> GroupService:
    return GroupService(
        user=user,
        group_repo=GroupRepository(db_session),
        user_repo=UserRepository(db_session),
        ingredient_repo=IngredientRepository(db_session),
    )


async def _add_user(db_session, email: str, nickname: str) -> User:
    user = User(email=email, password="hashed", nickname=nickname)
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_create_group_and_get_me(db_session, test_user):
    service = _service(test_user, db_session)

    created = await service.create(CreateGroupRequest(name="우리집"))

    assert created.name == "우리집"
    assert len(created.invite_code) == 8
    assert created.members[0].user_id == test_user.id
    assert created.members[0].nickname == test_user.nickname
    assert created.members[0].role == "owner"

    me = await service.get_me()
    assert me.id == created.id


@pytest.mark.asyncio
async def test_create_second_group_conflicts(db_session, test_user):
    service = _service(test_user, db_session)
    await service.create(CreateGroupRequest(name="첫 그룹"))

    with pytest.raises(ConflictException) as exc:
        await service.create(CreateGroupRequest(name="둘"))

    assert exc.value.code == ErrorCode.ALREADY_IN_GROUP


@pytest.mark.asyncio
async def test_get_me_raises_when_user_has_no_group(db_session, test_user):
    service = _service(test_user, db_session)

    with pytest.raises(NotFoundException) as exc:
        await service.get_me()

    assert exc.value.code == ErrorCode.GROUP_NOT_FOUND


@pytest.mark.asyncio
async def test_owner_can_update_group_name(db_session, test_user):
    service = _service(test_user, db_session)
    await service.create(CreateGroupRequest(name="우리집"))

    updated = await service.update_me(UpdateGroupRequest(name="새 우리집"))

    assert updated.name == "새 우리집"


@pytest.mark.asyncio
async def test_non_owner_cannot_update_or_dissolve(db_session, test_user):
    owner_service = _service(test_user, db_session)
    group = await owner_service.create(CreateGroupRequest(name="우리집"))
    member = await _add_user(db_session, "member@example.com", "member")
    group_repo = GroupRepository(db_session)
    await group_repo.add_member(
        GroupMember(group_id=group.id, user_id=member.id, role=GroupRole.member)
    )
    member_service = _service(member, db_session)

    with pytest.raises(ForbiddenException):
        await member_service.update_me(UpdateGroupRequest(name="변경"))
    with pytest.raises(ForbiddenException):
        await member_service.dissolve()


@pytest.mark.asyncio
async def test_owner_cannot_leave(db_session, test_user):
    service = _service(test_user, db_session)
    await service.create(CreateGroupRequest(name="우리집"))

    with pytest.raises(BadRequestException) as exc:
        await service.leave()

    assert exc.value.code == ErrorCode.OWNER_CANNOT_LEAVE


@pytest.mark.asyncio
async def test_member_can_leave_and_owner_can_dissolve(db_session, test_user):
    owner_service = _service(test_user, db_session)
    group = await owner_service.create(CreateGroupRequest(name="우리집"))
    member = await _add_user(db_session, "member@example.com", "member")
    group_repo = GroupRepository(db_session)
    await group_repo.add_member(
        GroupMember(group_id=group.id, user_id=member.id, role=GroupRole.member)
    )

    await _service(member, db_session).leave()
    assert await group_repo.get_membership(member.id) is None

    await owner_service.dissolve()
    assert await group_repo.get_group(group.id) is None


@pytest.mark.asyncio
async def test_owner_can_kick_member(db_session, test_user):
    owner_service = _service(test_user, db_session)
    group = await owner_service.create(CreateGroupRequest(name="우리집"))
    member = await _add_user(db_session, "member@example.com", "member")
    group_repo = GroupRepository(db_session)
    await group_repo.add_member(
        GroupMember(group_id=group.id, user_id=member.id, role=GroupRole.member)
    )

    await owner_service.kick(member.id)

    assert await group_repo.get_membership(member.id) is None


@pytest.mark.asyncio
async def test_kick_rejects_owner_self_and_non_member_targets(db_session, test_user):
    owner_service = _service(test_user, db_session)
    await owner_service.create(CreateGroupRequest(name="우리집"))

    with pytest.raises(BadRequestException):
        await owner_service.kick(test_user.id)
    with pytest.raises(NotFoundException) as exc:
        await owner_service.kick(uuid.uuid4())

    assert exc.value.code == ErrorCode.GROUP_NOT_FOUND
