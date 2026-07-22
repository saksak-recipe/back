from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
import uuid6
from sqlalchemy import select

from domains.ingredient.repository import IngredientRepository
from domains.ingredient.schemas import AddIngredientRequest
from domains.ingredient.service import IngredientService
from domains.ingredient_shelf_life.model import (
    IngredientShelfLife,
    IngredientShelfLifeLog,
)
from domains.ingredient_shelf_life.repository import IngredientShelfLifeRepository
from domains.ingredient_shelf_life.service import IngredientShelfLifeService
from domains.shopping.model import ShoppingItem
from domains.shopping.repository import ShoppingRepository
from domains.shopping.service import ShoppingService
from domains.user.model import User


@pytest.fixture
def shelf_life_service(db_session) -> IngredientShelfLifeService:
    return IngredientShelfLifeService(
        repo=IngredientShelfLifeRepository(db_session)
    )


async def _add_master(
    db_session, name: str, days: int
) -> IngredientShelfLife:
    row = IngredientShelfLife(ingredient_name=name, shelf_life_days=days)
    db_session.add(row)
    await db_session.flush()
    return row


async def test_autofill_when_master_hit_and_expiration_none(
    db_session,
    test_user: User,
    shelf_life_service: IngredientShelfLifeService,
):
    await _add_master(db_session, "우유", 7)
    purchase = date.today()
    service = IngredientService(
        user=test_user,
        ingredient_repo=IngredientRepository(db_session),
        shelf_life_service=shelf_life_service,
    )

    result = await service.add_ingredients(
        AddIngredientRequest(
            ingredients=["우유"],
            purchase_date=purchase,
            expiration_date=None,
        )
    )

    assert result[0].expiration_date == purchase + timedelta(days=7)
    logs = (
        await db_session.execute(select(IngredientShelfLifeLog))
    ).scalars().all()
    assert logs == []


async def test_missing_log_when_master_miss_and_expiration_none(
    db_session,
    test_user: User,
    shelf_life_service: IngredientShelfLifeService,
):
    service = IngredientService(
        user=test_user,
        ingredient_repo=IngredientRepository(db_session),
        shelf_life_service=shelf_life_service,
    )

    result = await service.add_ingredients(
        AddIngredientRequest(ingredients=["미등록재료"], expiration_date=None)
    )

    assert result[0].expiration_date is None
    logs = (
        await db_session.execute(select(IngredientShelfLifeLog))
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].log_type == "missing"
    assert logs[0].ingredient_name == "미등록재료"
    assert logs[0].user_id == test_user.id


async def test_deviation_log_when_user_days_differ(
    db_session,
    test_user: User,
    shelf_life_service: IngredientShelfLifeService,
):
    await _add_master(db_session, "우유", 7)
    purchase = date.today()
    user_expiration = purchase + timedelta(days=3)
    service = IngredientService(
        user=test_user,
        ingredient_repo=IngredientRepository(db_session),
        shelf_life_service=shelf_life_service,
    )

    result = await service.add_ingredients(
        AddIngredientRequest(
            ingredients=["우유"],
            purchase_date=purchase,
            expiration_date=user_expiration,
        )
    )

    assert result[0].expiration_date == user_expiration
    logs = (
        await db_session.execute(select(IngredientShelfLifeLog))
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].log_type == "deviation"
    assert logs[0].user_shelf_life_days == 3
    assert logs[0].master_shelf_life_days == 7


async def test_no_log_when_user_days_match_master(
    db_session,
    test_user: User,
    shelf_life_service: IngredientShelfLifeService,
):
    await _add_master(db_session, "우유", 7)
    purchase = date.today()
    service = IngredientService(
        user=test_user,
        ingredient_repo=IngredientRepository(db_session),
        shelf_life_service=shelf_life_service,
    )

    await service.add_ingredients(
        AddIngredientRequest(
            ingredients=["우유"],
            purchase_date=purchase,
            expiration_date=purchase + timedelta(days=7),
        )
    )

    logs = (
        await db_session.execute(select(IngredientShelfLifeLog))
    ).scalars().all()
    assert logs == []


async def test_missing_with_user_input_when_master_miss(
    db_session,
    test_user: User,
    shelf_life_service: IngredientShelfLifeService,
):
    purchase = date.today()
    expiration = purchase + timedelta(days=5)
    service = IngredientService(
        user=test_user,
        ingredient_repo=IngredientRepository(db_session),
        shelf_life_service=shelf_life_service,
    )

    result = await service.add_ingredients(
        AddIngredientRequest(
            ingredients=["새재료"],
            purchase_date=purchase,
            expiration_date=expiration,
        )
    )

    assert result[0].expiration_date == expiration
    logs = (
        await db_session.execute(select(IngredientShelfLifeLog))
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].log_type == "missing_with_user_input"
    assert logs[0].user_shelf_life_days == 5
    assert logs[0].master_shelf_life_days is None


async def test_exact_name_match_only(
    db_session,
    test_user: User,
    shelf_life_service: IngredientShelfLifeService,
):
    await _add_master(db_session, "우유", 7)
    service = IngredientService(
        user=test_user,
        ingredient_repo=IngredientRepository(db_session),
        shelf_life_service=shelf_life_service,
    )

    result = await service.add_ingredients(
        AddIngredientRequest(ingredients=["흰우유"], expiration_date=None)
    )

    assert result[0].expiration_date is None
    logs = (
        await db_session.execute(select(IngredientShelfLifeLog))
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].log_type == "missing"
    assert logs[0].ingredient_name == "흰우유"


async def test_batch_autofill_uses_per_name_shelf_life(
    db_session,
    test_user: User,
    shelf_life_service: IngredientShelfLifeService,
):
    await _add_master(db_session, "우유", 7)
    await _add_master(db_session, "계란", 14)
    purchase = date.today()
    service = IngredientService(
        user=test_user,
        ingredient_repo=IngredientRepository(db_session),
        shelf_life_service=shelf_life_service,
    )

    result = await service.add_ingredients(
        AddIngredientRequest(
            ingredients=["우유", "계란", "미등록"],
            purchase_date=purchase,
            expiration_date=None,
        )
    )

    by_name = {item.ingredient_name: item for item in result}
    assert by_name["우유"].expiration_date == purchase + timedelta(days=7)
    assert by_name["계란"].expiration_date == purchase + timedelta(days=14)
    assert by_name["미등록"].expiration_date is None
    logs = (
        await db_session.execute(select(IngredientShelfLifeLog))
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].ingredient_name == "미등록"


async def test_shopping_to_ingredient_autofills(
    db_session,
    test_user: User,
    shelf_life_service: IngredientShelfLifeService,
):
    await _add_master(db_session, "대파", 5)
    shopping_repo = ShoppingRepository(db_session)
    items = await shopping_repo.add_items(
        [ShoppingItem(user_id=test_user.id, name="대파", is_checked=False)]
    )
    service = ShoppingService(
        user=test_user,
        shopping_repo=shopping_repo,
        ingredient_repo=IngredientRepository(db_session),
        shelf_life_service=shelf_life_service,
    )

    result = await service.to_ingredient(items[0].id)

    assert result.expiration_date == date.today() + timedelta(days=5)
    assert result.status != "unknown"
    logs = (
        await db_session.execute(select(IngredientShelfLifeLog))
    ).scalars().all()
    assert logs == []


async def test_resolve_expirations_unit_passthrough_match():
    repo = AsyncMock()
    repo.get_by_names.return_value = {
        "우유": IngredientShelfLife(ingredient_name="우유", shelf_life_days=7)
    }
    repo.add_logs = AsyncMock()
    service = IngredientShelfLifeService(repo=repo)
    purchase = date(2026, 7, 1)
    expiration = purchase + timedelta(days=7)

    resolved = await service.resolve_expirations_on_add(
        names=["우유"],
        purchase_date=purchase,
        expiration_date=expiration,
        user_id=uuid6.uuid7(),
    )

    assert resolved == [expiration]
    repo.add_logs.assert_awaited_once_with([])
