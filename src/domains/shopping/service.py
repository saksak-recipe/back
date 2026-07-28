from datetime import date, datetime, timezone
from uuid import UUID

from core.exception.codes import ErrorCode
from core.exception.exceptions import ConflictException, ShoppingItemNotFoundException
from domains.ingredient.mappers import to_add_response
from domains.ingredient.model import Ingredient
from domains.ingredient.repository import IngredientRepository
from domains.ingredient.schemas import AddIngredientResponse
from domains.ingredient_shelf_life.service import IngredientShelfLifeService
from domains.shopping.model import ShoppingItem
from domains.shopping.repository import ShoppingRepository
from domains.shopping.schemas import (
    AddShoppingItemsRequest,
    ShoppingItemResponse,
    UpdateShoppingItemRequest,
)
from domains.user.model import User


class ShoppingService:
    def __init__(
        self,
        user: User,
        shopping_repo: ShoppingRepository,
        ingredient_repo: IngredientRepository,
        shelf_life_service: IngredientShelfLifeService,
    ):
        self.user = user
        self.shopping_repo = shopping_repo
        self.ingredient_repo = ingredient_repo
        self.shelf_life_service = shelf_life_service

    async def add_items(
        self, request: AddShoppingItemsRequest
    ) -> list[ShoppingItemResponse]:
        unique_names = list(dict.fromkeys(request.names))
        existing = await self.shopping_repo.get_existing_names(
            self.user.id, unique_names
        )
        to_create = [name for name in unique_names if name not in existing]
        if not to_create:
            return []

        items = [
            ShoppingItem(user_id=self.user.id, name=name, is_checked=False)
            for name in to_create
        ]
        saved = await self.shopping_repo.add_items(items)
        return [ShoppingItemResponse.model_validate(item) for item in saved]

    async def list_items(self) -> list[ShoppingItemResponse]:
        items = await self.shopping_repo.list_by_user(self.user.id)
        sorted_items = sorted(
            items,
            key=lambda item: (
                item.is_checked,
                item.created_at or datetime.min.replace(tzinfo=timezone.utc),
            ),
        )
        return [ShoppingItemResponse.model_validate(item) for item in sorted_items]

    async def update_item(
        self, item_id: int, request: UpdateShoppingItemRequest
    ) -> ShoppingItemResponse:
        item = await self.shopping_repo.get_by_id(item_id, self.user.id)
        if item is None:
            raise ShoppingItemNotFoundException()

        item.is_checked = request.is_checked
        return ShoppingItemResponse.model_validate(item)

    async def delete_item(self, item_id: int) -> None:
        deleted = await self.shopping_repo.delete_item(item_id, self.user.id)
        if not deleted:
            raise ShoppingItemNotFoundException()

    async def delete_all(self) -> None:
        await self.shopping_repo.delete_all(self.user.id)

    # get_db 요청 단위 트랜잭션으로 추가·삭제가 commit/rollback과 함께 원자적으로 처리됨
    async def to_ingredient(self, item_id: int) -> AddIngredientResponse:
        item = await self.shopping_repo.get_by_id(item_id, self.user.id)
        if item is None:
            raise ShoppingItemNotFoundException()

        if (
            await self.ingredient_repo.find_name_for_user(self.user.id, item.name)
            is not None
        ):
            raise ConflictException(
                code=ErrorCode.INGREDIENT_NAME_CONFLICT,
                detail="동일한 이름의 식재료가 이미 존재합니다.",
            )

        purchase_date = date.today()
        expirations = await self.shelf_life_service.resolve_expirations_on_add(
            names=[item.name],
            purchase_date=purchase_date,
            expiration_date=None,
            user_id=self.user.id,
        )
        ingredient = Ingredient(
            user_id=self.user.id,
            ingredient_name=item.name,
            purchase_date=purchase_date,
            expiration_date=expirations[0],
        )
        saved = await self.ingredient_repo.add_ingredient([ingredient])
        deleted = await self.shopping_repo.delete_item(item_id, self.user.id)
        if not deleted:
            raise ShoppingItemNotFoundException()

        return to_add_response(saved[0])

    async def list_for_group(self, group_id: UUID) -> list[ShoppingItemResponse]:
        items = await self.shopping_repo.list_by_group(group_id)
        sorted_items = sorted(
            items,
            key=lambda item: (
                item.is_checked,
                item.created_at or datetime.min.replace(tzinfo=timezone.utc),
            ),
        )
        return [ShoppingItemResponse.model_validate(item) for item in sorted_items]

    async def add_for_group(
        self, group_id: UUID, request: AddShoppingItemsRequest
    ) -> list[ShoppingItemResponse]:
        unique_names = list(dict.fromkeys(request.names))
        existing = await self.shopping_repo.get_existing_names_in_group(
            group_id, unique_names
        )
        items = [
            ShoppingItem(
                user_id=self.user.id,
                group_id=group_id,
                name=name,
                is_checked=False,
            )
            for name in unique_names
            if name not in existing
        ]
        saved = await self.shopping_repo.add_items_in_group(items)
        return [ShoppingItemResponse.model_validate(item) for item in saved]

    async def update_for_group(
        self, group_id: UUID, item_id: int, request: UpdateShoppingItemRequest
    ) -> ShoppingItemResponse:
        item = await self.shopping_repo.get_by_id_in_group(item_id, group_id)
        if item is None:
            raise ShoppingItemNotFoundException()
        item.is_checked = request.is_checked
        return ShoppingItemResponse.model_validate(item)

    async def delete_for_group(self, group_id: UUID, item_id: int) -> None:
        deleted = await self.shopping_repo.delete_in_group(item_id, group_id)
        if not deleted:
            raise ShoppingItemNotFoundException()

    async def delete_all_for_group(self, group_id: UUID) -> None:
        await self.shopping_repo.delete_all_in_group(group_id)

    async def to_ingredient_for_group(
        self, group_id: UUID, item_id: int
    ) -> AddIngredientResponse:
        item = await self.shopping_repo.get_by_id_in_group(item_id, group_id)
        if item is None:
            raise ShoppingItemNotFoundException()
        if await self.ingredient_repo.find_name_in_group(group_id, item.name) is not None:
            raise ConflictException(
                code=ErrorCode.INGREDIENT_NAME_CONFLICT,
                detail="그룹에 동일한 이름의 식재료가 이미 존재합니다.",
            )

        purchase_date = date.today()
        expirations = await self.shelf_life_service.resolve_expirations_on_add(
            names=[item.name],
            purchase_date=purchase_date,
            expiration_date=None,
            user_id=self.user.id,
        )
        saved = await self.ingredient_repo.add_ingredient(
            [
                Ingredient(
                    user_id=self.user.id,
                    group_id=group_id,
                    ingredient_name=item.name,
                    purchase_date=purchase_date,
                    expiration_date=expirations[0],
                )
            ]
        )
        deleted = await self.shopping_repo.delete_in_group(item_id, group_id)
        if not deleted:
            raise ShoppingItemNotFoundException()
        return to_add_response(saved[0])
