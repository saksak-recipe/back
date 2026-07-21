import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.exception.codes import ErrorCode
from core.exception.exceptions import NotFoundException
from domains.ingredient.scope import IngredientScopeLoader, RecipeScope


@pytest.fixture
def user():
    u = MagicMock()
    u.id = uuid.uuid4()
    return u


async def test_load_personal_uses_personal_ingredients(user):
    item = MagicMock()
    ingredient_repo = AsyncMock()
    ingredient_repo.get_ingredients.return_value = [item]
    group_repo = AsyncMock()
    loader = IngredientScopeLoader(user, ingredient_repo, group_repo)

    result = await loader.load(RecipeScope.personal)

    assert result.ingredients == [item]
    assert result.scope is RecipeScope.personal
    assert result.cache_owner_id == user.id
    ingredient_repo.get_ingredients.assert_awaited_once_with(user.id)
    group_repo.get_membership.assert_not_awaited()


async def test_load_group_uses_group_ingredients(user):
    group_id = uuid.uuid4()
    membership = MagicMock(group_id=group_id)
    item = MagicMock()
    ingredient_repo = AsyncMock()
    ingredient_repo.list_by_group.return_value = [item]
    group_repo = AsyncMock()
    group_repo.get_membership.return_value = membership
    loader = IngredientScopeLoader(user, ingredient_repo, group_repo)

    result = await loader.load(RecipeScope.group)

    assert result.ingredients == [item]
    assert result.scope is RecipeScope.group
    assert result.cache_owner_id == group_id
    ingredient_repo.list_by_group.assert_awaited_once_with(group_id)
    ingredient_repo.get_ingredients.assert_not_awaited()


async def test_load_group_without_membership_raises_not_found(user):
    ingredient_repo = AsyncMock()
    group_repo = AsyncMock()
    group_repo.get_membership.return_value = None
    loader = IngredientScopeLoader(user, ingredient_repo, group_repo)

    with pytest.raises(NotFoundException) as exc_info:
        await loader.load(RecipeScope.group)

    assert exc_info.value.code == ErrorCode.GROUP_NOT_FOUND
    assert "가입된 그룹" in exc_info.value.detail
