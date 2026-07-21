from datetime import date

from core.exception.exceptions import BadRequestException, IngredientNotFoundException
from domains.ingredient.model import Ingredient
from domains.ingredient.repository import IngredientRepository
from domains.ingredient.schemas import (
    AddIngredientRequest,
    AddIngredientResponse,
    GetIngredientResponse,
    UpdateIngredientRequest,
)
from domains.user.model import User


def _ensure_expiration_valid(
    purchase_date: date, expiration_date: date | None
) -> None:
    if expiration_date is not None and expiration_date < purchase_date:
        raise BadRequestException(detail="유통기한은 구매일 이후여야 합니다.")


class IngredientService:
    def __init__(self, user: User, ingredient_repo: IngredientRepository):
        self.user = user
        self.ingredient_repo = ingredient_repo

    async def add_ingredients(
        self, request: AddIngredientRequest
    ) -> list[AddIngredientResponse]:
        _ensure_expiration_valid(request.purchase_date, request.expiration_date)
        ingredients = [
            Ingredient(
                user_id=self.user.id,
                ingredient_name=name,
                purchase_date=request.purchase_date,
                expiration_date=request.expiration_date,
            )
            for name in request.ingredients
        ]
        saved = await self.ingredient_repo.add_ingredient(ingredients)
        return [AddIngredientResponse.model_validate(item) for item in saved]

    async def get_ingredients(self) -> list[GetIngredientResponse]:
        ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
        return [GetIngredientResponse.model_validate(item) for item in ingredients]

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
            ingredient.ingredient_name = updates["ingredient_name"]
        if "purchase_date" in updates:
            ingredient.purchase_date = updates["purchase_date"]
        if "expiration_date" in updates:
            ingredient.expiration_date = updates["expiration_date"]

        _ensure_expiration_valid(ingredient.purchase_date, ingredient.expiration_date)

        return GetIngredientResponse.model_validate(ingredient)

    async def delete_ingredient(self, ingredient_id: int) -> None:
        deleted = await self.ingredient_repo.delete_ingredient(
            ingredient_id, self.user.id
        )
        if not deleted:
            raise IngredientNotFoundException()

    async def delete_all_ingredients(self) -> None:
        deleted = await self.ingredient_repo.delete_all_ingredients(self.user.id)
        if not deleted:
            raise IngredientNotFoundException(
                "삭제할 식재료가 존재하지 않거나 이미 비어있는 냉장고 입니다."
            )
