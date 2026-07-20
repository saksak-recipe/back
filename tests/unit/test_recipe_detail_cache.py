import fakeredis.aioredis
import pytest

from domains.recipe_detail.cache import RecipeDetailCache, cache_key
from domains.recipe_detail.schemas import RecipeDetailResponse


def _sample(**kwargs) -> RecipeDetailResponse:
    base = dict(
        board_name="제목",
        author_name="작성자",
        recipe_name="요리",
        source_url="https://www.10000recipe.com/recipe/1",
        cached=False,
    )
    base.update(kwargs)
    return RecipeDetailResponse(**base)


@pytest.fixture
async def cache():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    c = RecipeDetailCache(redis, ttl_seconds=60)
    yield c
    await redis.aclose()


def test_cache_key_normalizes():
    assert cache_key(" A ", "B") == cache_key("a", "b")


async def test_cache_hit_and_miss(cache: RecipeDetailCache):
    key = cache_key("제목", "작성자")
    assert await cache.get(key) is None
    await cache.set(key, _sample())
    hit = await cache.get(key)
    assert hit is not None
    assert hit.recipe_name == "요리"
    assert hit.cached is True


async def test_cache_get_failure_returns_none():
    class BoomRedis:
        async def get(self, key):
            raise RuntimeError("down")

    cache = RecipeDetailCache(BoomRedis(), ttl_seconds=60)  # type: ignore[arg-type]
    assert await cache.get("x") is None
