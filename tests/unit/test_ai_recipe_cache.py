import fakeredis.aioredis
import pytest

from domains.ai_recipe.cache import AiRecipeCache
from domains.ai_recipe.schemas import AiRecipeCacheRecord


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
