import pytest
import fakeredis.aioredis
from datetime import datetime
from zoneinfo import ZoneInfo

from core.exception.exceptions import TooManyRequestsException
from core.quota import (
    DailyQuotaStore,
    EMAIL_SEND_DAILY_LIMIT,
    KIND_EMAIL_SEND,
    kst_next_midnight,
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
    peek = await store.peek(KIND_EMAIL_SEND, "a@example.com", 3)
    assert peek.used == 3
    assert peek.remaining == 0


async def test_subjects_are_independent(store: DailyQuotaStore):
    await store.consume(KIND_EMAIL_SEND, "a@example.com", 3)
    q = await store.consume(KIND_EMAIL_SEND, "b@example.com", 3)
    assert q.used == 1
