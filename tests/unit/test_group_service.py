import uuid

import pytest

from core.exception.codes import ErrorCode
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UserNotFoundException,
)
from domains.group.model import GroupMember, GroupRole, InviteStatus
from domains.group.repository import GroupRepository
from domains.group.schemas import (
    CreateGroupRequest,
    InviteByNicknameRequest,
    JoinByCodeRequest,
    UpdateGroupRequest,
)
from domains.group.service import GroupService
from domains.ingredient.schemas import AddIngredientRequest, UpdateIngredientRequest
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


@pytest.mark.asyncio
async def test_invite_by_nickname_is_idempotent_and_listed_for_invitee(
    db_session, test_user
):
    owner_service = _service(test_user, db_session)
    group = await owner_service.create(CreateGroupRequest(name="우리집"))
    invitee = await _add_user(db_session, "invitee@example.com", "invitee")

    first = await owner_service.invite_by_nickname(
        InviteByNicknameRequest(nickname=invitee.nickname)
    )
    second = await owner_service.invite_by_nickname(
        InviteByNicknameRequest(nickname=invitee.nickname)
    )
    invites = await _service(invitee, db_session).list_my_invites()

    assert first.id == second.id
    assert first.group_id == group.id
    assert first.group_name == "우리집"
    assert first.inviter_nickname == test_user.nickname
    assert first.status == InviteStatus.pending.value
    assert [invite.id for invite in invites] == [first.id]


@pytest.mark.asyncio
async def test_invite_rejects_self_and_unknown_nickname(db_session, test_user):
    service = _service(test_user, db_session)
    await service.create(CreateGroupRequest(name="우리집"))

    with pytest.raises(BadRequestException) as self_exc:
        await service.invite_by_nickname(
            InviteByNicknameRequest(nickname=test_user.nickname)
        )
    with pytest.raises(UserNotFoundException):
        await service.invite_by_nickname(InviteByNicknameRequest(nickname="missing"))

    assert self_exc.value.code == ErrorCode.INVALID_INVITE


@pytest.mark.asyncio
async def test_invitee_can_accept_pending_invite(db_session, test_user):
    owner_service = _service(test_user, db_session)
    group = await owner_service.create(CreateGroupRequest(name="우리집"))
    invitee = await _add_user(db_session, "invitee@example.com", "invitee")
    invite = await owner_service.invite_by_nickname(
        InviteByNicknameRequest(nickname=invitee.nickname)
    )

    accepted_group = await _service(invitee, db_session).accept_invite(invite.id)
    stored_invite = await GroupRepository(db_session).get_invite(invite.id)
    membership = await GroupRepository(db_session).get_membership(invitee.id)

    assert accepted_group.id == group.id
    assert membership is not None
    assert membership.role == GroupRole.member
    assert stored_invite is not None
    assert stored_invite.status == InviteStatus.accepted


@pytest.mark.asyncio
async def test_accept_invite_conflicts_when_invitee_is_already_in_group(
    db_session, test_user
):
    owner_service = _service(test_user, db_session)
    await owner_service.create(CreateGroupRequest(name="초대 그룹"))
    invitee = await _add_user(db_session, "invitee@example.com", "invitee")
    invite = await owner_service.invite_by_nickname(
        InviteByNicknameRequest(nickname=invitee.nickname)
    )
    await _service(invitee, db_session).create(CreateGroupRequest(name="다른 그룹"))

    with pytest.raises(ConflictException) as exc:
        await _service(invitee, db_session).accept_invite(invite.id)

    assert exc.value.code == ErrorCode.ALREADY_IN_GROUP


@pytest.mark.asyncio
async def test_invitee_can_reject_pending_invite(db_session, test_user):
    owner_service = _service(test_user, db_session)
    await owner_service.create(CreateGroupRequest(name="우리집"))
    invitee = await _add_user(db_session, "invitee@example.com", "invitee")
    invite = await owner_service.invite_by_nickname(
        InviteByNicknameRequest(nickname=invitee.nickname)
    )

    await _service(invitee, db_session).reject_invite(invite.id)

    stored_invite = await GroupRepository(db_session).get_invite(invite.id)
    assert stored_invite is not None
    assert stored_invite.status == InviteStatus.rejected
    assert await _service(invitee, db_session).list_my_invites() == []


@pytest.mark.asyncio
async def test_user_can_join_by_valid_code(db_session, test_user):
    owner_service = _service(test_user, db_session)
    group = await owner_service.create(CreateGroupRequest(name="우리집"))
    joiner = await _add_user(db_session, "joiner@example.com", "joiner")

    joined_group = await _service(joiner, db_session).join_by_code(
        JoinByCodeRequest(invite_code=group.invite_code)
    )

    membership = await GroupRepository(db_session).get_membership(joiner.id)
    assert joined_group.id == group.id
    assert membership is not None
    assert membership.role == GroupRole.member


@pytest.mark.asyncio
async def test_join_by_code_rejects_invalid_code_and_existing_membership(
    db_session, test_user
):
    service = _service(test_user, db_session)
    group = await service.create(CreateGroupRequest(name="우리집"))

    with pytest.raises(NotFoundException) as invalid_code_exc:
        await service.join_by_code(JoinByCodeRequest(invite_code="invalid"))
    with pytest.raises(ConflictException) as member_exc:
        await service.join_by_code(JoinByCodeRequest(invite_code=group.invite_code))

    assert invalid_code_exc.value.code == ErrorCode.INVITE_CODE_INVALID
    assert member_exc.value.code == ErrorCode.ALREADY_IN_GROUP


@pytest.mark.asyncio
async def test_owner_can_rotate_code_and_member_cannot(db_session, test_user):
    owner_service = _service(test_user, db_session)
    group = await owner_service.create(CreateGroupRequest(name="우리집"))
    member = await _add_user(db_session, "member@example.com", "member")
    await GroupRepository(db_session).add_member(
        GroupMember(group_id=group.id, user_id=member.id, role=GroupRole.member)
    )

    rotated_group = await owner_service.rotate_code()

    assert rotated_group.invite_code != group.invite_code
    assert len(rotated_group.invite_code) == 8
    with pytest.raises(ForbiddenException):
        await _service(member, db_session).rotate_code()


@pytest.mark.asyncio
async def test_group_member_can_manage_group_ingredients(db_session, test_user):
    service = _service(test_user, db_session)
    await service.create(CreateGroupRequest(name="우리집"))

    added = await service.add_ingredients(
        AddIngredientRequest(ingredients=["양파", "당근"])
    )
    listed = await service.list_ingredients()
    updated = await service.update_ingredient(
        added[0].id, UpdateIngredientRequest(ingredient_name="깐양파")
    )

    assert [item.ingredient_name for item in listed] == ["양파", "당근"]
    assert updated.ingredient_name == "깐양파"

    await service.delete_ingredient(added[1].id)
    await service.delete_all_ingredients()

    assert await service.list_ingredients() == []


@pytest.mark.asyncio
async def test_group_add_ingredients_rejects_conflict_without_partial_insert(
    db_session, test_user
):
    service = _service(test_user, db_session)
    await service.create(CreateGroupRequest(name="우리집"))
    await service.add_ingredients(AddIngredientRequest(ingredients=["양파"]))

    with pytest.raises(ConflictException) as exc:
        await service.add_ingredients(AddIngredientRequest(ingredients=["당근", "양파"]))

    assert exc.value.code == ErrorCode.INGREDIENT_NAME_CONFLICT
    assert [item.ingredient_name for item in await service.list_ingredients()] == ["양파"]
