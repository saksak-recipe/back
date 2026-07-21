import hashlib
import json
import secrets

from redis.asyncio import Redis
from redis.exceptions import WatchError

from core.exception.codes import ErrorCode
from core.exception.exceptions import BadRequestException, ExternalServiceException

PURPOSE_SIGNUP = "signup"
PURPOSE_PASSWORD_RESET = "password_reset"
CODE_TTL_SECONDS = 600
COOLDOWN_SECONDS = 60
MAX_ATTEMPTS = 5


def hash_email_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def generate_email_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


class VerificationCodeStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _code_key(self, purpose: str, email: str) -> str:
        return f"email_code:{purpose}:{email.lower()}"

    def _cooldown_key(self, purpose: str, email: str) -> str:
        return f"email_code_cooldown:{purpose}:{email.lower()}"

    async def issue(self, purpose: str, email: str) -> str:
        email = email.lower()
        cooldown_key = self._cooldown_key(purpose, email)
        try:
            cooldown_set = await self._redis.set(
                cooldown_key,
                "1",
                ex=COOLDOWN_SECONDS,
                nx=True,
            )
            if not cooldown_set:
                raise BadRequestException(
                    code=ErrorCode.VERIFICATION_COOLDOWN,
                    detail="인증 코드 재발송은 잠시 후 다시 시도해 주세요.",
                )
            code = generate_email_code()
            payload = json.dumps(
                {"hash": hash_email_code(code), "attempts": 0}
            )
            await self._redis.set(
                self._code_key(purpose, email),
                payload,
                ex=CODE_TTL_SECONDS,
            )
            return code
        except BadRequestException:
            raise
        except Exception as exc:
            raise ExternalServiceException("인증 코드 저장에 실패했습니다.") from exc

    async def verify(self, purpose: str, email: str, code: str) -> None:
        email = email.lower()
        key = self._code_key(purpose, email)
        try:
            while True:
                try:
                    async with self._redis.pipeline() as pipe:
                        await pipe.watch(key)
                        raw = await pipe.get(key)
                        if raw is None:
                            raise BadRequestException(
                                code=ErrorCode.INVALID_VERIFICATION_CODE,
                                detail=(
                                    "인증 코드가 올바르지 않거나 만료되었습니다."
                                ),
                            )

                        data = json.loads(raw)
                        if data["hash"] == hash_email_code(code):
                            pipe.multi()
                            pipe.delete(key)
                            await pipe.execute()
                            return

                        attempts = int(data.get("attempts", 0)) + 1
                        if attempts >= MAX_ATTEMPTS:
                            pipe.multi()
                            pipe.delete(key)
                        else:
                            ttl = await pipe.ttl(key)
                            if ttl <= 0:
                                raise BadRequestException(
                                    code=ErrorCode.INVALID_VERIFICATION_CODE,
                                    detail=(
                                        "인증 코드가 올바르지 않거나 "
                                        "만료되었습니다."
                                    ),
                                )
                            data["attempts"] = attempts
                            pipe.multi()
                            pipe.set(key, json.dumps(data), ex=ttl)

                        await pipe.execute()
                        raise BadRequestException(
                            code=ErrorCode.INVALID_VERIFICATION_CODE,
                            detail="인증 코드가 올바르지 않거나 만료되었습니다.",
                        )
                except WatchError:
                    continue
        except BadRequestException:
            raise
        except Exception as exc:
            raise ExternalServiceException("인증 코드 검증에 실패했습니다.") from exc
