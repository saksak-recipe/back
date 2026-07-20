from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
import uuid6
from langchain_core.documents import Document

from domains.ingredient.model import Ingredient
from domains.rag.retriever import RecipeRetriever
from domains.rag.service import SEARCH_CANDIDATE_K, RagService
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
def ingredient_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def retriever() -> MagicMock:
    return MagicMock(spec=RecipeRetriever)


@pytest.fixture
def rag_service(user, ingredient_repo, retriever) -> RagService:
    return RagService(
        user=user,
        ingredient_repo=ingredient_repo,
        retriever=retriever,
    )


async def test_recommend_returns_empty_when_no_ingredients(
    rag_service: RagService, ingredient_repo: AsyncMock, retriever: MagicMock
):
    ingredient_repo.get_ingredients.return_value = []

    result = await rag_service.recommend_recipes()

    assert result.ingredients_used == []
    assert result.recipes == []
    retriever.search.assert_not_called()


async def test_recommend_maps_search_results(
    rag_service: RagService,
    ingredient_repo: AsyncMock,
    retriever: MagicMock,
    user: User,
):
    ingredient_repo.get_ingredients.return_value = [
        Ingredient(
            id=1,
            user_id=user.id,
            ingredient_name="계란",
            purchase_date=date.today(),
        ),
        Ingredient(
            id=2,
            user_id=user.id,
            ingredient_name="양파",
            purchase_date=date.today(),
        ),
    ]
    doc = Document(
        page_content="recipe_name: 계란볶음밥\nparsed_ingredients: 계란, 양파, 밥",
        metadata={
            "board_name": "한식",
            "author_name": "kim",
            "recipe_difficulty": "초급",
            "time": "15분",
        },
    )
    retriever.search.return_value = [(doc, 0.2)]

    result = await rag_service.recommend_recipes()

    assert result.ingredients_used == ["계란", "양파"]
    assert len(result.recipes) == 1
    assert result.recipes[0].recipe_name == "계란볶음밥"
    assert result.recipes[0].score == 0.2
    retriever.search.assert_called_once_with(
        "parsed_ingredients: 계란, 양파", k=SEARCH_CANDIDATE_K
    )


async def test_recommend_filters_recipes_named_like_ingredients(
    rag_service: RagService,
    ingredient_repo: AsyncMock,
    retriever: MagicMock,
    user: User,
):
    ingredient_repo.get_ingredients.return_value = [
        Ingredient(
            id=1,
            user_id=user.id,
            ingredient_name="김가루",
            purchase_date=date.today(),
        ),
        Ingredient(
            id=2,
            user_id=user.id,
            ingredient_name="계란",
            purchase_date=date.today(),
        ),
    ]
    name_collision = Document(
        page_content="recipe_name: 김가루\nparsed_ingredients: 김, 참기름",
        metadata={},
    )
    real_recipe = Document(
        page_content="recipe_name: 김치볶음밥\nparsed_ingredients: 김치, 계란, 밥",
        metadata={},
    )
    retriever.search.return_value = [
        (name_collision, 0.1),
        (name_collision, 0.1),
        (real_recipe, 0.3),
    ]

    result = await rag_service.recommend_recipes()

    assert len(result.recipes) == 1
    assert result.recipes[0].recipe_name == "김치볶음밥"


async def test_recommend_skips_unparsable_documents(
    rag_service: RagService,
    ingredient_repo: AsyncMock,
    retriever: MagicMock,
    user: User,
):
    ingredient_repo.get_ingredients.return_value = [
        Ingredient(
            id=1,
            user_id=user.id,
            ingredient_name="계란",
            purchase_date=date.today(),
        )
    ]
    bad = Document(page_content="no name here", metadata={})
    good = Document(
        page_content="recipe_name: 된장찌개\nparsed_ingredients: 계란",
        metadata={},
    )
    retriever.search.return_value = [(bad, 0.9), (good, 0.5)]

    result = await rag_service.recommend_recipes()

    assert len(result.recipes) == 1
    assert result.recipes[0].recipe_name == "된장찌개"
