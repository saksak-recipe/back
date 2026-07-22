import json

import openai
from openai import AsyncOpenAI
from pydantic import ValidationError

from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException
from domains.ocr.schemas import _LlmIngredientsPayload

INGREDIENT_NAME_MAX_LEN = 45

SYSTEM_PROMPT = """당신은 마트 영수증 OCR 텍스트에서 식재료만 추출하는 도우미입니다.
규칙:
1. 식재료(식품)만 포함하세요. 봉투, 배달비, 할인, 세제, 포인트, 쿠폰 등은 제외합니다.
2. 이름은 짧은 일반명으로 정규화하세요. 브랜드·용량·프로모션 문구를 제거합니다.
   예: "CJ 비비고 왕교자 1.05kg" → "왕교자"
3. 중복을 제거하고, OCR에 나온 순서를 유지합니다.
4. 반드시 JSON만 출력합니다: {"ingredients": ["이름1", "이름2"]}
5. 식재료가 없으면 {"ingredients": []} 입니다."""


def _normalize_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in names:
        name = raw.strip()[:INGREDIENT_NAME_MAX_LEN]
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


async def parse_receipt_text(
    ocr_text: str,
    *,
    api_key: str,
    model: str,
) -> list[str]:
    client = AsyncOpenAI(api_key=api_key)
    try:
        response = await client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": ocr_text},
            ],
        )
        content = response.choices[0].message.content or ""
        payload = _LlmIngredientsPayload.model_validate(json.loads(content))
        return _normalize_names(payload.ingredients)
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError, IndexError, TypeError) as exc:
        raise ExternalServiceException(
            detail="영수증 식재료 분석 중 오류가 발생했습니다.",
            code=ErrorCode.OCR_LLM_FAILED,
        ) from exc
