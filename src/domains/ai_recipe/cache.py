from loguru import logger
from redis.asyncio import Redis

from domains.ai_recipe.schemas import AiRecipeCacheRecord, AiRecipeListCacheRecord

TTL_SECONDS = 86400
LIST_TTL_SECONDS = 1800


class AiRecipeCache:
    def __init__(
        self,
        redis: Redis,
        ttl_seconds: int = TTL_SECONDS,
        list_ttl_seconds: int = LIST_TTL_SECONDS,
    ) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._list_ttl = list_ttl_seconds

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

    @staticmethod
    def list_key(user_id: int) -> str:
        return f"ai_recipe_list:{user_id}"

    async def get_list(self, user_id: int) -> AiRecipeListCacheRecord | None:
        try:
            raw = await self._redis.get(self.list_key(user_id))
        except Exception:
            logger.warning("ai recipe list cache get failed")
            return None
        if raw is None:
            return None
        try:
            return AiRecipeListCacheRecord.model_validate_json(raw)
        except Exception:
            logger.warning("ai recipe list cache decode failed")
            return None

    async def set_list(self, user_id: int, record: AiRecipeListCacheRecord) -> None:
        try:
            await self._redis.set(
                self.list_key(user_id),
                record.model_dump_json(),
                ex=self._list_ttl,
            )
        except Exception:
            logger.warning("ai recipe list cache set failed")

    async def invalidate_list(self, user_id: int) -> None:
        try:
            await self._redis.delete(self.list_key(user_id))
        except Exception:
            logger.warning("ai recipe list cache invalidate failed")
