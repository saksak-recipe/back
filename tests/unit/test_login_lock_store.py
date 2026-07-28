import pytest
import fakeredis.aioredis

from domains.auth.login_lock_store import LOGIN_FAIL_LIMIT, LoginLockStore


@pytest.fixture
async def store():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = LoginLockStore(redis)
    yield s
    await redis.aclose()


async def test_not_locked_initially(store: LoginLockStore):
    assert await store.is_locked("a@example.com") is False


async def test_locked_after_five_failures(store: LoginLockStore):
    for i in range(LOGIN_FAIL_LIMIT):
        n = await store.record_failure("a@example.com")
        assert n == i + 1
    assert await store.is_locked("a@example.com") is True


async def test_clear_removes_lock(store: LoginLockStore):
    for _ in range(LOGIN_FAIL_LIMIT):
        await store.record_failure("a@example.com")
    await store.clear("a@example.com")
    assert await store.is_locked("a@example.com") is False
