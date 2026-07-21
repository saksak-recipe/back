from __future__ import annotations

import asyncio
import secrets
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.orm import Session

from core.exception.codes import ErrorCode
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    IngredientNotFoundException,
    NotFoundException,
    ShoppingItemNotFoundException,
    UserNotFoundException,
)
from domains.ai_recipe.cache import AiRecipeCache
from domains.group.model import Group, GroupInvite, GroupMember, GroupRole, InviteStatus
from domains.group.repository import GroupRepository
from domains.group.schemas import (
    CreateGroupRequest,
    GroupInviteResponse,
    GroupMemberResponse,
    GroupResponse,
    InviteByNicknameRequest,
    JoinByCodeRequest,
    MergeRequest,
    MergeResponse,
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
from domains.ingredient.scope import RecipeScope
from domains.ingredient.service import (
    _ensure_expiration_valid,
    _list_sort_key,
    _to_add_response,
    _to_get_response,
)
from domains.shopping.model import ShoppingItem
from domains.shopping.repository import ShoppingRepository
from domains.shopping.schemas import (
    AddShoppingItemsRequest,
    ShoppingItemResponse,
    UpdateShoppingItemRequest,
)
from domains.user.model import User
from domains.user.repository import UserRepository

_AI_RECIPE_INVALIDATION_PENDING = "group_ai_recipe_invalidation_pending"


class GroupService:
    def __init__(
        self,
        user: User,
        group_repo: GroupRepository,
        user_repo: UserRepository,
        ingredient_repo: IngredientRepository,
        shopping_repo: ShoppingRepository,
        list_cache: AiRecipeCache | None = None,
    ) -> None:
        self.user = user
        self.group_repo = group_repo
        self.user_repo = user_repo
        self.ingredient_repo = ingredient_repo
        self.shopping_repo = shopping_repo
        self.list_cache = list_cache

    def _schedule_ai_recipe_list_invalidation(self, group_id: UUID) -> None:
        if self.list_cache is None:
            return

        sync_session = self.ingredient_repo.session.sync_session
        if sync_session.info.get(_AI_RECIPE_INVALIDATION_PENDING):
            return

        loop = asyncio.get_running_loop()
        list_cache = self.list_cache
        cancelled = {"value": False}

        def invalidate_after_commit(session: Session) -> None:
            session.info.pop(_AI_RECIPE_INVALIDATION_PENDING, None)
            if cancelled["value"]:
                return
            loop.create_task(
                list_cache.invalidate_list(group_id, scope=RecipeScope.group)
            )

        def cancel_on_rollback(session: Session) -> None:
            cancelled["value"] = True
            session.info.pop(_AI_RECIPE_INVALIDATION_PENDING, None)

        event.listen(
            sync_session,
            "after_commit",
            invalidate_after_commit,
            once=True,
        )
        event.listen(
            sync_session,
            "after_rollback",
            cancel_on_rollback,
            once=True,
        )
        sync_session.info[_AI_RECIPE_INVALIDATION_PENDING] = True

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

        seen: set[str] = set()
        for name in request.ingredients:
            if name in seen:
                raise ConflictException(
                    code=ErrorCode.INGREDIENT_NAME_CONFLICT,
                    detail="그룹에 동일한 이름의 식재료가 이미 존재합니다.",
                )
            seen.add(name)
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
        self._schedule_ai_recipe_list_invalidation(membership.group_id)

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

        if "ingredient_name" in updates:
            new_name = updates["ingredient_name"]
            existing = await self.ingredient_repo.find_name_in_group(
                membership.group_id, new_name
            )
            if existing is not None and existing.id != ingredient.id:
                raise ConflictException(
                    code=ErrorCode.INGREDIENT_NAME_CONFLICT,
                    detail="그룹에 동일한 이름의 식재료가 이미 존재합니다.",
                )

        for field, value in updates.items():
            setattr(ingredient, field, value)
        _ensure_expiration_valid(ingredient.purchase_date, ingredient.expiration_date)
        self._schedule_ai_recipe_list_invalidation(membership.group_id)
        return _to_get_response(ingredient)

    async def delete_ingredient(self, ingredient_id: int) -> None:
        membership, _ = await self._require_membership()
        deleted = await self.ingredient_repo.delete_in_group(
            ingredient_id, membership.group_id
        )
        if not deleted:
            raise IngredientNotFoundException()
        self._schedule_ai_recipe_list_invalidation(membership.group_id)

    async def delete_all_ingredients(self) -> None:
        membership, _ = await self._require_membership()
        await self.ingredient_repo.delete_all_in_group(membership.group_id)
        self._schedule_ai_recipe_list_invalidation(membership.group_id)

    async def list_shopping_items(self) -> list[ShoppingItemResponse]:
        membership, _ = await self._require_membership()
        items = await self.shopping_repo.list_by_group(membership.group_id)
        sorted_items = sorted(
            items,
            key=lambda item: (
                item.is_checked,
                item.created_at or datetime.min.replace(tzinfo=timezone.utc),
            ),
        )
        return [ShoppingItemResponse.model_validate(item) for item in sorted_items]

    async def add_shopping_items(
        self, request: AddShoppingItemsRequest
    ) -> list[ShoppingItemResponse]:
        membership, _ = await self._require_membership()
        unique_names = list(dict.fromkeys(request.names))
        existing = await self.shopping_repo.get_existing_names_in_group(
            membership.group_id, unique_names
        )
        items = [
            ShoppingItem(
                user_id=self.user.id,
                group_id=membership.group_id,
                name=name,
                is_checked=False,
            )
            for name in unique_names
            if name not in existing
        ]
        saved = await self.shopping_repo.add_items_in_group(items)
        return [ShoppingItemResponse.model_validate(item) for item in saved]

    async def update_shopping_item(
        self, item_id: int, request: UpdateShoppingItemRequest
    ) -> ShoppingItemResponse:
        membership, _ = await self._require_membership()
        item = await self.shopping_repo.get_by_id_in_group(
            item_id, membership.group_id
        )
        if item is None:
            raise ShoppingItemNotFoundException()
        item.is_checked = request.is_checked
        return ShoppingItemResponse.model_validate(item)

    async def delete_shopping_item(self, item_id: int) -> None:
        membership, _ = await self._require_membership()
        deleted = await self.shopping_repo.delete_in_group(item_id, membership.group_id)
        if not deleted:
            raise ShoppingItemNotFoundException()

    async def delete_all_shopping_items(self) -> None:
        membership, _ = await self._require_membership()
        await self.shopping_repo.delete_all_in_group(membership.group_id)

    async def shopping_to_ingredient(self, item_id: int) -> AddIngredientResponse:
        membership, _ = await self._require_membership()
        item = await self.shopping_repo.get_by_id_in_group(item_id, membership.group_id)
        if item is None:
            raise ShoppingItemNotFoundException()
        if (
            await self.ingredient_repo.find_name_in_group(
                membership.group_id, item.name
            )
            is not None
        ):
            raise ConflictException(
                code=ErrorCode.INGREDIENT_NAME_CONFLICT,
                detail="그룹에 동일한 이름의 식재료가 이미 존재합니다.",
            )

        saved = await self.ingredient_repo.add_ingredient(
            [
                Ingredient(
                    user_id=self.user.id,
                    group_id=membership.group_id,
                    ingredient_name=item.name,
                    purchase_date=date.today(),
                    expiration_date=None,
                )
            ]
        )
        deleted = await self.shopping_repo.delete_in_group(item_id, membership.group_id)
        if not deleted:
            raise ShoppingItemNotFoundException()
        self._schedule_ai_recipe_list_invalidation(membership.group_id)
        return _to_add_response(saved[0])

    async def merge(self, request: MergeRequest) -> MergeResponse:
        membership, _ = await self._require_membership()

        personal_ingredients: list[Ingredient] = []
        for ingredient_id in request.ingredients:
            ingredient = await self.ingredient_repo.get_by_id(
                ingredient_id, self.user.id
            )
            if ingredient is None:
                raise IngredientNotFoundException()
            personal_ingredients.append(ingredient)

        personal_shopping_items: list[ShoppingItem] = []
        for item_id in request.shopping_items:
            item = await self.shopping_repo.get_by_id(item_id, self.user.id)
            if item is None:
                raise ShoppingItemNotFoundException()
            personal_shopping_items.append(item)

        created_ingredients: list[GetIngredientResponse] = []
        created_shopping_items: list[ShoppingItemResponse] = []
        skipped_ingredient_ids: list[int] = []
        skipped_shopping_item_ids: list[int] = []
        deleted_ingredient_ids: list[int] = []
        deleted_shopping_item_ids: list[int] = []

        for ingredient in personal_ingredients:
            if (
                await self.ingredient_repo.find_name_in_group(
                    membership.group_id, ingredient.ingredient_name
                )
                is not None
            ):
                skipped_ingredient_ids.append(ingredient.id)
                continue

            saved = await self.ingredient_repo.add_ingredient(
                [
                    Ingredient(
                        user_id=self.user.id,
                        group_id=membership.group_id,
                        ingredient_name=ingredient.ingredient_name,
                        purchase_date=ingredient.purchase_date,
                        expiration_date=ingredient.expiration_date,
                    )
                ]
            )
            created_ingredients.append(_to_get_response(saved[0]))
            if request.mode == "move":
                await self.ingredient_repo.delete_ingredient(ingredient.id, self.user.id)
                deleted_ingredient_ids.append(ingredient.id)

        for item in personal_shopping_items:
            if (
                item.name
                in await self.shopping_repo.get_existing_names_in_group(
                    membership.group_id, [item.name]
                )
            ):
                skipped_shopping_item_ids.append(item.id)
                continue

            saved = await self.shopping_repo.add_items_in_group(
                [
                    ShoppingItem(
                        user_id=self.user.id,
                        group_id=membership.group_id,
                        name=item.name,
                        is_checked=item.is_checked,
                    )
                ]
            )
            created_shopping_items.append(ShoppingItemResponse.model_validate(saved[0]))
            if request.mode == "move":
                await self.shopping_repo.delete_item(item.id, self.user.id)
                deleted_shopping_item_ids.append(item.id)

        if created_ingredients:
            self._schedule_ai_recipe_list_invalidation(membership.group_id)

        return MergeResponse(
            created_ingredients=created_ingredients,
            created_shopping_items=created_shopping_items,
            skipped_ingredient_ids=skipped_ingredient_ids,
            skipped_shopping_item_ids=skipped_shopping_item_ids,
            deleted_ingredient_ids=deleted_ingredient_ids,
            deleted_shopping_item_ids=deleted_shopping_item_ids,
        )

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
