from datetime import date, datetime, timezone

from core.exception.exceptions import ShoppingItemNotFoundException
from domains.ingredient.model import Ingredient
from domains.ingredient.repository import IngredientRepository
from domains.ingredient.schemas import AddIngredientResponse
from domains.ingredient.service import compute_status
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
    ):
        self.user = user
        self.shopping_repo = shopping_repo
        self.ingredient_repo = ingredient_repo

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
        deleted = await self.shopping_repo.delete_all(self.user.id)
        if not deleted:
            raise ShoppingItemNotFoundException()

    # get_db 요청 단위 트랜잭션으로 추가·삭제가 commit/rollback과 함께 원자적으로 처리됨
    async def to_ingredient(self, item_id: int) -> AddIngredientResponse:
        item = await self.shopping_repo.get_by_id(item_id, self.user.id)
        if item is None:
            raise ShoppingItemNotFoundException()

        ingredient = Ingredient(
            user_id=self.user.id,
            ingredient_name=item.name,
            purchase_date=date.today(),
            expiration_date=None,
        )
        saved = await self.ingredient_repo.add_ingredient([ingredient])
        deleted = await self.shopping_repo.delete_item(item_id, self.user.id)
        if not deleted:
            raise ShoppingItemNotFoundException()

        saved_ingredient = saved[0]
        return AddIngredientResponse(
            id=saved_ingredient.id,
            ingredient_name=saved_ingredient.ingredient_name,
            purchase_date=saved_ingredient.purchase_date,
            expiration_date=saved_ingredient.expiration_date,
            status=compute_status(saved_ingredient.expiration_date),
        )
