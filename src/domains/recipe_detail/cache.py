import hashlib

from loguru import logger
from redis.asyncio import Redis

from domains.recipe_detail.normalize import normalize_text
from domains.recipe_detail.schemas import RecipeDetailResponse


def cache_key(board_name: str, author_name: str) -> str:
    raw = f"{normalize_text(board_name)}|{normalize_text(author_name)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RecipeDetailCache:
    def __init__(self, redis: Redis, ttl_seconds: int = 86400) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    def _redis_key(self, key: str) -> str:
        return f"recipe_detail:{key}"

    async def get(self, key: str) -> RecipeDetailResponse | None:
        try:
            raw = await self._redis.get(self._redis_key(key))
        except Exception:
            logger.warning("recipe detail cache get failed")
            return None
        if raw is None:
            return None
        try:
            value = RecipeDetailResponse.model_validate_json(raw)
        except Exception:
            logger.warning("recipe detail cache decode failed")
            return None
        return value.model_copy(update={"cached": True})

    async def set(self, key: str, value: RecipeDetailResponse) -> None:
        stored = value.model_copy(update={"cached": False})
        try:
            await self._redis.set(
                self._redis_key(key),
                stored.model_dump_json(),
                ex=self._ttl,
            )
        except Exception:
            logger.warning("recipe detail cache set failed")
