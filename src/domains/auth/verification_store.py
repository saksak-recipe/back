import hashlib
import json
import secrets

from redis.asyncio import Redis
from redis.exceptions import WatchError

from core.exception.codes import ErrorCode
from core.exception.exceptions import BadRequestException, ExternalServiceException

PURPOSE_SIGNUP = "signup"
PURPOSE_PASSWORD_RESET = "password_reset"
CODE_TTL_SECONDS = 180
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

    def _resend_used_key(self, purpose: str, email: str) -> str:
        return f"email_code_resend_used:{purpose}:{email.lower()}"

    async def _store_code(self, purpose: str, email: str) -> str:
        code = generate_email_code()
        payload = json.dumps({"hash": hash_email_code(code), "attempts": 0})
        await self._redis.set(
            self._code_key(purpose, email),
            payload,
            ex=CODE_TTL_SECONDS,
        )
        return code

    async def issue(self, purpose: str, email: str) -> str:
        email = email.lower()
        try:
            await self._redis.delete(self._resend_used_key(purpose, email))
            return await self._store_code(purpose, email)
        except Exception as exc:
            raise ExternalServiceException("인증 코드 저장에 실패했습니다.") from exc

    async def resend(self, purpose: str, email: str) -> str:
        email = email.lower()
        resend_key = self._resend_used_key(purpose, email)
        try:
            resend_set = await self._redis.set(
                resend_key,
                "1",
                ex=CODE_TTL_SECONDS,
                nx=True,
            )
            if not resend_set:
                raise BadRequestException(
                    code=ErrorCode.VERIFICATION_COOLDOWN,
                    detail="인증 코드 재발송은 1회만 가능합니다.",
                )
            return await self._store_code(purpose, email)
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
                            pipe.delete(self._resend_used_key(purpose, email))
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
