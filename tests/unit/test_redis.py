from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core import redis as redis_module
from core.redis import close_redis, get_redis, init_redis


@pytest.fixture(autouse=True)
async def reset_redis():
    redis_module._redis = None
    yield
    redis_module._redis = None


async def test_init_redis_ping_failure_does_not_raise():
    mock_client = MagicMock()
    mock_client.ping = AsyncMock(side_effect=ConnectionError("redis down"))
    mock_client.aclose = AsyncMock()

    with patch("core.redis.Redis.from_url", return_value=mock_client):
        await init_redis()

    assert get_redis() is mock_client
    await close_redis()
