from redis.asyncio import Redis

from core.exception.exceptions import ExternalServiceException

LOGIN_FAIL_LIMIT = 5
_FAIL_TTL_SECONDS = 24 * 60 * 60


class LoginLockStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, email: str) -> str:
        return f"login_fail:{email.lower()}"

    async def is_locked(self, email: str) -> bool:
        try:
            raw = await self._redis.get(self._key(email))
        except Exception as exc:
            raise ExternalServiceException(
                "로그인 잠금 상태 조회에 실패했습니다."
            ) from exc
        if raw is None:
            return False
        return int(raw) >= LOGIN_FAIL_LIMIT

    async def record_failure(self, email: str) -> int:
        key = self._key(email)
        try:
            n = await self._redis.incr(key)
            if n >= LOGIN_FAIL_LIMIT:
                # Locked until password-reset clear(); do not auto-expire via TTL.
                await self._redis.persist(key)
            else:
                await self._redis.expire(key, _FAIL_TTL_SECONDS)
            return int(n)
        except Exception as exc:
            raise ExternalServiceException(
                "로그인 실패 기록에 실패했습니다."
            ) from exc

    async def clear(self, email: str) -> None:
        try:
            await self._redis.delete(self._key(email))
        except Exception as exc:
            raise ExternalServiceException(
                "로그인 잠금 해제에 실패했습니다."
            ) from exc
