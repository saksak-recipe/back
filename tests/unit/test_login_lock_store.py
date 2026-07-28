import pytest
import fakeredis.aioredis
from unittest.mock import AsyncMock

from core.exception.exceptions import ExternalServiceException
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


async def test_locked_key_has_no_ttl(store: LoginLockStore):
    email = "a@example.com"
    redis = store._redis
    key = store._key(email)

    for i in range(LOGIN_FAIL_LIMIT - 1):
        await store.record_failure(email)
        ttl = await redis.ttl(key)
        assert ttl > 0, f"partial failure {i + 1} should keep TTL"

    await store.record_failure(email)
    assert await store.is_locked(email) is True
    assert await redis.ttl(key) == -1


async def test_redis_errors_raise_external_service_exception():
    redis = AsyncMock()
    redis.get.side_effect = RuntimeError("redis down")
    store = LoginLockStore(redis)

    with pytest.raises(ExternalServiceException):
        await store.is_locked("a@example.com")

    redis.incr.side_effect = RuntimeError("redis down")
    with pytest.raises(ExternalServiceException):
        await store.record_failure("a@example.com")

    redis.delete.side_effect = RuntimeError("redis down")
    with pytest.raises(ExternalServiceException):
        await store.clear("a@example.com")
