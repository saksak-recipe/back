from dataclasses import asdict, dataclass

from redis.asyncio import Redis

from core.exception.codes import ErrorCode
from core.exception.exceptions import ConflictException, ExternalServiceException

PENDING_KAKAO_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class PendingKakaoSignup:
    kakao_id: str
    email: str
    nickname: str


class KakaoPendingStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _email_key(self, email: str) -> str:
        return f"kakao_pending:{email.lower()}"

    def _kakao_key(self, kakao_id: str) -> str:
        return f"kakao_pending_id:{kakao_id}"

    def _nickname_key(self, nickname: str) -> str:
        return f"kakao_pending_nickname:{nickname.lower()}"

    async def upsert(self, pending: PendingKakaoSignup) -> None:
        email = pending.email.lower()
        email_key = self._email_key(email)
        kakao_key = self._kakao_key(pending.kakao_id)
        nickname_key = self._nickname_key(pending.nickname)
        try:
            existing_email_for_nick = await self._redis.get(nickname_key)
            if (
                existing_email_for_nick is not None
                and existing_email_for_nick.lower() != email
            ):
                raise ConflictException(
                    code=ErrorCode.NICKNAME_CONFLICT,
                    detail="이미 사용 중인 닉네임 입니다.(대소문자 구별)",
                )

            current = await self._redis.hgetall(email_key)
            pipe = self._redis.pipeline()
            if current:
                old_nick = current.get("nickname")
                old_kakao = current.get("kakao_id")
                if old_nick and old_nick.lower() != pending.nickname.lower():
                    pipe.delete(self._nickname_key(old_nick))
                if old_kakao and old_kakao != pending.kakao_id:
                    pipe.delete(self._kakao_key(old_kakao))

            mapping = asdict(pending)
            mapping["email"] = email
            pipe.hset(email_key, mapping=mapping)
            pipe.expire(email_key, PENDING_KAKAO_TTL_SECONDS)
            pipe.set(kakao_key, email, ex=PENDING_KAKAO_TTL_SECONDS)
            pipe.set(nickname_key, email, ex=PENDING_KAKAO_TTL_SECONDS)
            await pipe.execute()
        except ConflictException:
            raise
        except Exception as exc:
            raise ExternalServiceException(
                detail="카카오 가입 임시 정보 저장에 실패했습니다."
            ) from exc

    async def get_by_email(self, email: str) -> PendingKakaoSignup | None:
        try:
            data = await self._redis.hgetall(self._email_key(email))
            if not data:
                return None
            return PendingKakaoSignup(**data)
        except Exception as exc:
            raise ExternalServiceException(
                detail="카카오 가입 임시 정보 조회에 실패했습니다."
            ) from exc

    async def pop_by_email(self, email: str) -> PendingKakaoSignup | None:
        email = email.lower()
        email_key = self._email_key(email)
        try:
            raw = await self._redis.hgetall(email_key)
            if not raw:
                return None
            pending = PendingKakaoSignup(**raw)
            pipe = self._redis.pipeline()
            pipe.delete(email_key)
            pipe.delete(self._kakao_key(pending.kakao_id))
            pipe.delete(self._nickname_key(pending.nickname))
            await pipe.execute()
            return pending
        except Exception as exc:
            raise ExternalServiceException(
                detail="카카오 가입 임시 정보 처리에 실패했습니다."
            ) from exc
