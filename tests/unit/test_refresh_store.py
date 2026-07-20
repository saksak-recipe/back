import uuid

import fakeredis.aioredis
import pytest

from domains.auth.refresh_store import RefreshTokenStore


@pytest.fixture
async def store():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = RefreshTokenStore(redis, ttl_seconds=60)
    yield s
    await redis.aclose()


async def test_save_and_pop_returns_user_id(store: RefreshTokenStore):
    user_id = uuid.uuid4()
    raw = "raw-refresh-token-value"
    await store.save(raw, user_id)
    got = await store.pop_user_id(raw)
    assert got == user_id
    assert await store.pop_user_id(raw) is None


async def test_delete_makes_token_invalid(store: RefreshTokenStore):
    user_id = uuid.uuid4()
    raw = "to-delete"
    await store.save(raw, user_id)
    await store.delete(raw)
    assert await store.pop_user_id(raw) is None
