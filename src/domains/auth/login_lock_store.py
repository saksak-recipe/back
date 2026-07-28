from redis.asyncio import Redis

LOGIN_FAIL_LIMIT = 5
_FAIL_TTL_SECONDS = 24 * 60 * 60


class LoginLockStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, email: str) -> str:
        return f"login_fail:{email.lower()}"

    async def is_locked(self, email: str) -> bool:
        raw = await self._redis.get(self._key(email))
        if raw is None:
            return False
        return int(raw) >= LOGIN_FAIL_LIMIT

    async def record_failure(self, email: str) -> int:
        key = self._key(email)
        n = await self._redis.incr(key)
        if n == 1:
            await self._redis.expire(key, _FAIL_TTL_SECONDS)
        return int(n)

    async def clear(self, email: str) -> None:
        await self._redis.delete(self._key(email))
