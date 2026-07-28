from pydantic import BaseModel, Field

from core.quota import QuotaInfo


class OcrReceiptResponse(BaseModel):
    ingredients: list[str] = Field(default_factory=list)
    quota: QuotaInfo


class _LlmIngredientsPayload(BaseModel):
    ingredients: list[str] = Field(default_factory=list)
