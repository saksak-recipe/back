from loguru import logger
from redis.asyncio import Redis

from domains.ai_recipe.schemas import AiRecipeCacheRecord

TTL_SECONDS = 86400


class AiRecipeCache:
    def __init__(self, redis: Redis, ttl_seconds: int = TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    def _key(self, recipe_id: str) -> str:
        return f"ai_recipe:{recipe_id}"

    async def get(self, recipe_id: str) -> AiRecipeCacheRecord | None:
        try:
            raw = await self._redis.get(self._key(recipe_id))
        except Exception:
            logger.warning("ai recipe cache get failed")
            return None
        if raw is None:
            return None
        try:
            return AiRecipeCacheRecord.model_validate_json(raw)
        except Exception:
            logger.warning("ai recipe cache decode failed")
            return None

    async def set(self, record: AiRecipeCacheRecord) -> None:
        try:
            await self._redis.set(
                self._key(record.recipe_id),
                record.model_dump_json(),
                ex=self._ttl,
            )
        except Exception:
            logger.warning("ai recipe cache set failed")
