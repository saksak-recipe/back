from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.exception.codes import ErrorCode
from core.exception.exceptions import ExternalServiceException
from domains.ocr.naver_client import extract_text


@pytest.mark.asyncio
async def test_extract_text_joins_infer_text():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "images": [
            {
                "fields": [
                    {"inferText": "왕교자"},
                    {"inferText": "1,200"},
                    {"inferText": "계란"},
                ]
            }
        ]
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("domains.ocr.naver_client.httpx.AsyncClient", return_value=mock_client):
        text = await extract_text(
            b"fake-image",
            format="jpeg",
            api_url="https://ocr.test/invoke",
            secret_key="secret",
        )

    assert text == "왕교자\n1,200\n계란"
    call_kwargs = mock_client.post.await_args.kwargs
    assert call_kwargs["headers"]["X-OCR-SECRET"] == "secret"
    message = call_kwargs["data"]["message"]
    assert '"format": "jpg"' in message  # jpeg → jpg


@pytest.mark.asyncio
async def test_extract_text_http_error_raises():
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("domains.ocr.naver_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ExternalServiceException) as exc_info:
            await extract_text(
                b"x",
                format="png",
                api_url="https://ocr.test/invoke",
                secret_key="secret",
            )

    assert exc_info.value.code == ErrorCode.OCR_FAILED


@pytest.mark.asyncio
async def test_extract_text_non_200_raises():
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "boom"
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("domains.ocr.naver_client.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ExternalServiceException) as exc_info:
            await extract_text(
                b"x",
                format="png",
                api_url="https://ocr.test/invoke",
                secret_key="secret",
            )

    assert exc_info.value.code == ErrorCode.OCR_FAILED
