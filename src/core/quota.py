from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from redis.asyncio import Redis

from core.exception.codes import ErrorCode
from core.exception.exceptions import TooManyRequestsException

KST = ZoneInfo("Asia/Seoul")

EMAIL_SEND_DAILY_LIMIT = 3
OCR_DAILY_LIMIT = 3
RAG_DAILY_LIMIT = 7

KIND_EMAIL_SEND = "email_send"
KIND_OCR = "ocr"
KIND_RAG = "rag"

_KIND_ERROR = {
    KIND_EMAIL_SEND: (
        ErrorCode.EMAIL_SEND_LIMIT_EXCEEDED,
        "인증 메일 발송 한도를 초과했습니다. 내일 다시 시도해 주세요.",
    ),
    KIND_OCR: (
        ErrorCode.OCR_DAILY_LIMIT_EXCEEDED,
        "OCR 일일 사용 한도를 초과했습니다.",
    ),
    KIND_RAG: (
        ErrorCode.RAG_DAILY_LIMIT_EXCEEDED,
        "레시피 추천 일일 사용 한도를 초과했습니다.",
    ),
}


class QuotaInfo(BaseModel):
    limit: int
    used: int
    remaining: int
    reset_at: datetime


def kst_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(KST)
    if now.tzinfo is None:
        return now.replace(tzinfo=KST)
    return now.astimezone(KST)


def kst_today_yyyymmdd(now: datetime | None = None) -> str:
    return kst_now(now).strftime("%Y%m%d")


def kst_next_midnight(now: datetime | None = None) -> datetime:
    local = kst_now(now)
    tomorrow = local.date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=KST)


def _ttl_seconds_until_reset(now: datetime | None = None) -> int:
    local = kst_now(now)
    reset = kst_next_midnight(local)
    return max(int((reset - local).total_seconds()), 1)


class DailyQuotaStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    def _key(self, kind: str, subject: str) -> str:
        return f"quota:{kind}:{subject.lower()}:{kst_today_yyyymmdd()}"

    def _snapshot(self, used: int, limit: int) -> QuotaInfo:
        used = max(0, used)
        return QuotaInfo(
            limit=limit,
            used=used,
            remaining=max(0, limit - used),
            reset_at=kst_next_midnight(),
        )

    async def consume(self, kind: str, subject: str, limit: int) -> QuotaInfo:
        key = self._key(kind, subject)
        used = await self._redis.incr(key)
        if used == 1:
            await self._redis.expire(key, _ttl_seconds_until_reset())
        if used > limit:
            await self._redis.decr(key)
            code, detail = _KIND_ERROR[kind]
            snap = self._snapshot(limit, limit)
            raise TooManyRequestsException(
                code=code,
                detail=detail,
                extra={
                    "limit": snap.limit,
                    "remaining": 0,
                    "reset_at": snap.reset_at.isoformat(),
                },
            )
        return self._snapshot(used, limit)

    async def peek(self, kind: str, subject: str, limit: int) -> QuotaInfo:
        key = self._key(kind, subject)
        raw = await self._redis.get(key)
        used = int(raw) if raw is not None else 0
        return self._snapshot(used, limit)

    async def peek(self, kind: str, subject: str, limit: int) -> QuotaInfo:
        key = self._key(kind, subject)
        raw = await self._redis.get(key)
        used = int(raw) if raw is not None else 0
        return self._snapshot(used, limit)
