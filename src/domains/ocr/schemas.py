from pydantic import BaseModel, Field


class OcrReceiptResponse(BaseModel):
    ingredients: list[str] = Field(default_factory=list)


class _LlmIngredientsPayload(BaseModel):
    ingredients: list[str] = Field(default_factory=list)
