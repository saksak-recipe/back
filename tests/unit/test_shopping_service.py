from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
import uuid6

from core.exception.exceptions import ShoppingItemNotFoundException
from domains.ingredient.model import Ingredient
from domains.shopping.model import ShoppingItem
from domains.shopping.repository import ShoppingRepository
from domains.shopping.schemas import AddShoppingItemsRequest, UpdateShoppingItemRequest
from domains.shopping.service import ShoppingService
from domains.user.model import User


@pytest.fixture
def shopping_repo() -> AsyncMock:
    return AsyncMock()


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
def shopping_service(
    user: User,
    shopping_repo: AsyncMock,
    ingredient_repo: AsyncMock,
) -> ShoppingService:
    return ShoppingService(
        user=user,
        shopping_repo=shopping_repo,
        ingredient_repo=ingredient_repo,
    )


async def test_add_items_skips_existing_and_request_duplicates(
    shopping_service: ShoppingService,
    shopping_repo: AsyncMock,
    user: User,
):
    created_at = datetime.now(timezone.utc)
    shopping_repo.get_existing_names.return_value = {"대파"}
    shopping_repo.add_items.return_value = [
        ShoppingItem(
            id=1,
            user_id=user.id,
            name="계란",
            is_checked=False,
            created_at=created_at,
        ),
        ShoppingItem(
            id=2,
            user_id=user.id,
            name="간장",
            is_checked=False,
            created_at=created_at,
        ),
    ]

    result = await shopping_service.add_items(
        AddShoppingItemsRequest(names=["대파", "계란", "계란", " 간장"])
    )

    shopping_repo.get_existing_names.assert_awaited_once_with(
        user.id, ["대파", "계란", "간장"]
    )
    created = shopping_repo.add_items.await_args.args[0]
    assert [item.name for item in created] == ["계란", "간장"]
    assert all(item.user_id == user.id and not item.is_checked for item in created)
    assert len(result) == 2


async def test_add_items_all_duplicate_returns_empty(
    shopping_service: ShoppingService,
    shopping_repo: AsyncMock,
):
    shopping_repo.get_existing_names.return_value = {"대파", "계란"}

    result = await shopping_service.add_items(
        AddShoppingItemsRequest(names=["대파", "계란", "계란"])
    )

    assert result == []
    shopping_repo.add_items.assert_not_awaited()


async def test_repository_add_items_skips_unique_conflict(
    db_session,
    test_user: User,
):
    repository = ShoppingRepository(db_session)
    await repository.add_items(
        [ShoppingItem(user_id=test_user.id, name="대파", is_checked=False)]
    )

    saved = await repository.add_items(
        [
            ShoppingItem(user_id=test_user.id, name="대파", is_checked=False),
            ShoppingItem(user_id=test_user.id, name="계란", is_checked=False),
        ]
    )

    assert [item.name for item in saved] == ["계란"]
    assert [
        item.name for item in await repository.list_by_user(test_user.id)
    ] == ["대파", "계란"]


async def test_list_items_unchecked_first(
    shopping_service: ShoppingService,
    shopping_repo: AsyncMock,
    user: User,
):
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2026, 1, 2, tzinfo=timezone.utc)
    shopping_repo.list_by_user.return_value = [
        ShoppingItem(
            id=1,
            user_id=user.id,
            name="체크됨",
            is_checked=True,
            created_at=older,
        ),
        ShoppingItem(
            id=2,
            user_id=user.id,
            name="미체크",
            is_checked=False,
            created_at=newer,
        ),
    ]

    result = await shopping_service.list_items()

    assert [item.name for item in result] == ["미체크", "체크됨"]
    shopping_repo.list_by_user.assert_awaited_once_with(user.id)


async def test_update_item_sets_checked(
    shopping_service: ShoppingService,
    shopping_repo: AsyncMock,
    user: User,
):
    item = ShoppingItem(
        id=1,
        user_id=user.id,
        name="우유",
        is_checked=False,
        created_at=datetime.now(timezone.utc),
    )
    shopping_repo.get_by_id.return_value = item

    result = await shopping_service.update_item(
        1, UpdateShoppingItemRequest(is_checked=True)
    )

    assert item.is_checked is True
    assert result.is_checked is True
    shopping_repo.get_by_id.assert_awaited_once_with(1, user.id)


async def test_update_item_not_found_raises(
    shopping_service: ShoppingService,
    shopping_repo: AsyncMock,
):
    shopping_repo.get_by_id.return_value = None

    with pytest.raises(ShoppingItemNotFoundException):
        await shopping_service.update_item(
            999, UpdateShoppingItemRequest(is_checked=True)
        )


async def test_delete_item_not_found_raises(
    shopping_service: ShoppingService,
    shopping_repo: AsyncMock,
):
    shopping_repo.delete_item.return_value = False

    with pytest.raises(ShoppingItemNotFoundException):
        await shopping_service.delete_item(999)


async def test_delete_all_empty_raises(
    shopping_service: ShoppingService,
    shopping_repo: AsyncMock,
):
    shopping_repo.delete_all.return_value = False

    with pytest.raises(ShoppingItemNotFoundException):
        await shopping_service.delete_all()


async def test_to_ingredient_creates_ingredient_and_deletes_shopping(
    shopping_service: ShoppingService,
    shopping_repo: AsyncMock,
    ingredient_repo: AsyncMock,
    user: User,
):
    shopping_repo.get_by_id.return_value = ShoppingItem(
        id=1,
        user_id=user.id,
        name="대파",
        is_checked=False,
        created_at=datetime.now(timezone.utc),
    )
    ingredient_repo.add_ingredient.return_value = [
        Ingredient(
            id=10,
            user_id=user.id,
            ingredient_name="대파",
            purchase_date=date.today(),
            expiration_date=None,
        )
    ]
    shopping_repo.delete_item.return_value = True

    result = await shopping_service.to_ingredient(1)

    added = ingredient_repo.add_ingredient.await_args.args[0]
    assert len(added) == 1
    assert added[0].ingredient_name == "대파"
    assert added[0].purchase_date == date.today()
    assert added[0].expiration_date is None
    shopping_repo.delete_item.assert_awaited_once_with(1, user.id)
    assert result.ingredient_name == "대파"
    assert result.status == "unknown"


async def test_to_ingredient_not_found_raises(
    shopping_service: ShoppingService,
    shopping_repo: AsyncMock,
    ingredient_repo: AsyncMock,
):
    shopping_repo.get_by_id.return_value = None

    with pytest.raises(ShoppingItemNotFoundException):
        await shopping_service.to_ingredient(999)

    ingredient_repo.add_ingredient.assert_not_awaited()
