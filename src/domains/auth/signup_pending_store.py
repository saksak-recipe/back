from dataclasses import asdict, dataclass

from redis.asyncio import Redis

from core.exception.codes import ErrorCode
from core.exception.exceptions import ConflictException, ExternalServiceException

PENDING_SIGNUP_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class PendingSignup:
    email: str
    password_hash: str
    nickname: str


class SignupPendingStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _signup_key(self, email: str) -> str:
        return f"signup_pending:{email.lower()}"

    def _nickname_key(self, nickname: str) -> str:
        return f"signup_pending_nickname:{nickname.lower()}"

    async def upsert(self, pending: PendingSignup) -> None:
        email = pending.email.lower()
        signup_key = self._signup_key(email)
        nickname_key = self._nickname_key(pending.nickname)
        try:
            current_nickname = await self._redis.hget(signup_key, "nickname")
            existing_email = await self._redis.get(nickname_key)
            if existing_email is not None and existing_email.lower() != email:
                raise ConflictException(
                    code=ErrorCode.NICKNAME_CONFLICT,
                    detail="이미 사용 중인 닉네임 입니다.(대소문자 구별)",
                )

            pipe = self._redis.pipeline()
            if (
                current_nickname
                and current_nickname.lower() != pending.nickname.lower()
            ):
                pipe.delete(self._nickname_key(current_nickname))

            pipe.hset(signup_key, mapping=asdict(pending))
            pipe.expire(signup_key, PENDING_SIGNUP_TTL_SECONDS)
            pipe.set(
                nickname_key,
                email,
                ex=PENDING_SIGNUP_TTL_SECONDS,
            )
            await pipe.execute()
        except ConflictException:
            raise
        except Exception as exc:
            raise ExternalServiceException(
                detail="회원가입 임시 정보 저장에 실패했습니다."
            ) from exc

    async def get(self, email: str) -> PendingSignup | None:
        try:
            data = await self._redis.hgetall(self._signup_key(email))
            if not data:
                return None
            return PendingSignup(**data)
        except Exception as exc:
            raise ExternalServiceException(
                detail="회원가입 임시 정보 조회에 실패했습니다."
            ) from exc

    async def pop(self, email: str) -> PendingSignup | None:
        email = email.lower()
        signup_key = self._signup_key(email)
        try:
            raw = await self._redis.hgetall(signup_key)
            if not raw:
                return None

            pending = PendingSignup(**raw)
            pipe = self._redis.pipeline()
            pipe.delete(signup_key)
            pipe.delete(self._nickname_key(pending.nickname))
            await pipe.execute()
            return pending
        except Exception as exc:
            raise ExternalServiceException(
                detail="회원가입 임시 정보 처리에 실패했습니다."
            ) from exc
