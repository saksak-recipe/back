import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException, TooManyRequestsException
from domains.ai_recipe.quota import AiQuotaStore
from domains.ingredient.scope import RecipeScope

KST = ZoneInfo("Asia/Seoul")
OWNER = uuid.UUID("11111111-1111-1111-1111-111111111111")
GROUP = uuid.UUID("22222222-2222-2222-2222-222222222222")


def test_key_uses_scope_and_kst_date():
    redis = MagicMock()
    store = AiQuotaStore(redis, daily_limit=15)
    now = datetime(2026, 7, 21, 23, 30, tzinfo=KST)

    assert (
        store.key(RecipeScope.personal, OWNER, now=now)
        == f"ai_quota:personal:{OWNER}:20260721"
    )
    assert (
        store.key(RecipeScope.group, GROUP, now=now)
        == f"ai_quota:group:{GROUP}:20260721"
    )


def test_seconds_until_kst_midnight():
    redis = MagicMock()
    store = AiQuotaStore(redis, daily_limit=15)
    now = datetime(2026, 7, 21, 23, 0, 0, tzinfo=KST)

    assert store.seconds_until_kst_midnight(now=now) == 3600


async def test_consume_increments_and_sets_ttl_on_first():
    redis = AsyncMock()
    redis.incr.return_value = 1
    redis.expire.return_value = True
    store = AiQuotaStore(redis, daily_limit=15)

    count = await store.consume(RecipeScope.personal, OWNER)

    assert count == 1
    redis.incr.assert_awaited_once()
    redis.expire.assert_awaited_once()
    assert redis.expire.await_args.args[1] > 0


async def test_consume_raises_when_over_limit_and_decrs():
    redis = AsyncMock()
    redis.incr.return_value = 16
    redis.decr.return_value = 15
    store = AiQuotaStore(redis, daily_limit=15)

    with pytest.raises(TooManyRequestsException) as exc_info:
        await store.consume(RecipeScope.personal, OWNER)

    assert exc_info.value.code == ErrorCode.AI_QUOTA_EXCEEDED
    redis.decr.assert_awaited_once()


async def test_consume_personal_and_group_use_different_keys():
    redis = AsyncMock()
    redis.incr.return_value = 1
    redis.expire.return_value = True
    store = AiQuotaStore(redis, daily_limit=15)

    await store.consume(RecipeScope.personal, OWNER)
    await store.consume(RecipeScope.group, GROUP)

    keys = [call.args[0] for call in redis.incr.await_args_list]
    assert keys[0].startswith("ai_quota:personal:")
    assert keys[1].startswith("ai_quota:group:")
    assert keys[0] != keys[1]


async def test_consume_redis_failure_is_fail_closed():
    redis = AsyncMock()
    redis.incr.side_effect = ConnectionError("down")
    store = AiQuotaStore(redis, daily_limit=15)

    with pytest.raises(ExternalServiceException):
        await store.consume(RecipeScope.personal, OWNER)
