from loguru import logger
from redis.asyncio import Redis

from core.config import settings

_redis: Redis | None = None


async def init_redis() -> None:
    global _redis
    try:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception as exc:
        logger.warning("Failed to create Redis client from URL: {}", exc)
        raise
    try:
        await _redis.ping()
    except Exception as exc:
        logger.warning(
            "Redis ping failed; server will start but Redis-backed operations may fail: {}",
            exc,
        )


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis is not initialized")
    return _redis
