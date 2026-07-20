from uuid import UUID

from redis.asyncio import Redis

from core.exception.exceptions import ExternalServiceException
from core.security import hash_refresh_token


class RefreshTokenStore:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    def _key(self, raw_token: str) -> str:
        return f"refresh:{hash_refresh_token(raw_token)}"

    async def save(self, raw_token: str, user_id: UUID) -> None:
        try:
            await self._redis.set(self._key(raw_token), str(user_id), ex=self._ttl)
        except Exception as exc:
            raise ExternalServiceException("세션 저장에 실패했습니다.") from exc

    async def pop_user_id(self, raw_token: str) -> UUID | None:
        key = self._key(raw_token)
        try:
            user_id = await self._redis.get(key)
            if user_id is None:
                return None
            await self._redis.delete(key)
            return UUID(user_id)
        except Exception as exc:
            raise ExternalServiceException("세션 조회에 실패했습니다.") from exc

    async def delete(self, raw_token: str) -> None:
        try:
            await self._redis.delete(self._key(raw_token))
        except Exception as exc:
            raise ExternalServiceException("세션 삭제에 실패했습니다.") from exc
