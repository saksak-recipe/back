import pytest
import fakeredis.aioredis

from core.exception.exceptions import TooManyRequestsException
from core.quota import (
    DailyQuotaStore,
    EMAIL_SEND_DAILY_LIMIT,
    KIND_EMAIL_SEND,
    KIND_OCR,
    KIND_RAG,
    OCR_DAILY_LIMIT,
    RAG_DAILY_LIMIT,
)


@pytest.fixture
async def store():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    s = DailyQuotaStore(redis)
    yield s
    await redis.aclose()


async def test_consume_increments_and_returns_quota(store: DailyQuotaStore):
    q = await store.consume(KIND_EMAIL_SEND, "a@example.com", EMAIL_SEND_DAILY_LIMIT)
    assert q.limit == 3
    assert q.used == 1
    assert q.remaining == 2
    assert q.reset_at.tzinfo is not None


async def test_consume_over_limit_raises_and_does_not_keep_extra(
    store: DailyQuotaStore,
):
    for _ in range(3):
        await store.consume(KIND_EMAIL_SEND, "a@example.com", 3)
    with pytest.raises(TooManyRequestsException) as ei:
        await store.consume(KIND_EMAIL_SEND, "a@example.com", 3)
    assert ei.value.status_code == 429
    key = store._key(KIND_EMAIL_SEND, "a@example.com")
    used = int(await store._redis.get(key))
    assert used == 3


async def test_subjects_are_independent(store: DailyQuotaStore):
    await store.consume(KIND_EMAIL_SEND, "a@example.com", 3)
    q = await store.consume(KIND_EMAIL_SEND, "b@example.com", 3)
    assert q.used == 1


async def test_peek_missing_key_returns_zero_used(store: DailyQuotaStore):
    q = await store.peek(KIND_OCR, "user-1", OCR_DAILY_LIMIT)
    assert q.limit == 3
    assert q.used == 0
    assert q.remaining == 3
    assert q.reset_at.tzinfo is not None


async def test_peek_does_not_increment(store: DailyQuotaStore):
    await store.peek(KIND_RAG, "user-1", RAG_DAILY_LIMIT)
    q = await store.peek(KIND_RAG, "user-1", RAG_DAILY_LIMIT)
    assert q.used == 0
    assert q.remaining == 7


async def test_peek_matches_consume_used(store: DailyQuotaStore):
    await store.consume(KIND_OCR, "user-1", OCR_DAILY_LIMIT)
    await store.consume(KIND_OCR, "user-1", OCR_DAILY_LIMIT)
    q = await store.peek(KIND_OCR, "user-1", OCR_DAILY_LIMIT)
    assert q.used == 2
    assert q.remaining == 1
