from unittest.mock import AsyncMock

import pytest
import uuid6

from core.exception.exceptions import BadRequestException
from core.quota import KIND_OCR, OCR_DAILY_LIMIT, QuotaInfo, kst_next_midnight
from domains.ocr.service import OcrService


def _quota_mock() -> AsyncMock:
    quota = AsyncMock()
    quota.consume = AsyncMock(
        return_value=QuotaInfo(
            limit=3, used=1, remaining=2, reset_at=kst_next_midnight()
        )
    )
    return quota


@pytest.mark.asyncio
async def test_parse_receipt_happy_path():
    extract = AsyncMock(return_value="왕교자\n계란")
    parse = AsyncMock(return_value=["왕교자", "계란"])
    quota = _quota_mock()
    user_id = uuid6.uuid7()
    service = OcrService(
        api_url="https://ocr.test",
        secret_key="secret",
        openai_api_key="openai",
        llm_model="gpt-4o-mini",
        extract_text_fn=extract,
        parse_receipt_text_fn=parse,
        daily_quota_store=quota,
        user_id=user_id,
    )

    result = await service.parse_receipt(
        b"img",
        content_type="image/jpeg",
        filename="receipt.jpg",
    )

    assert result.ingredients == ["왕교자", "계란"]
    assert result.quota is not None
    assert result.quota.remaining == 2
    quota.consume.assert_awaited_once_with(KIND_OCR, str(user_id), OCR_DAILY_LIMIT)
    extract.assert_awaited_once()
    parse.assert_awaited_once_with(
        "왕교자\n계란",
        api_key="openai",
        model="gpt-4o-mini",
    )


@pytest.mark.asyncio
async def test_parse_receipt_consumes_quota():
    extract = AsyncMock(return_value="계란")
    parse = AsyncMock(return_value=["계란"])
    quota = _quota_mock()
    user_id = uuid6.uuid7()
    service = OcrService(
        api_url="https://ocr.test",
        secret_key="secret",
        openai_api_key="openai",
        llm_model="gpt-4o-mini",
        extract_text_fn=extract,
        parse_receipt_text_fn=parse,
        daily_quota_store=quota,
        user_id=user_id,
    )
    result = await service.parse_receipt(b"img", "image/jpeg", "a.jpg")
    quota.consume.assert_awaited_once_with(KIND_OCR, str(user_id), OCR_DAILY_LIMIT)
    assert result.quota is not None
    assert result.quota.remaining == 2
    extract.assert_awaited_once()


@pytest.mark.asyncio
async def test_parse_receipt_bad_request_skips_quota():
    quota = AsyncMock()
    service = OcrService(
        api_url="u",
        secret_key="s",
        openai_api_key="k",
        llm_model="m",
        extract_text_fn=AsyncMock(),
        parse_receipt_text_fn=AsyncMock(),
        daily_quota_store=quota,
        user_id=uuid6.uuid7(),
    )
    with pytest.raises(BadRequestException):
        await service.parse_receipt(b"", "image/jpeg", "a.jpg")
    quota.consume.assert_not_called()


@pytest.mark.asyncio
async def test_parse_receipt_rejects_oversize():
    quota = AsyncMock()
    service = OcrService(
        api_url="u",
        secret_key="s",
        openai_api_key="k",
        llm_model="m",
        extract_text_fn=AsyncMock(),
        parse_receipt_text_fn=AsyncMock(),
        daily_quota_store=quota,
        user_id=uuid6.uuid7(),
    )
    with pytest.raises(BadRequestException):
        await service.parse_receipt(
            b"x" * (10 * 1024 * 1024 + 1),
            content_type="image/png",
            filename="big.png",
        )
    quota.consume.assert_not_called()


@pytest.mark.asyncio
async def test_parse_receipt_rejects_bad_type():
    quota = AsyncMock()
    service = OcrService(
        api_url="u",
        secret_key="s",
        openai_api_key="k",
        llm_model="m",
        extract_text_fn=AsyncMock(),
        parse_receipt_text_fn=AsyncMock(),
        daily_quota_store=quota,
        user_id=uuid6.uuid7(),
    )
    with pytest.raises(BadRequestException):
        await service.parse_receipt(
            b"x",
            content_type="application/pdf",
            filename="a.pdf",
        )
    quota.consume.assert_not_called()
