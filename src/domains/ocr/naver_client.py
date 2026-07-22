import json
import time
import uuid

import httpx

from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException

_FORMAT_MAP = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp"}


async def extract_text(
    image_bytes: bytes,
    *,
    format: str,
    api_url: str,
    secret_key: str,
) -> str:
    if not api_url or not secret_key:
        raise ExternalServiceException(
            detail="Naver OCR 설정이 없습니다.",
            code=ErrorCode.OCR_FAILED,
        )

    clova_format = _FORMAT_MAP.get(format.lower())
    if clova_format is None:
        raise ExternalServiceException(
            detail="지원하지 않는 이미지 형식입니다.",
            code=ErrorCode.OCR_FAILED,
        )

    message = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "images": [{"format": clova_format, "name": "receipt"}],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                api_url,
                headers={"X-OCR-SECRET": secret_key},
                data={"message": json.dumps(message)},
                files={"file": ("receipt." + clova_format, image_bytes, f"image/{format}")},
            )
    except httpx.HTTPError as exc:
        raise ExternalServiceException(
            detail="Naver OCR 서버와 통신에 실패했습니다.",
            code=ErrorCode.OCR_FAILED,
        ) from exc

    if response.status_code != httpx.codes.OK:
        raise ExternalServiceException(
            detail="Naver OCR 요청이 실패했습니다.",
            code=ErrorCode.OCR_FAILED,
        )

    try:
        payload = response.json()
        fields = payload["images"][0].get("fields") or []
        lines = [f.get("inferText", "").strip() for f in fields]
        return "\n".join(line for line in lines if line)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ExternalServiceException(
            detail="Naver OCR 응답을 해석하지 못했습니다.",
            code=ErrorCode.OCR_FAILED,
        ) from exc
