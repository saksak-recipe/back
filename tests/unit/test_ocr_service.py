from unittest.mock import AsyncMock

import pytest

from core.exception.exceptions import BadRequestException
from domains.ocr.service import OcrService


@pytest.mark.asyncio
async def test_parse_receipt_happy_path():
    extract = AsyncMock(return_value="왕교자\n계란")
    parse = AsyncMock(return_value=["왕교자", "계란"])
    service = OcrService(
        api_url="https://ocr.test",
        secret_key="secret",
        openai_api_key="openai",
        llm_model="gpt-4o-mini",
        extract_text_fn=extract,
        parse_receipt_text_fn=parse,
    )

    result = await service.parse_receipt(
        b"img",
        content_type="image/jpeg",
        filename="receipt.jpg",
    )

    assert result.ingredients == ["왕교자", "계란"]
    extract.assert_awaited_once()
    parse.assert_awaited_once_with(
        "왕교자\n계란",
        api_key="openai",
        model="gpt-4o-mini",
    )


@pytest.mark.asyncio
async def test_parse_receipt_rejects_oversize():
    service = OcrService(
        api_url="u",
        secret_key="s",
        openai_api_key="k",
        llm_model="m",
        extract_text_fn=AsyncMock(),
        parse_receipt_text_fn=AsyncMock(),
    )
    with pytest.raises(BadRequestException):
        await service.parse_receipt(
            b"x" * (10 * 1024 * 1024 + 1),
            content_type="image/png",
            filename="big.png",
        )


@pytest.mark.asyncio
async def test_parse_receipt_rejects_bad_type():
    service = OcrService(
        api_url="u",
        secret_key="s",
        openai_api_key="k",
        llm_model="m",
        extract_text_fn=AsyncMock(),
        parse_receipt_text_fn=AsyncMock(),
    )
    with pytest.raises(BadRequestException):
        await service.parse_receipt(
            b"x",
            content_type="application/pdf",
            filename="a.pdf",
        )
