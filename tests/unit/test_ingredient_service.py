from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
import uuid6

from datetime import datetime, timezone

from core.exception.exceptions import BadRequestException, IngredientNotFoundException
from domains.ingredient.model import Ingredient
from domains.ingredient.repository import IngredientRepository
from domains.ingredient.schemas import AddIngredientRequest, UpdateIngredientRequest
from domains.ingredient.service import IngredientService, compute_status
from domains.user.model import User


@pytest.fixture
def ingredient_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def list_cache() -> AsyncMock:
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
def ingredient_service(
    user: User, ingredient_repo: AsyncMock, list_cache: AsyncMock
) -> IngredientService:
    return IngredientService(
        user=user,
        ingredient_repo=ingredient_repo,
        list_cache=list_cache,
    )


async def test_add_ingredients_returns_saved_items(
    ingredient_service: IngredientService,
    ingredient_repo: AsyncMock,
    list_cache: AsyncMock,
    user: User,
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
    assert result[0].status == "unknown"
    list_cache.invalidate_list.assert_awaited_once_with(user.id)


async def test_compute_status_boundaries():
    today = date.today()
    assert compute_status(None, today) == "unknown"
    assert compute_status(today - timedelta(days=1), today) == "expired"
    assert compute_status(today, today) == "soon"
    assert compute_status(today + timedelta(days=3), today) == "soon"
    assert compute_status(today + timedelta(days=4), today) == "ok"


async def test_add_ingredients_sets_expiration_date(
    ingredient_service: IngredientService, ingredient_repo: AsyncMock, user: User
):
    purchase = date.today()
    expiration = purchase + timedelta(days=5)
    saved = [
        Ingredient(
            id=1,
            user_id=user.id,
            ingredient_name="우유",
            purchase_date=purchase,
            expiration_date=expiration,
        )
    ]
    ingredient_repo.add_ingredient.return_value = saved

    result = await ingredient_service.add_ingredients(
        AddIngredientRequest(
            ingredients=["우유"],
            purchase_date=purchase,
            expiration_date=expiration,
        )
    )

    assert result[0].expiration_date == expiration
    assert result[0].status == "ok"
    created = ingredient_repo.add_ingredient.await_args.args[0]
    assert created[0].expiration_date == expiration


async def test_add_ingredients_rejects_invalid_expiration(
    ingredient_service: IngredientService,
):
    purchase = date.today()
    with pytest.raises(BadRequestException):
        await ingredient_service.add_ingredients(
            AddIngredientRequest(
                ingredients=["우유"],
                purchase_date=purchase,
                expiration_date=purchase - timedelta(days=1),
            )
        )


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
    assert result[0].status == "unknown"
    ingredient_repo.get_ingredients.assert_awaited_once_with(user.id)


async def test_get_ingredients_excludes_group_scoped_rows(db_session, test_user: User):
    personal = Ingredient(
        user_id=test_user.id,
        ingredient_name="개인 양파",
        purchase_date=date.today(),
    )
    group_scoped = Ingredient(
        user_id=test_user.id,
        group_id=uuid6.uuid7(),
        ingredient_name="그룹 양파",
        purchase_date=date.today(),
    )
    db_session.add_all([personal, group_scoped])
    await db_session.flush()

    result = await IngredientService(
        user=test_user, ingredient_repo=IngredientRepository(db_session)
    ).get_ingredients()

    assert [item.ingredient_name for item in result] == ["개인 양파"]


async def test_get_ingredients_sorts_by_status(
    ingredient_service: IngredientService, ingredient_repo: AsyncMock, user: User
):
    today = date.today()
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2026, 1, 2, tzinfo=timezone.utc)
    ingredient_repo.get_ingredients.return_value = [
        Ingredient(
            id=1,
            user_id=user.id,
            ingredient_name="여유",
            purchase_date=today,
            expiration_date=today + timedelta(days=4),
            created_at=older,
        ),
        Ingredient(
            id=2,
            user_id=user.id,
            ingredient_name="미설정새것",
            purchase_date=today,
            expiration_date=None,
            created_at=newer,
        ),
        Ingredient(
            id=3,
            user_id=user.id,
            ingredient_name="만료",
            purchase_date=today - timedelta(days=5),
            expiration_date=today - timedelta(days=1),
            created_at=older,
        ),
        Ingredient(
            id=4,
            user_id=user.id,
            ingredient_name="임박",
            purchase_date=today,
            expiration_date=today + timedelta(days=1),
            created_at=older,
        ),
        Ingredient(
            id=5,
            user_id=user.id,
            ingredient_name="미설정옛것",
            purchase_date=today,
            expiration_date=None,
            created_at=older,
        ),
    ]

    result = await ingredient_service.get_ingredients()

    assert [item.ingredient_name for item in result] == [
        "만료",
        "임박",
        "여유",
        "미설정새것",
        "미설정옛것",
    ]
    assert [item.status for item in result] == [
        "expired",
        "soon",
        "ok",
        "unknown",
        "unknown",
    ]


async def test_update_ingredient_partial_fields(
    ingredient_service: IngredientService,
    ingredient_repo: AsyncMock,
    list_cache: AsyncMock,
    user: User,
):
    existing = Ingredient(
        id=1,
        user_id=user.id,
        ingredient_name="양파",
        purchase_date=date.today(),
        expiration_date=None,
    )
    ingredient_repo.get_by_id.return_value = existing
    expiration = date.today() + timedelta(days=2)

    result = await ingredient_service.update_ingredient(
        1,
        UpdateIngredientRequest(
            ingredient_name="빨간양파",
            expiration_date=expiration,
        ),
    )

    assert result.ingredient_name == "빨간양파"
    assert result.expiration_date == expiration
    assert result.status == "soon"
    ingredient_repo.get_by_id.assert_awaited_once_with(1, user.id)
    list_cache.invalidate_list.assert_awaited_once_with(user.id)


async def test_update_ingredient_empty_patch_raises(
    ingredient_service: IngredientService,
):
    with pytest.raises(BadRequestException):
        await ingredient_service.update_ingredient(1, UpdateIngredientRequest())


async def test_update_ingredient_raises_when_not_found(
    ingredient_service: IngredientService, ingredient_repo: AsyncMock
):
    ingredient_repo.get_by_id.return_value = None

    with pytest.raises(IngredientNotFoundException):
        await ingredient_service.update_ingredient(
            999, UpdateIngredientRequest(ingredient_name="없는재료")
        )


async def test_delete_ingredient_raises_when_not_found(
    ingredient_service: IngredientService, ingredient_repo: AsyncMock
):
    ingredient_repo.delete_ingredient.return_value = False

    with pytest.raises(IngredientNotFoundException):
        await ingredient_service.delete_ingredient(999)


async def test_delete_ingredient_invalidates_list_cache(
    ingredient_service: IngredientService,
    ingredient_repo: AsyncMock,
    list_cache: AsyncMock,
    user: User,
):
    ingredient_repo.delete_ingredient.return_value = True

    await ingredient_service.delete_ingredient(1)

    list_cache.invalidate_list.assert_awaited_once_with(user.id)


async def test_delete_all_ingredients_raises_when_empty(
    ingredient_service: IngredientService, ingredient_repo: AsyncMock
):
    ingredient_repo.delete_all_ingredients.return_value = False

    with pytest.raises(IngredientNotFoundException):
        await ingredient_service.delete_all_ingredients()


async def test_delete_all_ingredients_deletes_all(
    ingredient_service: IngredientService,
    ingredient_repo: AsyncMock,
    list_cache: AsyncMock,
    user: User,
):
    ingredient_repo.delete_all_ingredients.return_value = True

    await ingredient_service.delete_all_ingredients()

    ingredient_repo.delete_all_ingredients.assert_awaited_once_with(user.id)
    list_cache.invalidate_list.assert_awaited_once_with(user.id)
