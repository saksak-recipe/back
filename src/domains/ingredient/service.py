import asyncio
from datetime import date, timedelta

from sqlalchemy import event
from sqlalchemy.orm import Session

from core.exception.exceptions import BadRequestException, IngredientNotFoundException
from domains.ai_recipe.cache import AiRecipeCache
from domains.ingredient.model import Ingredient
from domains.ingredient.repository import IngredientRepository
from domains.ingredient.schemas import (
    AddIngredientRequest,
    AddIngredientResponse,
    GetIngredientResponse,
    IngredientStatus,
    UpdateIngredientRequest,
)
from domains.user.model import User

SOON_WITHIN_DAYS = 3
_AI_RECIPE_INVALIDATION_PENDING = "ingredient_ai_recipe_invalidation_pending"

_STATUS_RANK: dict[IngredientStatus, int] = {
    "expired": 0,
    "soon": 1,
    "ok": 2,
    "unknown": 3,
}


def _ensure_expiration_valid(purchase_date: date, expiration_date: date | None) -> None:
    if expiration_date is not None and expiration_date < purchase_date:
        raise BadRequestException(detail="유통기한은 구매일 이후여야 합니다.")


def compute_status(
    expiration_date: date | None, today: date | None = None
) -> IngredientStatus:
    today = today or date.today()
    if expiration_date is None:
        return "unknown"
    if expiration_date < today:
        return "expired"
    if expiration_date <= today + timedelta(days=SOON_WITHIN_DAYS):
        return "soon"
    return "ok"


def _to_get_response(
    ingredient: Ingredient, today: date | None = None
) -> GetIngredientResponse:
    today = today or date.today()
    return GetIngredientResponse(
        id=ingredient.id,
        ingredient_name=ingredient.ingredient_name,
        purchase_date=ingredient.purchase_date,
        expiration_date=ingredient.expiration_date,
        status=compute_status(ingredient.expiration_date, today),
    )


def _to_add_response(
    ingredient: Ingredient, today: date | None = None
) -> AddIngredientResponse:
    today = today or date.today()
    return AddIngredientResponse(
        id=ingredient.id,
        ingredient_name=ingredient.ingredient_name,
        purchase_date=ingredient.purchase_date,
        expiration_date=ingredient.expiration_date,
        status=compute_status(ingredient.expiration_date, today),
    )


def _list_sort_key(ingredient: Ingredient, today: date) -> tuple:
    status = compute_status(ingredient.expiration_date, today)
    rank = _STATUS_RANK[status]
    if status == "unknown":
        created = ingredient.created_at
        ts = created.timestamp() if created is not None else 0.0
        return (rank, -ts)
    assert ingredient.expiration_date is not None
    return (rank, ingredient.expiration_date.toordinal())


class IngredientService:
    def __init__(
        self,
        user: User,
        ingredient_repo: IngredientRepository,
        list_cache: AiRecipeCache | None = None,
    ):
        self.user = user
        self.ingredient_repo = ingredient_repo
        self.list_cache = list_cache

    def _schedule_ai_recipe_list_invalidation(self) -> None:
        if self.list_cache is None:
            return

        sync_session = self.ingredient_repo.session.sync_session
        if sync_session.info.get(_AI_RECIPE_INVALIDATION_PENDING):
            return

        loop = asyncio.get_running_loop()
        list_cache = self.list_cache
        user_id = self.user.id
        cancelled = {"value": False}

        def invalidate_after_commit(session: Session) -> None:
            session.info.pop(_AI_RECIPE_INVALIDATION_PENDING, None)
            if cancelled["value"]:
                return
            loop.create_task(list_cache.invalidate_list(user_id))

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
        self._schedule_ai_recipe_list_invalidation()
        today = date.today()
        return [_to_add_response(item, today) for item in saved]

    async def get_ingredients(self) -> list[GetIngredientResponse]:
        ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
        today = date.today()
        sorted_items = sorted(ingredients, key=lambda item: _list_sort_key(item, today))
        return [_to_get_response(item, today) for item in sorted_items]

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

        self._schedule_ai_recipe_list_invalidation()
        return _to_get_response(ingredient)

    async def delete_ingredient(self, ingredient_id: int) -> None:
        deleted = await self.ingredient_repo.delete_ingredient(
            ingredient_id, self.user.id
        )
        if not deleted:
            raise IngredientNotFoundException()
        self._schedule_ai_recipe_list_invalidation()

    async def delete_all_ingredients(self) -> None:
        deleted = await self.ingredient_repo.delete_all_ingredients(self.user.id)
        if not deleted:
            raise IngredientNotFoundException(
                "삭제할 식재료가 존재하지 않거나 이미 비어있는 냉장고 입니다."
            )
        self._schedule_ai_recipe_list_invalidation()
