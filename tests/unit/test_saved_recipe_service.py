from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import uuid6

from core.exception.codes import ErrorCode
from core.exception.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from domains.recipe_detail.schemas import RecipeDetailResponse, RecipeIngredient, RecipeStep
from domains.saved_recipe.model import SavedRecipe
from domains.saved_recipe.schemas import SaveRecipeRequest
from domains.saved_recipe.service import SavedRecipeService
from domains.user.model import User


@pytest.fixture
def user() -> User:
    return User(
        id=uuid6.uuid7(),
        email="test@example.com",
        password="hashed",
        nickname="testuser",
    )


@pytest.fixture
def repo() -> AsyncMock:
    mock = AsyncMock()
    mock.find_by_source.return_value = None
    return mock


@pytest.fixture
def detail_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    user: User, repo: AsyncMock, detail_service: AsyncMock
) -> SavedRecipeService:
    return SavedRecipeService(
        user=user,
        repo=repo,
        recipe_detail_service=detail_service,
    )


def _saved_row(user: User, **overrides) -> SavedRecipe:
    data = {
        "id": uuid6.uuid7(),
        "user_id": user.id,
        "source": "mangae",
        "source_id": "김치볶음밥|요리왕",
        "recipe_name": "김치볶음밥",
        "recipe_difficulty": "쉬움",
        "time": "30분",
        "snapshot": {"ingredients": [], "steps": [], "tips": []},
        "created_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return SavedRecipe(**data)


async def test_save_mangae_recipe(
    service: SavedRecipeService,
    repo: AsyncMock,
    detail_service: AsyncMock,
    user: User,
):
    detail_service.get_detail.return_value = RecipeDetailResponse(
        board_name="김치볶음밥",
        author_name="요리왕",
        recipe_name="김치볶음밥",
        source_url="https://example.com/1",
        main_image_url=None,
        ingredients=[RecipeIngredient(name="김치", amount="1컵")],
        steps=[RecipeStep(order=1, description="볶는다")],
        tips=[],
    )
    repo.find_by_source.return_value = None
    repo.add.return_value = _saved_row(
        user,
        source="mangae",
        source_id="김치볶음밥|요리왕",
        recipe_name="김치볶음밥",
    )

    result = await service.save(
        SaveRecipeRequest(source="mangae", source_id="김치볶음밥|요리왕")
    )

    assert result.source == "mangae"
    detail_service.get_detail.assert_awaited_once_with("김치볶음밥", "요리왕")


async def test_save_duplicate_raises_conflict(
    service: SavedRecipeService, repo: AsyncMock, user: User
):
    repo.find_by_source.return_value = _saved_row(user)

    with pytest.raises(ConflictException) as exc:
        await service.save(
            SaveRecipeRequest(source="mangae", source_id="김치볶음밥|요리왕")
        )

    assert exc.value.code == ErrorCode.CONFLICT


async def test_save_mangae_bad_source_id(service: SavedRecipeService):
    with pytest.raises(BadRequestException):
        await service.save(SaveRecipeRequest(source="mangae", source_id="no-pipe"))


async def test_get_raises_when_missing(service: SavedRecipeService, repo: AsyncMock):
    repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await service.get(uuid4())


async def test_delete_raises_when_missing(service: SavedRecipeService, repo: AsyncMock):
    repo.delete.return_value = False
    with pytest.raises(NotFoundException):
        await service.delete(uuid4())


async def test_status_saved(
    service: SavedRecipeService, repo: AsyncMock, user: User
):
    row = _saved_row(user)
    repo.find_by_source.return_value = row
    result = await service.status("mangae", "김치볶음밥|요리왕")
    assert result.saved is True
    assert result.id == row.id


async def test_status_not_saved(service: SavedRecipeService, repo: AsyncMock):
    repo.find_by_source.return_value = None
    result = await service.status("mangae", "없음|작성자")
    assert result.saved is False
    assert result.id is None


async def test_status_rejects_ai_source(service: SavedRecipeService):
    with pytest.raises(BadRequestException, match="source는 mangae 여야 합니다"):
        await service.status("ai", "rid-1")


async def test_list_saved(service: SavedRecipeService, repo: AsyncMock, user: User):
    repo.list_by_user.return_value = [_saved_row(user)]
    result = await service.list_saved()
    assert len(result) == 1
    repo.list_by_user.assert_awaited_once_with(user.id)
