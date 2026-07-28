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

    def _key_from_hash(self, token_hash: str) -> str:
        return f"refresh:{token_hash}"

    def _user_set_key(self, user_id: UUID) -> str:
        return f"refresh_user:{user_id}"

    async def save(self, raw_token: str, user_id: UUID) -> None:
        token_hash = hash_refresh_token(raw_token)
        key = self._key_from_hash(token_hash)
        user_set = self._user_set_key(user_id)
        try:
            pipe = self._redis.pipeline()
            pipe.set(key, str(user_id), ex=self._ttl)
            pipe.sadd(user_set, token_hash)
            pipe.expire(user_set, self._ttl)
            await pipe.execute()
        except Exception as exc:
            raise ExternalServiceException("세션 저장에 실패했습니다.") from exc

    async def pop_user_id(self, raw_token: str) -> UUID | None:
        token_hash = hash_refresh_token(raw_token)
        key = self._key_from_hash(token_hash)
        try:
            user_id_raw = await self._redis.get(key)
            if user_id_raw is None:
                return None
            user_id = UUID(user_id_raw)
            pipe = self._redis.pipeline()
            pipe.delete(key)
            pipe.srem(self._user_set_key(user_id), token_hash)
            await pipe.execute()
            return user_id
        except Exception as exc:
            raise ExternalServiceException("세션 조회에 실패했습니다.") from exc

    async def delete(self, raw_token: str) -> None:
        token_hash = hash_refresh_token(raw_token)
        key = self._key_from_hash(token_hash)
        try:
            user_id_raw = await self._redis.get(key)
            pipe = self._redis.pipeline()
            pipe.delete(key)
            if user_id_raw is not None:
                pipe.srem(self._user_set_key(UUID(user_id_raw)), token_hash)
            await pipe.execute()
        except Exception as exc:
            raise ExternalServiceException("세션 삭제에 실패했습니다.") from exc

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        user_set = self._user_set_key(user_id)
        try:
            token_hashes = await self._redis.smembers(user_set)
            if not token_hashes:
                await self._redis.delete(user_set)
                return
            pipe = self._redis.pipeline()
            for token_hash in token_hashes:
                pipe.delete(self._key_from_hash(token_hash))
            pipe.delete(user_set)
            await pipe.execute()
        except Exception as exc:
            raise ExternalServiceException("세션 일괄 삭제에 실패했습니다.") from exc
