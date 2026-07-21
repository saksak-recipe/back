from __future__ import annotations

import secrets
from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from core.exception.codes import ErrorCode
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    IngredientNotFoundException,
    NotFoundException,
    UserNotFoundException,
)
from domains.group.model import Group, GroupInvite, GroupMember, GroupRole, InviteStatus
from domains.group.repository import GroupRepository
from domains.group.schemas import (
    CreateGroupRequest,
    GroupInviteResponse,
    GroupMemberResponse,
    GroupResponse,
    InviteByNicknameRequest,
    JoinByCodeRequest,
    UpdateGroupRequest,
)
from domains.ingredient.repository import IngredientRepository
from domains.ingredient.model import Ingredient
from domains.ingredient.schemas import (
    AddIngredientRequest,
    AddIngredientResponse,
    GetIngredientResponse,
    UpdateIngredientRequest,
)
from domains.ingredient.service import (
    _ensure_expiration_valid,
    _list_sort_key,
    _to_add_response,
    _to_get_response,
)
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

    async def invite_by_nickname(
        self, request: InviteByNicknameRequest
    ) -> GroupInviteResponse:
        _, group = await self._require_membership()
        invitee = await self.user_repo.get_user_by_nickname(request.nickname)
        if invitee is None:
            raise UserNotFoundException()
        if invitee.id == self.user.id:
            raise BadRequestException(
                code=ErrorCode.INVALID_INVITE,
                detail="자기 자신을 초대할 수 없습니다.",
            )

        invite = await self.group_repo.find_pending_invite(group.id, invitee.id)
        if invite is None:
            invite = await self.group_repo.add_invite(
                GroupInvite(
                    group_id=group.id,
                    inviter_id=self.user.id,
                    invitee_id=invitee.id,
                )
            )
        return await self._to_invite_response(invite)

    async def list_my_invites(self) -> list[GroupInviteResponse]:
        invites = await self.group_repo.list_pending_for_invitee(self.user.id)
        return [await self._to_invite_response(invite) for invite in invites]

    async def accept_invite(self, invite_id: UUID) -> GroupResponse:
        invite = await self._require_pending_invite_for_current_user(invite_id)
        if await self.group_repo.get_membership(self.user.id) is not None:
            raise ConflictException(
                code=ErrorCode.ALREADY_IN_GROUP,
                detail="이미 그룹에 가입되어 있습니다.",
            )

        group = await self.group_repo.get_group_with_members(invite.group_id)
        if group is None:
            raise NotFoundException(
                code=ErrorCode.GROUP_NOT_FOUND,
                detail="초대 그룹을 찾을 수 없습니다.",
            )

        await self.group_repo.add_member(
            GroupMember(
                group_id=group.id,
                user_id=self.user.id,
                role=GroupRole.member,
            )
        )
        invite.status = InviteStatus.accepted
        await self.group_repo.session.flush()

        group = await self.group_repo.get_group_with_members(group.id)
        assert group is not None
        return await self._to_group_response(group)

    async def reject_invite(self, invite_id: UUID) -> None:
        invite = await self._require_pending_invite_for_current_user(invite_id)
        invite.status = InviteStatus.rejected
        await self.group_repo.session.flush()

    async def join_by_code(self, request: JoinByCodeRequest) -> GroupResponse:
        group = await self.group_repo.get_by_invite_code(request.invite_code)
        if group is None:
            raise NotFoundException(
                code=ErrorCode.INVITE_CODE_INVALID,
                detail="유효하지 않은 초대 코드입니다.",
            )
        if await self.group_repo.get_membership(self.user.id) is not None:
            raise ConflictException(
                code=ErrorCode.ALREADY_IN_GROUP,
                detail="이미 그룹에 가입되어 있습니다.",
            )

        await self.group_repo.add_member(
            GroupMember(
                group_id=group.id,
                user_id=self.user.id,
                role=GroupRole.member,
            )
        )
        group = await self.group_repo.get_group_with_members(group.id)
        assert group is not None
        return await self._to_group_response(group)

    async def rotate_code(self) -> GroupResponse:
        _, group = await self._require_owner()
        group.invite_code = secrets.token_hex(4)
        return await self._to_group_response(group)

    async def list_ingredients(self) -> list[GetIngredientResponse]:
        membership, _ = await self._require_membership()
        ingredients = await self.ingredient_repo.list_by_group(membership.group_id)

        today = date.today()
        sorted_items = sorted(ingredients, key=lambda item: _list_sort_key(item, today))
        return [_to_get_response(item, today) for item in sorted_items]

    async def add_ingredients(
        self, request: AddIngredientRequest
    ) -> list[AddIngredientResponse]:
        membership, _ = await self._require_membership()
        _ensure_expiration_valid(request.purchase_date, request.expiration_date)

        for name in request.ingredients:
            if (
                await self.ingredient_repo.find_name_in_group(membership.group_id, name)
                is not None
            ):
                raise ConflictException(
                    code=ErrorCode.INGREDIENT_NAME_CONFLICT,
                    detail="그룹에 동일한 이름의 식재료가 이미 존재합니다.",
                )

        ingredients = [
            Ingredient(
                user_id=self.user.id,
                group_id=membership.group_id,
                ingredient_name=name,
                purchase_date=request.purchase_date,
                expiration_date=request.expiration_date,
            )
            for name in request.ingredients
        ]
        saved = await self.ingredient_repo.add_ingredient(ingredients)

        today = date.today()
        return [_to_add_response(item, today) for item in saved]

    async def update_ingredient(
        self, ingredient_id: int, request: UpdateIngredientRequest
    ) -> GetIngredientResponse:
        updates = request.model_dump(exclude_unset=True)
        if not updates:
            raise BadRequestException(detail="수정할 필드가 없습니다.")

        membership, _ = await self._require_membership()
        ingredient = await self.ingredient_repo.get_by_id_in_group(
            ingredient_id, membership.group_id
        )
        if ingredient is None:
            raise IngredientNotFoundException()

        for field, value in updates.items():
            setattr(ingredient, field, value)
        _ensure_expiration_valid(ingredient.purchase_date, ingredient.expiration_date)
        return _to_get_response(ingredient)

    async def delete_ingredient(self, ingredient_id: int) -> None:
        membership, _ = await self._require_membership()
        deleted = await self.ingredient_repo.delete_in_group(
            ingredient_id, membership.group_id
        )
        if not deleted:
            raise IngredientNotFoundException()

    async def delete_all_ingredients(self) -> None:
        membership, _ = await self._require_membership()
        await self.ingredient_repo.delete_all_in_group(membership.group_id)

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

    async def _require_pending_invite_for_current_user(
        self, invite_id: UUID
    ) -> GroupInvite:
        invite = await self.group_repo.get_invite(invite_id)
        if (
            invite is None
            or invite.invitee_id != self.user.id
            or invite.status != InviteStatus.pending
        ):
            raise NotFoundException(
                code=ErrorCode.INVALID_INVITE,
                detail="처리할 수 있는 초대를 찾을 수 없습니다.",
            )
        return invite

    async def _to_invite_response(self, invite: GroupInvite) -> GroupInviteResponse:
        group = await self.group_repo.get_group(invite.group_id)
        inviter = await self.user_repo.get_user_by_id(invite.inviter_id)
        assert group is not None
        assert inviter is not None
        return GroupInviteResponse(
            id=invite.id,
            group_id=group.id,
            group_name=group.name,
            inviter_nickname=inviter.nickname,
            status=invite.status.value,
            created_at=invite.created_at,
        )

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
