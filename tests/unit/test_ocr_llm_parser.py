from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest
from httpx import Request

from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException
from domains.ocr.llm_parser import parse_receipt_text


@pytest.mark.asyncio
async def test_parse_receipt_text_returns_ingredients_and_truncates():
    long_name = "가" * 50
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content='{"ingredients": ["왕교자", "계란", "' + long_name + '", "왕교자"]}'
            )
        )
    ]

    with patch("domains.ocr.llm_parser.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await parse_receipt_text(
            "비비고 왕교자\n계란\n...",
            api_key="test-key",
            model="gpt-4o-mini",
        )

    assert result == ["왕교자", "계란", "가" * 45]
    mock_client.chat.completions.create.assert_awaited_once()
    call_kwargs = mock_client.chat.completions.create.await_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_parse_receipt_text_empty_ingredients():
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"ingredients": []}'))
    ]

    with patch("domains.ocr.llm_parser.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await parse_receipt_text("봉투 100원", api_key="k", model="gpt-4o-mini")

    assert result == []


@pytest.mark.asyncio
async def test_parse_receipt_text_invalid_json_raises():
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="not-json"))]

    with patch("domains.ocr.llm_parser.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with pytest.raises(ExternalServiceException) as exc_info:
            await parse_receipt_text("x", api_key="k", model="gpt-4o-mini")

    assert exc_info.value.code == ErrorCode.OCR_LLM_FAILED


@pytest.mark.asyncio
async def test_parse_receipt_text_openai_error_raises():
    with patch("domains.ocr.llm_parser.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        request = Request("POST", "https://api.openai.com/v1/chat/completions")
        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.APIError("fail", request=request, body=None)
        )

        with pytest.raises(ExternalServiceException) as exc_info:
            await parse_receipt_text("x", api_key="k", model="gpt-4o-mini")

    assert exc_info.value.code == ErrorCode.OCR_LLM_FAILED
