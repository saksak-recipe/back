import fakeredis.aioredis
import pytest

from domains.ai_recipe.cache import AiRecipeCache
from domains.ai_recipe.schemas import (
    AiRecipeCacheRecord,
    AiRecipeListCacheRecord,
    AiRecipeRecommendation,
)


@pytest.fixture
def cache():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return AiRecipeCache(redis, ttl_seconds=86400)


async def test_set_get_roundtrip(cache: AiRecipeCache):
    record = AiRecipeCacheRecord(
        recipe_id="11111111-1111-1111-1111-111111111111",
        recipe_name="계란볶음밥",
        recipe_ingredients=["계란", "밥"],
        owned_ingredients=["계란"],
        missing_ingredients=["밥"],
        recipe_difficulty="초급",
        time="15분",
    )
    await cache.set(record)
    got = await cache.get(record.recipe_id)
    assert got is not None
    assert got.recipe_name == "계란볶음밥"
    assert got.has_detail() is False


async def test_get_missing_returns_none(cache: AiRecipeCache):
    assert await cache.get("00000000-0000-0000-0000-000000000000") is None


async def test_list_cache_roundtrip_and_invalidation():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = AiRecipeCache(redis, list_ttl_seconds=1800)
    record = AiRecipeListCacheRecord(
        ingredients_hash="abc",
        ingredients_used=["계란"],
        recipes=[
            AiRecipeRecommendation(
                recipe_id="rid",
                recipe_name="계란찜",
                owned_ingredients=["계란"],
            )
        ],
    )

    await cache.set_list(user_id=1, record=record)

    got = await cache.get_list(1)
    assert got == record
    assert await redis.ttl(cache.list_key(1)) == 1800

    await cache.invalidate_list(1)
    assert await cache.get_list(1) is None
