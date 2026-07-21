from __future__ import annotations

import secrets
from typing import TYPE_CHECKING
from uuid import UUID

from core.exception.codes import ErrorCode
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from domains.group.model import Group, GroupMember, GroupRole
from domains.group.repository import GroupRepository
from domains.group.schemas import (
    CreateGroupRequest,
    GroupMemberResponse,
    GroupResponse,
    UpdateGroupRequest,
)
from domains.ingredient.repository import IngredientRepository
from domains.user.model import User
from domains.user.repository import UserRepository

if TYPE_CHECKING:
    from domains.shopping.repository import ShoppingRepository


class GroupService:
    def __init__(
        self,
        user: User,
        group_repo: GroupRepository,
        user_repo: UserRepository,
        ingredient_repo: IngredientRepository,
        shopping_repo: ShoppingRepository | None = None,
    ) -> None:
        self.user = user
        self.group_repo = group_repo
        self.user_repo = user_repo
        self.ingredient_repo = ingredient_repo
        self.shopping_repo = shopping_repo

    async def create(self, request: CreateGroupRequest) -> GroupResponse:
        if await self.group_repo.get_membership(self.user.id) is not None:
            raise ConflictException(
                code=ErrorCode.ALREADY_IN_GROUP,
                detail="이미 그룹에 가입되어 있습니다.",
            )

        group = await self.group_repo.add_group(
            Group(
                name=request.name,
                invite_code=secrets.token_hex(4),
                owner_id=self.user.id,
            )
        )
        await self.group_repo.add_member(
            GroupMember(
                group_id=group.id,
                user_id=self.user.id,
                role=GroupRole.owner,
            )
        )
        group_with_members = await self.group_repo.get_group_with_members(group.id)
        assert group_with_members is not None
        return await self._to_group_response(group_with_members)

    async def get_me(self) -> GroupResponse:
        _, group = await self._require_membership()
        return await self._to_group_response(group)

    async def update_me(self, request: UpdateGroupRequest) -> GroupResponse:
        _, group = await self._require_owner()
        group.name = request.name
        return await self._to_group_response(group)

    async def dissolve(self) -> None:
        _, group = await self._require_owner()
        await self.group_repo.delete_group(group)

    async def leave(self) -> None:
        membership, _ = await self._require_membership()
        if membership.role == GroupRole.owner:
            raise BadRequestException(
                code=ErrorCode.OWNER_CANNOT_LEAVE,
                detail="그룹 소유자는 그룹을 나갈 수 없습니다.",
            )
        await self.group_repo.delete_member(membership.group_id, self.user.id)

    async def kick(self, user_id: UUID) -> None:
        membership, _ = await self._require_owner()
        if user_id == self.user.id:
            raise BadRequestException(detail="자기 자신은 추방할 수 없습니다.")

        target_membership = await self.group_repo.get_membership(user_id)
        if (
            target_membership is None
            or target_membership.group_id != membership.group_id
        ):
            raise NotFoundException(
                code=ErrorCode.GROUP_NOT_FOUND,
                detail="그룹 멤버를 찾을 수 없습니다.",
            )
        if target_membership.role == GroupRole.owner:
            raise BadRequestException(detail="그룹 소유자는 추방할 수 없습니다.")

        await self.group_repo.delete_member(membership.group_id, user_id)

    async def _require_membership(self) -> tuple[GroupMember, Group]:
        membership = await self.group_repo.get_membership(self.user.id)
        if membership is None:
            raise NotFoundException(
                code=ErrorCode.GROUP_NOT_FOUND,
                detail="가입된 그룹을 찾을 수 없습니다.",
            )

        group = await self.group_repo.get_group_with_members(membership.group_id)
        if group is None:
            raise NotFoundException(
                code=ErrorCode.GROUP_NOT_FOUND,
                detail="그룹을 찾을 수 없습니다.",
            )
        return membership, group

    async def _require_owner(self) -> tuple[GroupMember, Group]:
        membership, group = await self._require_membership()
        if membership.role != GroupRole.owner:
            raise ForbiddenException(detail="그룹 소유자만 수행할 수 있습니다.")
        return membership, group

    async def _to_group_response(self, group: Group) -> GroupResponse:
        members = []
        for member in group.members:
            user = await self.user_repo.get_user_by_id(member.user_id)
            if user is None:
                continue
            members.append(
                GroupMemberResponse(
                    user_id=member.user_id,
                    nickname=user.nickname,
                    role=member.role.value,
                )
            )

        return GroupResponse(
            id=group.id,
            name=group.name,
            invite_code=group.invite_code,
            owner_id=group.owner_id,
            members=members,
            created_at=group.created_at,
        )
