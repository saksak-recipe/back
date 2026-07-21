from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from core.config import settings
from core.exception.exceptions import ExternalServiceException, TooManyRequestsException
from domains.ingredient.scope import RecipeScope

KST = ZoneInfo("Asia/Seoul")


class AiQuotaStore:
    def __init__(
        self,
        redis: Redis,
        daily_limit: int | None = None,
    ) -> None:
        self._redis = redis
        self._daily_limit = (
            daily_limit if daily_limit is not None else settings.AI_QUOTA_DAILY_LIMIT
        )

    def key(
        self,
        scope: RecipeScope,
        owner_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> str:
        current = now or datetime.now(KST)
        if current.tzinfo is None:
            current = current.replace(tzinfo=KST)
        else:
            current = current.astimezone(KST)
        day = current.strftime("%Y%m%d")
        return f"ai_quota:{scope.value}:{owner_id}:{day}"

    def seconds_until_kst_midnight(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(KST)
        if current.tzinfo is None:
            current = current.replace(tzinfo=KST)
        else:
            current = current.astimezone(KST)
        tomorrow = (current + timedelta(days=1)).date()
        midnight = datetime(
            tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=KST
        )
        seconds = int((midnight - current).total_seconds())
        return max(seconds, 1)

    async def consume(self, scope: RecipeScope, owner_id: uuid.UUID) -> int:
        redis_key = self.key(scope, owner_id)
        try:
            count = await self._redis.incr(redis_key)
            if count == 1:
                await self._redis.expire(
                    redis_key, self.seconds_until_kst_midnight()
                )
            if count > self._daily_limit:
                await self._redis.decr(redis_key)
                raise TooManyRequestsException(
                    detail=(
                        f"오늘 AI 레시피 생성 한도"
                        f"({self._daily_limit}회)를 초과했습니다."
                    )
                )
            return int(count)
        except TooManyRequestsException:
            raise
        except Exception as exc:
            raise ExternalServiceException(
                detail="AI 사용량 확인에 실패했습니다."
            ) from exc
