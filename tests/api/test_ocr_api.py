from unittest.mock import AsyncMock

from httpx import AsyncClient

from api.deps import get_ocr_service
from core.exception.codes import ErrorCode
from domains.ocr.schemas import OcrReceiptResponse
from main import app


async def test_ocr_receipt_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/ocr/receipt",
        files={"image": ("r.jpg", b"fake", "image/jpeg")},
    )
    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_ocr_receipt_success(
    client: AsyncClient, auth_headers: dict[str, str]
):
    mock_service = AsyncMock()
    mock_service.parse_receipt = AsyncMock(
        return_value=OcrReceiptResponse(ingredients=["왕교자", "계란"])
    )
    app.dependency_overrides[get_ocr_service] = lambda: mock_service
    try:
        response = await client.post(
            "/api/v1/ocr/receipt",
            headers=auth_headers,
            files={"image": ("receipt.jpg", b"fake-bytes", "image/jpeg")},
        )
    finally:
        app.dependency_overrides.pop(get_ocr_service, None)

    assert response.status_code == 200
    assert response.json() == {"ingredients": ["왕교자", "계란"]}
    mock_service.parse_receipt.assert_awaited_once()
    args = mock_service.parse_receipt.await_args.args
    assert args[0] == b"fake-bytes"


async def test_ocr_receipt_rejects_missing_file(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.post(
        "/api/v1/ocr/receipt",
        headers=auth_headers,
    )
    assert response.status_code == 422
