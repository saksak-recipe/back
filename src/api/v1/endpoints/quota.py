from fastapi import APIRouter, Depends

from api.deps import get_current_user, get_daily_quota_store
from core.quota import (
    DailyQuotaStore,
    KIND_OCR,
    KIND_RAG,
    OCR_DAILY_LIMIT,
    RAG_DAILY_LIMIT,
)
from domains.quota.schemas import QuotasResponse
from domains.user.model import User

router = APIRouter(prefix="/quotas", tags=["사용량"])


@router.get(
    "",
    response_model=QuotasResponse,
    summary="일일 사용량 조회",
    description="OCR·레시피 추천 등 기능별 일일 사용량과 잔여 한도를 조회합니다.",
)
async def get_quotas(
    user: User = Depends(get_current_user),
    store: DailyQuotaStore = Depends(get_daily_quota_store),
) -> QuotasResponse:
    subject = str(user.id)
    ocr = await store.peek(KIND_OCR, subject, OCR_DAILY_LIMIT)
    rag = await store.peek(KIND_RAG, subject, RAG_DAILY_LIMIT)
    return QuotasResponse(ocr=ocr, rag=rag)
