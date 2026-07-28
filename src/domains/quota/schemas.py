from pydantic import BaseModel

from core.quota import QuotaInfo


class QuotasResponse(BaseModel):
    ocr: QuotaInfo
    rag: QuotaInfo
