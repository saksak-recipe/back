import time
from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from core.exception.exceptions import ExternalServiceException, NotFoundException
from domains.ai_recipe.agent import AgentFailedError
from domains.ai_recipe import service as service_module
from domains.ai_recipe.schemas import (
    AiRecipeCacheRecord,
    AiRecipeCandidate,
    AiRecipeIngredient,
    AiRecipeStep,
)
from domains.ai_recipe.service import AiRecipeService


@pytest.fixture
def user():
    mocked_user = MagicMock()
    mocked_user.id = "user-1"
    return mocked_user


async def test_recommend_empty_skips_agent(user):
    repo = AsyncMock()
    repo.get_ingredients.return_value = []
    agent = MagicMock()
    cache = AsyncMock()
    service = AiRecipeService(
        user=user, ingredient_repo=repo, agent=agent, cache=cache
    )

    result = await service.recommend()

    assert result.ingredients_used == []
    assert result.recipes == []
    agent.run_list.assert_not_called()
    cache.set.assert_not_awaited()


async def test_recommend_caches_five(user):
    repo = AsyncMock()
    item = MagicMock()
    item.ingredient_name = "계란"
    repo.get_ingredients.return_value = [item]
    agent = MagicMock()
    agent.run_list.return_value = [
        AiRecipeCandidate(
            recipe_name=f"요리{i}",
            recipe_ingredients=["계란", "밥"],
            recipe_difficulty="초급",
            time="10분",
        )
        for i in range(5)
    ]
    cache = AsyncMock()
    service = AiRecipeService(
        user=user, ingredient_repo=repo, agent=agent, cache=cache
    )

    result = await service.recommend()

    assert len(result.recipes) == 5
    assert len({recipe.recipe_id for recipe in result.recipes}) == 5
    assert result.recipes[0].owned_ingredients == ["계란"]
    assert result.recipes[0].missing_ingredients == ["밥"]
    assert result.recipes[0].source == "ai"
    assert cache.set.await_count == 5


@pytest.mark.parametrize(
    "agent_error",
    [
        AgentFailedError("fail"),
        openai.APIError("fail", request=None, body=None),
    ],
)
async def test_recommend_maps_agent_failure(user, agent_error):
    repo = AsyncMock()
    item = MagicMock()
    item.ingredient_name = "계란"
    repo.get_ingredients.return_value = [item]
    agent = MagicMock()
    agent.run_list.side_effect = agent_error
    cache = AsyncMock()
    service = AiRecipeService(
        user=user, ingredient_repo=repo, agent=agent, cache=cache
    )

    with pytest.raises(
        ExternalServiceException, match="AI 레시피 생성에 실패했습니다."
    ):
        await service.recommend()


async def test_recommend_maps_agent_timeout(user, monkeypatch):
    monkeypatch.setattr(service_module, "AGENT_TIMEOUT_SECONDS", 0.01)
    repo = AsyncMock()
    item = MagicMock()
    item.ingredient_name = "계란"
    repo.get_ingredients.return_value = [item]
    agent = MagicMock()
    agent.run_list.side_effect = lambda _names: time.sleep(0.05)
    service = AiRecipeService(
        user=user, ingredient_repo=repo, agent=agent, cache=AsyncMock()
    )

    with pytest.raises(
        ExternalServiceException, match="AI 레시피 생성에 실패했습니다."
    ):
        await service.recommend()


async def test_detail_not_found(user):
    cache = AsyncMock()
    cache.get.return_value = None
    service = AiRecipeService(
        user=user,
        ingredient_repo=AsyncMock(),
        agent=MagicMock(),
        cache=cache,
    )

    with pytest.raises(NotFoundException, match="AI 레시피를 찾지 못했습니다."):
        await service.get_detail("missing-id")


async def test_detail_cache_hit(user):
    cache = AsyncMock()
    cache.get.return_value = AiRecipeCacheRecord(
        recipe_id="rid",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란"],
        owned_ingredients=["계란"],
        missing_ingredients=[],
        recipe_difficulty="초급",
        time="10분",
        ingredients=[AiRecipeIngredient(name="계란", amount="2개")],
        steps=[AiRecipeStep(order=1, description="볶는다")],
        tips=["약불"],
    )
    agent = MagicMock()
    service = AiRecipeService(
        user=user, ingredient_repo=AsyncMock(), agent=agent, cache=cache
    )

    result = await service.get_detail("rid")

    assert result.cached is True
    assert result.ingredients == [AiRecipeIngredient(name="계란", amount="2개")]
    agent.run_detail.assert_not_called()


async def test_detail_expands_when_missing(user):
    cache = AsyncMock()
    summary = AiRecipeCacheRecord(
        recipe_id="rid",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란", "밥"],
        owned_ingredients=["계란"],
        missing_ingredients=["밥"],
        recipe_difficulty="초급",
        time="10분",
    )
    cache.get.return_value = summary
    agent = MagicMock()
    agent.run_detail.return_value = {
        "ingredients": [AiRecipeIngredient(name="계란", amount="2개")],
        "steps": [AiRecipeStep(order=1, description="볶는다")],
        "tips": ["약불"],
    }
    repo = AsyncMock()
    item = MagicMock()
    item.ingredient_name = "계란"
    repo.get_ingredients.return_value = [item]
    service = AiRecipeService(
        user=user, ingredient_repo=repo, agent=agent, cache=cache
    )

    result = await service.get_detail("rid")

    assert result.cached is False
    assert result.steps[0].description == "볶는다"
    cache.set.assert_awaited_once()


async def test_detail_maps_agent_failure(user):
    cache = AsyncMock()
    cache.get.return_value = AiRecipeCacheRecord(
        recipe_id="rid",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란"],
    )
    agent = MagicMock()
    agent.run_detail.side_effect = AgentFailedError("fail")
    repo = AsyncMock()
    repo.get_ingredients.return_value = []
    service = AiRecipeService(
        user=user, ingredient_repo=repo, agent=agent, cache=cache
    )

    with pytest.raises(
        ExternalServiceException, match="AI 레시피 상세 생성에 실패했습니다."
    ):
        await service.get_detail("rid")


async def test_detail_maps_agent_timeout(user, monkeypatch):
    monkeypatch.setattr(service_module, "AGENT_TIMEOUT_SECONDS", 0.01)
    cache = AsyncMock()
    cache.get.return_value = AiRecipeCacheRecord(
        recipe_id="rid",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란"],
    )
    agent = MagicMock()
    agent.run_detail.side_effect = lambda _names, _record: time.sleep(0.05)
    repo = AsyncMock()
    repo.get_ingredients.return_value = []
    service = AiRecipeService(
        user=user, ingredient_repo=repo, agent=agent, cache=cache
    )

    with pytest.raises(
        ExternalServiceException, match="AI 레시피 상세 생성에 실패했습니다."
    ):
        await service.get_detail("rid")
