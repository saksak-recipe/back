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


async def test_revoke_all_for_user_invalidates_all_tokens(store: RefreshTokenStore):
    user_id = uuid.uuid4()
    other_id = uuid.uuid4()
    await store.save("token-a", user_id)
    await store.save("token-b", user_id)
    await store.save("token-other", other_id)

    await store.revoke_all_for_user(user_id)

    assert await store.pop_user_id("token-a") is None
    assert await store.pop_user_id("token-b") is None
    assert await store.pop_user_id("token-other") == other_id
