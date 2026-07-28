from unittest.mock import AsyncMock

import pytest
import uuid6

from core.exception.exceptions import BadRequestException, ExternalServiceException
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


def _service(
    *,
    extract=None,
    parse=None,
    quota=None,
    user_id=None,
) -> tuple[OcrService, object]:
    uid = user_id or uuid6.uuid7()
    service = OcrService(
        api_url="https://ocr.test",
        secret_key="secret",
        openai_api_key="openai",
        llm_model="gpt-4o-mini",
        extract_text_fn=extract or AsyncMock(return_value="계란"),
        parse_receipt_text_fn=parse or AsyncMock(return_value=["계란"]),
        daily_quota_store=quota or _quota_mock(),
        user_id=uid,
    )
    return service, uid


@pytest.mark.asyncio
async def test_parse_receipt_happy_path():
    order: list[str] = []
    extract = AsyncMock(
        side_effect=lambda *a, **k: (order.append("extract"), "왕교자\n계란")[1]
    )
    parse = AsyncMock(
        side_effect=lambda *a, **k: (order.append("parse"), ["왕교자", "계란"])[1]
    )
    quota = _quota_mock()

    async def consume(*args, **kwargs):
        order.append("consume")
        return QuotaInfo(
            limit=3, used=1, remaining=2, reset_at=kst_next_midnight()
        )

    quota.consume = AsyncMock(side_effect=consume)
    user_id = uuid6.uuid7()
    service, _ = _service(
        extract=extract, parse=parse, quota=quota, user_id=user_id
    )

    result = await service.parse_receipt(
        b"img",
        content_type="image/jpeg",
        filename="receipt.jpg",
    )

    assert result.ingredients == ["왕교자", "계란"]
    assert result.quota is not None
    assert result.quota.remaining == 2
    assert order == ["extract", "parse", "consume"]
    quota.consume.assert_awaited_once_with(KIND_OCR, str(user_id), OCR_DAILY_LIMIT)
    extract.assert_awaited_once()
    parse.assert_awaited_once_with(
        "왕교자\n계란",
        api_key="openai",
        model="gpt-4o-mini",
    )


@pytest.mark.asyncio
async def test_parse_receipt_consumes_quota_after_success():
    extract = AsyncMock(return_value="계란")
    parse = AsyncMock(return_value=["계란"])
    quota = _quota_mock()
    user_id = uuid6.uuid7()
    service, _ = _service(
        extract=extract, parse=parse, quota=quota, user_id=user_id
    )
    result = await service.parse_receipt(b"img", "image/jpeg", "a.jpg")
    quota.consume.assert_awaited_once_with(KIND_OCR, str(user_id), OCR_DAILY_LIMIT)
    assert result.quota is not None
    assert result.quota.remaining == 2
    extract.assert_awaited_once()


@pytest.mark.asyncio
async def test_parse_receipt_skips_quota_when_ocr_fails():
    extract = AsyncMock(side_effect=ExternalServiceException(detail="ocr down"))
    quota = _quota_mock()
    service, _ = _service(extract=extract, quota=quota)
    with pytest.raises(ExternalServiceException):
        await service.parse_receipt(b"img", "image/jpeg", "a.jpg")
    quota.consume.assert_not_called()


@pytest.mark.asyncio
async def test_parse_receipt_skips_quota_when_llm_fails():
    extract = AsyncMock(return_value="계란")
    parse = AsyncMock(side_effect=ExternalServiceException(detail="llm down"))
    quota = _quota_mock()
    service, _ = _service(extract=extract, parse=parse, quota=quota)
    with pytest.raises(ExternalServiceException):
        await service.parse_receipt(b"img", "image/jpeg", "a.jpg")
    quota.consume.assert_not_called()


@pytest.mark.asyncio
async def test_parse_receipt_accepts_content_type_with_charset():
    extract = AsyncMock(return_value="계란")
    parse = AsyncMock(return_value=["계란"])
    quota = _quota_mock()
    service, _ = _service(extract=extract, parse=parse, quota=quota)

    result = await service.parse_receipt(
        b"img",
        content_type="image/jpeg; charset=binary",
        filename="a.bin",
    )

    assert result.ingredients == ["계란"]
    extract.assert_awaited_once()
    assert extract.await_args.kwargs["format"] == "jpg"


@pytest.mark.asyncio
async def test_parse_receipt_bad_request_skips_quota():
    quota = AsyncMock()
    service, _ = _service(
        extract=AsyncMock(),
        parse=AsyncMock(),
        quota=quota,
    )
    with pytest.raises(BadRequestException):
        await service.parse_receipt(b"", "image/jpeg", "a.jpg")
    quota.consume.assert_not_called()


@pytest.mark.asyncio
async def test_parse_receipt_rejects_oversize():
    quota = AsyncMock()
    service, _ = _service(
        extract=AsyncMock(),
        parse=AsyncMock(),
        quota=quota,
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
    service, _ = _service(
        extract=AsyncMock(),
        parse=AsyncMock(),
        quota=quota,
    )
    with pytest.raises(BadRequestException):
        await service.parse_receipt(
            b"x",
            content_type="application/pdf",
            filename="a.pdf",
        )
    quota.consume.assert_not_called()
