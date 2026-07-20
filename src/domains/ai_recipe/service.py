from __future__ import annotations

import asyncio
import uuid

import openai

from core.exception.exceptions import ExternalServiceException, NotFoundException
from domains.ai_recipe.agent import AgentFailedError, AiRecipeAgent
from domains.ai_recipe.cache import AiRecipeCache
from domains.ai_recipe.schemas import (
    AiRecipeCacheRecord,
    AiRecipeDetailResponse,
    AiRecipeRecommendation,
    AiRecipeRecommendationResponse,
)
from domains.ingredient.repository import IngredientRepository
from domains.rag.mapper import classify_ingredients
from domains.user.model import User

AGENT_TIMEOUT_SECONDS = 60


class AiRecipeService:
    def __init__(
        self,
        user: User,
        ingredient_repo: IngredientRepository,
        agent: AiRecipeAgent,
        cache: AiRecipeCache,
    ) -> None:
        self.user = user
        self.ingredient_repo = ingredient_repo
        self.agent = agent
        self.cache = cache

    async def recommend(self) -> AiRecipeRecommendationResponse:
        ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
        names = [item.ingredient_name for item in ingredients]
        if not names:
            return AiRecipeRecommendationResponse(ingredients_used=[], recipes=[])

        try:
            candidates = await asyncio.wait_for(
                asyncio.to_thread(self.agent.run_list, names),
                timeout=AGENT_TIMEOUT_SECONDS,
            )
        except (TimeoutError, AgentFailedError, openai.OpenAIError) as exc:
            raise ExternalServiceException(
                detail="AI 레시피 생성에 실패했습니다."
            ) from exc

        recipes: list[AiRecipeRecommendation] = []
        for candidate in candidates:
            recipe_id = str(uuid.uuid4())
            owned, missing = classify_ingredients(
                candidate.recipe_ingredients, names
            )
            record = AiRecipeCacheRecord(
                recipe_id=recipe_id,
                recipe_name=candidate.recipe_name,
                recipe_ingredients=candidate.recipe_ingredients,
                owned_ingredients=owned,
                missing_ingredients=missing,
                recipe_difficulty=candidate.recipe_difficulty,
                time=candidate.time,
            )
            await self.cache.set(record)
            recipes.append(
                AiRecipeRecommendation(
                    recipe_id=recipe_id,
                    recipe_name=candidate.recipe_name,
                    owned_ingredients=owned,
                    missing_ingredients=missing,
                    recipe_difficulty=candidate.recipe_difficulty,
                    time=candidate.time,
                )
            )
        return AiRecipeRecommendationResponse(
            ingredients_used=names,
            recipes=recipes,
        )

    async def get_detail(self, recipe_id: str) -> AiRecipeDetailResponse:
        record = await self.cache.get(recipe_id)
        if record is None:
            raise NotFoundException(detail="AI 레시피를 찾지 못했습니다.")

        if record.has_detail():
            return self._detail_response(record, cached=True)

        ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
        names = [item.ingredient_name for item in ingredients]
        try:
            detail = await asyncio.wait_for(
                asyncio.to_thread(self.agent.run_detail, names, record),
                timeout=AGENT_TIMEOUT_SECONDS,
            )
        except (TimeoutError, AgentFailedError, openai.OpenAIError) as exc:
            raise ExternalServiceException(
                detail="AI 레시피 상세 생성에 실패했습니다."
            ) from exc

        updated = record.model_copy(
            update={
                "ingredients": detail["ingredients"],
                "steps": detail["steps"],
                "tips": detail["tips"],
            }
        )
        await self.cache.set(updated)
        return self._detail_response(updated, cached=False)

    @staticmethod
    def _detail_response(
        record: AiRecipeCacheRecord,
        *,
        cached: bool,
    ) -> AiRecipeDetailResponse:
        return AiRecipeDetailResponse(
            recipe_id=record.recipe_id,
            recipe_name=record.recipe_name,
            ingredients=record.ingredients or [],
            steps=record.steps or [],
            tips=record.tips or [],
            owned_ingredients=record.owned_ingredients,
            missing_ingredients=record.missing_ingredients,
            cached=cached,
        )
