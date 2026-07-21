from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from typing import Any

import openai
from loguru import logger
from pydantic import BaseModel

from core.exception.exceptions import ExternalServiceException, NotFoundException
from domains.ai_recipe.agent import AgentFailedError, AiRecipeAgent
from domains.ai_recipe.cache import AiRecipeCache
from domains.ai_recipe.quota import AiQuotaStore
from domains.ai_recipe.schemas import (
    AiRecipeCacheRecord,
    AiRecipeCandidate,
    AiRecipeDetailResponse,
    AiRecipeListCacheRecord,
    AiRecipeRecommendation,
    AiRecipeRecommendationResponse,
)
from domains.ingredient.scope import IngredientScopeLoader, RecipeScope
from domains.ingredient_matching.matching import normalize_name
from domains.ingredient_matching.urgency import urgent_names
from domains.rag.mapper import classify_ingredients
from domains.user.model import User

AGENT_TIMEOUT_SECONDS = 25


def ingredients_hash(names: list[str]) -> str:
    normalized = ",".join(sorted(normalize_name(name) for name in names))
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _maybe_dump(value: object) -> object:
    if isinstance(value, list):
        return [
            item.model_dump() if isinstance(item, BaseModel) else item for item in value
        ]
    if isinstance(value, BaseModel):
        return value.model_dump()
    return value


class AiRecipeService:
    def __init__(
        self,
        user: User,
        scope_loader: IngredientScopeLoader,
        agent: AiRecipeAgent,
        cache: AiRecipeCache,
        quota: AiQuotaStore,
    ) -> None:
        self.user = user
        self.scope_loader = scope_loader
        self.agent = agent
        self.cache = cache
        self.quota = quota

    async def recommend(
        self,
        refresh: bool = False,
        scope: RecipeScope = RecipeScope.personal,
    ) -> AiRecipeRecommendationResponse:
        scoped = await self.scope_loader.load(scope)
        ingredients = scoped.ingredients
        names = [item.ingredient_name for item in ingredients]
        if not names:
            return AiRecipeRecommendationResponse(ingredients_used=[], recipes=[])

        digest = ingredients_hash(names)
        if not refresh:
            cached = await self.cache.get_list(
                scoped.cache_owner_id, scope=scoped.scope
            )
            if cached is not None and cached.ingredients_hash == digest:
                return AiRecipeRecommendationResponse(
                    ingredients_used=cached.ingredients_used,
                    recipes=cached.recipes,
                )

        await self.quota.consume(scoped.scope, scoped.cache_owner_id)
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
            scoped.cache_owner_id,
            AiRecipeListCacheRecord(
                ingredients_hash=digest,
                ingredients_used=names,
                recipes=response.recipes,
            ),
            scope=scoped.scope,
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

    async def get_detail(
        self,
        recipe_id: str,
        scope: RecipeScope = RecipeScope.personal,
    ) -> AiRecipeDetailResponse:
        record = await self.cache.get(recipe_id)
        if record is None:
            raise NotFoundException(detail="AI 레시피를 찾지 못했습니다.")

        if record.has_detail():
            return self._detail_response(record, cached=True)

        scoped = await self.scope_loader.load(scope)
        names = [item.ingredient_name for item in scoped.ingredients]
        await self.quota.consume(scoped.scope, scoped.cache_owner_id)
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

    async def stream_detail(
        self,
        recipe_id: str,
        scope: RecipeScope = RecipeScope.personal,
    ) -> AsyncIterator[tuple[str, object]]:
        record = await self.cache.get(recipe_id)
        if record is None:
            raise NotFoundException(detail="AI 레시피를 찾지 못했습니다.")

        if record.has_detail():
            yield (
                "meta",
                {
                    "recipe_id": record.recipe_id,
                    "recipe_name": record.recipe_name,
                    "owned_ingredients": record.owned_ingredients,
                    "missing_ingredients": record.missing_ingredients,
                    "cached": True,
                },
            )
            yield (
                "ingredients",
                [item.model_dump() for item in record.ingredients or []],
            )
            yield ("steps", [item.model_dump() for item in record.steps or []])
            yield ("tips", list(record.tips or []))
            yield ("done", {"cached": True})
            return

        scoped = await self.scope_loader.load(scope)
        names = [item.ingredient_name for item in scoped.ingredients]
        await self.quota.consume(scoped.scope, scoped.cache_owner_id)

        yield (
            "meta",
            {
                "recipe_id": record.recipe_id,
                "recipe_name": record.recipe_name,
                "owned_ingredients": record.owned_ingredients,
                "missing_ingredients": record.missing_ingredients,
                "cached": False,
            },
        )

        try:
            complete: dict[str, Any] | None = None
            async for kind, value in self._agent_stream_events(names, record):
                if kind == "complete":
                    complete = value if isinstance(value, dict) else None
                else:
                    yield (kind, value)
            if complete is None:
                raise AgentFailedError("missing complete")
            updated = record.model_copy(
                update={
                    "ingredients": complete["ingredients"],
                    "steps": complete["steps"],
                    "tips": complete["tips"],
                }
            )
            await self.cache.set(updated)
            yield ("done", {"cached": False})
        except (TimeoutError, AgentFailedError, openai.OpenAIError):
            logger.exception("AI recipe detail stream failed")
            yield ("error", {"detail": "AI 레시피 상세 생성에 실패했습니다."})

    async def _agent_stream_events(
        self,
        names: list[str],
        record: AiRecipeCacheRecord,
    ) -> AsyncIterator[tuple[str, object]]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        def run() -> None:
            try:
                for item in self.agent.stream_detail(names, record):
                    loop.call_soon_threadsafe(queue.put_nowait, ("ok", item))
                loop.call_soon_threadsafe(queue.put_nowait, ("end", None))
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, ("err", exc))

        task = loop.run_in_executor(None, run)
        deadline = loop.time() + AGENT_TIMEOUT_SECONDS
        try:
            while True:
                timeout = deadline - loop.time()
                if timeout <= 0:
                    raise TimeoutError()
                status, payload = await asyncio.wait_for(queue.get(), timeout=timeout)
                if status == "end":
                    break
                if status == "err":
                    raise payload
                kind, value = payload
                if kind == "complete":
                    yield (kind, value)
                else:
                    yield (kind, _maybe_dump(value))
            await task
        except TimeoutError as exc:
            raise TimeoutError() from exc

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
