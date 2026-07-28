from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from core.exception.codes import ErrorCode
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    IngredientNotFoundException,
)
from domains.ingredient.mappers import (
    SOON_WITHIN_DAYS,
    _STATUS_RANK,
    compute_status,
    ensure_expiration_valid,
    list_sort_key,
    to_add_response,
    to_get_response,
)
from domains.ingredient.model import Ingredient
from domains.ingredient.repository import IngredientRepository
from domains.ingredient.schemas import (
    AddIngredientRequest,
    AddIngredientResponse,
    GetIngredientResponse,
    UpdateIngredientRequest,
)
from domains.user.model import User

if TYPE_CHECKING:
    from domains.ingredient_shelf_life.service import IngredientShelfLifeService
    from domains.notification.service import NotificationService

# Backwards-compatible re-exports / aliases
_ensure_expiration_valid = ensure_expiration_valid
_to_get_response = to_get_response
_to_add_response = to_add_response
_list_sort_key = list_sort_key

__all__ = [
    "SOON_WITHIN_DAYS",
    "_STATUS_RANK",
    "IngredientService",
    "compute_status",
    "ensure_expiration_valid",
    "list_sort_key",
    "to_add_response",
    "to_get_response",
    "_ensure_expiration_valid",
    "_list_sort_key",
    "_to_add_response",
    "_to_get_response",
]


class IngredientService:
    def __init__(
        self,
        user: User,
        ingredient_repo: IngredientRepository,
        shelf_life_service: IngredientShelfLifeService,
        notification_service: NotificationService,
    ):
        self.user = user
        self.ingredient_repo = ingredient_repo
        self.shelf_life_service = shelf_life_service
        self.notification_service = notification_service

    async def add_ingredients(
        self, request: AddIngredientRequest
    ) -> list[AddIngredientResponse]:
        ensure_expiration_valid(request.purchase_date, request.expiration_date)
        await self._ensure_names_available(request.ingredients)
        expirations = await self.shelf_life_service.resolve_expirations_on_add(
            names=request.ingredients,
            purchase_date=request.purchase_date,
            expiration_date=request.expiration_date,
            user_id=self.user.id,
        )
        ingredients = [
            Ingredient(
                user_id=self.user.id,
                ingredient_name=name,
                purchase_date=request.purchase_date,
                expiration_date=expiration,
            )
            for name, expiration in zip(request.ingredients, expirations, strict=True)
        ]
        saved = await self.ingredient_repo.add_ingredient(ingredients)
        today = date.today()
        return [to_add_response(item, today) for item in saved]

    async def get_ingredients(self) -> list[GetIngredientResponse]:
        ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
        today = date.today()
        sorted_items = sorted(ingredients, key=lambda item: list_sort_key(item, today))
        return [to_get_response(item, today) for item in sorted_items]

    async def update_ingredient(
        self, ingredient_id: int, request: UpdateIngredientRequest
    ) -> GetIngredientResponse:
        updates = request.model_dump(exclude_unset=True)
        if not updates:
            raise BadRequestException(detail="수정할 필드가 없습니다.")

        ingredient = await self.ingredient_repo.get_by_id(ingredient_id, self.user.id)
        if ingredient is None:
            raise IngredientNotFoundException()

        if "ingredient_name" in updates:
            new_name = updates["ingredient_name"]
            existing = await self.ingredient_repo.find_name_for_user(
                self.user.id, new_name
            )
            if existing is not None and existing.id != ingredient.id:
                raise ConflictException(
                    code=ErrorCode.INGREDIENT_NAME_CONFLICT,
                    detail="동일한 이름의 식재료가 이미 존재합니다.",
                )
            ingredient.ingredient_name = new_name
        if "purchase_date" in updates:
            ingredient.purchase_date = updates["purchase_date"]
        if "expiration_date" in updates:
            ingredient.expiration_date = updates["expiration_date"]

        ensure_expiration_valid(ingredient.purchase_date, ingredient.expiration_date)

        return to_get_response(ingredient)

    async def delete_ingredient(self, ingredient_id: int) -> None:
        deleted = await self.ingredient_repo.delete_ingredient(
            ingredient_id, self.user.id
        )
        if not deleted:
            raise IngredientNotFoundException()
        await self.notification_service.delete_expiry_for_ingredient(ingredient_id)

    async def delete_all_ingredients(self) -> None:
        ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
        await self.ingredient_repo.delete_all_ingredients(self.user.id)
        if ingredients:
            await self.notification_service.delete_expiry_for_ingredients(
                [item.id for item in ingredients]
            )

    async def list_for_group(self, group_id: UUID) -> list[GetIngredientResponse]:
        ingredients = await self.ingredient_repo.list_by_group(group_id)
        today = date.today()
        sorted_items = sorted(ingredients, key=lambda item: list_sort_key(item, today))
        return [to_get_response(item, today) for item in sorted_items]

    async def add_for_group(
        self, group_id: UUID, request: AddIngredientRequest
    ) -> list[AddIngredientResponse]:
        ensure_expiration_valid(request.purchase_date, request.expiration_date)

        seen: set[str] = set()
        for name in request.ingredients:
            if name in seen:
                raise ConflictException(
                    code=ErrorCode.INGREDIENT_NAME_CONFLICT,
                    detail="그룹에 동일한 이름의 식재료가 이미 존재합니다.",
                )
            seen.add(name)
            if await self.ingredient_repo.find_name_in_group(group_id, name) is not None:
                raise ConflictException(
                    code=ErrorCode.INGREDIENT_NAME_CONFLICT,
                    detail="그룹에 동일한 이름의 식재료가 이미 존재합니다.",
                )

        expirations = await self.shelf_life_service.resolve_expirations_on_add(
            names=request.ingredients,
            purchase_date=request.purchase_date,
            expiration_date=request.expiration_date,
            user_id=self.user.id,
        )
        ingredients = [
            Ingredient(
                user_id=self.user.id,
                group_id=group_id,
                ingredient_name=name,
                purchase_date=request.purchase_date,
                expiration_date=expiration,
            )
            for name, expiration in zip(request.ingredients, expirations, strict=True)
        ]
        saved = await self.ingredient_repo.add_ingredient(ingredients)

        today = date.today()
        return [to_add_response(item, today) for item in saved]

    async def update_for_group(
        self,
        group_id: UUID,
        ingredient_id: int,
        request: UpdateIngredientRequest,
    ) -> GetIngredientResponse:
        updates = request.model_dump(exclude_unset=True)
        if not updates:
            raise BadRequestException(detail="수정할 필드가 없습니다.")

        ingredient = await self.ingredient_repo.get_by_id_in_group(
            ingredient_id, group_id
        )
        if ingredient is None:
            raise IngredientNotFoundException()

        if "ingredient_name" in updates:
            new_name = updates["ingredient_name"]
            existing = await self.ingredient_repo.find_name_in_group(group_id, new_name)
            if existing is not None and existing.id != ingredient.id:
                raise ConflictException(
                    code=ErrorCode.INGREDIENT_NAME_CONFLICT,
                    detail="그룹에 동일한 이름의 식재료가 이미 존재합니다.",
                )

        for field, value in updates.items():
            setattr(ingredient, field, value)
        ensure_expiration_valid(ingredient.purchase_date, ingredient.expiration_date)
        return to_get_response(ingredient)

    async def delete_for_group(self, group_id: UUID, ingredient_id: int) -> None:
        deleted = await self.ingredient_repo.delete_in_group(ingredient_id, group_id)
        if not deleted:
            raise IngredientNotFoundException()
        await self.notification_service.delete_expiry_for_ingredient(ingredient_id)

    async def delete_all_for_group(self, group_id: UUID) -> None:
        ingredients = await self.ingredient_repo.list_by_group(group_id)
        await self.ingredient_repo.delete_all_in_group(group_id)
        if ingredients:
            await self.notification_service.delete_expiry_for_ingredients(
                [item.id for item in ingredients]
            )

    async def _ensure_names_available(self, names: list[str]) -> None:
        seen: set[str] = set()
        for name in names:
            if name in seen:
                raise ConflictException(
                    code=ErrorCode.INGREDIENT_NAME_CONFLICT,
                    detail="동일한 이름의 식재료가 이미 존재합니다.",
                )
            seen.add(name)
            if await self.ingredient_repo.find_name_for_user(self.user.id, name) is not None:
                raise ConflictException(
                    code=ErrorCode.INGREDIENT_NAME_CONFLICT,
                    detail="동일한 이름의 식재료가 이미 존재합니다.",
                )
