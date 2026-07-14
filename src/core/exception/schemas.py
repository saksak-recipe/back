from pydantic import BaseModel, Field
from typing import Any


class GlobalErrorResponse(BaseModel):
    status_code: int = Field(..., examples=[400])
    code: str = Field(..., examples=["ERROR_CODE_STRING"])
    detail: str = Field(..., examples=["에러에 대한 상세 메시지입니다."])
    errors: list[Any] | None = Field(None, description="유효성 검사 에러 시 상세 내용")
