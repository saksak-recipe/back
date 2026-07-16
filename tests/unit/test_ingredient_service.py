from datetime import date
from unittest.mock import AsyncMock

import pytest
import uuid6

from core.exception.exceptions import IngredientNotFoundException
from domains.ingredient.model import Ingredient
from domains.ingredient.schemas import AddIngredientRequest
from domains.ingredient.service import IngredientService
from domains.user.model import User


@pytest.fixture
def ingredient_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def user() -> User:
    return User(
        id=uuid6.uuid7(),
        email="test@example.com",
        password="hashed",
        nickname="testuser",
    )


@pytest.fixture
def ingredient_service(user: User, ingredient_repo: AsyncMock) -> IngredientService:
    return IngredientService(user=user, ingredient_repo=ingredient_repo)


async def test_add_ingredients_returns_saved_items(
    ingredient_service: IngredientService, ingredient_repo: AsyncMock, user: User
):
    saved = [
        Ingredient(
            id=1,
            user_id=user.id,
            ingredient_name="양파",
            purchase_date=date.today(),
        ),
        Ingredient(
            id=2,
            user_id=user.id,
            ingredient_name="당근",
            purchase_date=date.today(),
        ),
    ]
    ingredient_repo.add_ingredient.return_value = saved

    result = await ingredient_service.add_ingredients(
        AddIngredientRequest(ingredients=["양파", "당근"])
    )

    assert len(result) == 2
    assert result[0].ingredient_name == "양파"
    assert result[1].ingredient_name == "당근"


async def test_get_ingredients_returns_user_items(
    ingredient_service: IngredientService, ingredient_repo: AsyncMock, user: User
):
    ingredient_repo.get_ingredients.return_value = [
        Ingredient(
            id=1,
            user_id=user.id,
            ingredient_name="양파",
            purchase_date=date.today(),
        )
    ]

    result = await ingredient_service.get_ingredients()

    assert len(result) == 1
    ingredient_repo.get_ingredients.assert_awaited_once_with(user.id)


async def test_delete_ingredient_raises_when_not_found(
    ingredient_service: IngredientService, ingredient_repo: AsyncMock
):
    ingredient_repo.delete_ingredient.return_value = False

    with pytest.raises(IngredientNotFoundException):
        await ingredient_service.delete_ingredient(999)


async def test_delete_all_ingredients_raises_when_empty(
    ingredient_service: IngredientService, ingredient_repo: AsyncMock
):
    ingredient_repo.delete_all_ingredients.return_value = False

    with pytest.raises(IngredientNotFoundException):
        await ingredient_service.delete_all_ingredients()


async def test_delete_all_ingredients_deletes_all(
    ingredient_service: IngredientService, ingredient_repo: AsyncMock, user: User
):
    ingredient_repo.delete_all_ingredients.return_value = True

    await ingredient_service.delete_all_ingredients()

    ingredient_repo.delete_all_ingredients.assert_awaited_once_with(user.id)
