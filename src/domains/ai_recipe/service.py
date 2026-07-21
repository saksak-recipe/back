from __future__ import annotations

import asyncio
import hashlib
import uuid

import openai
from loguru import logger

from core.exception.exceptions import ExternalServiceException, NotFoundException
from domains.ai_recipe.agent import AgentFailedError, AiRecipeAgent
from domains.ai_recipe.cache import AiRecipeCache
from domains.ai_recipe.schemas import (
    AiRecipeCacheRecord,
    AiRecipeCandidate,
    AiRecipeDetailResponse,
    AiRecipeListCacheRecord,
    AiRecipeRecommendation,
    AiRecipeRecommendationResponse,
)
from domains.ingredient.repository import IngredientRepository
from domains.ingredient_matching.matching import normalize_name
from domains.ingredient_matching.urgency import urgent_names
from domains.rag.mapper import classify_ingredients
from domains.user.model import User

AGENT_TIMEOUT_SECONDS = 25


def ingredients_hash(names: list[str]) -> str:
    normalized = ",".join(sorted(normalize_name(name) for name in names))
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


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

    async def recommend(self, refresh: bool = False) -> AiRecipeRecommendationResponse:
        ingredients = await self.ingredient_repo.get_ingredients(self.user.id)
        names = [item.ingredient_name for item in ingredients]
        if not names:
            return AiRecipeRecommendationResponse(ingredients_used=[], recipes=[])

        digest = ingredients_hash(names)
        if not refresh:
            cached = await self.cache.get_list(self.user.id)
            if cached is not None and cached.ingredients_hash == digest:
                return AiRecipeRecommendationResponse(
                    ingredients_used=cached.ingredients_used,
                    recipes=cached.recipes,
                )

        candidates = await self._generate_list(names, urgent_names(ingredients))

        recipes: list[AiRecipeRecommendation] = []
        for candidate in candidates:
            recipe_id = str(uuid.uuid4())
            owned, missing = classify_ingredients(candidate.recipe_ingredients, names)
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
        response = AiRecipeRecommendationResponse(
            ingredients_used=names,
            recipes=recipes,
        )
        await self.cache.set_list(
            self.user.id,
            AiRecipeListCacheRecord(
                ingredients_hash=digest,
                ingredients_used=names,
                recipes=response.recipes,
            ),
        )
        return response

    async def _generate_list(
        self,
        names: list[str],
        urgent: list[str],
    ) -> list[AiRecipeCandidate]:
        last_exc: Exception | None = None
        for _ in range(2):
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self.agent.run_list, names, urgent),
                    timeout=AGENT_TIMEOUT_SECONDS,
                )
            except (TimeoutError, AgentFailedError, openai.OpenAIError) as exc:
                last_exc = exc

        assert last_exc is not None
        logger.error("AI recipe recommend failed: {}", last_exc)
        raise ExternalServiceException(
            detail="AI 레시피 생성에 실패했습니다."
        ) from last_exc

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
            logger.exception("AI recipe detail failed")
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
