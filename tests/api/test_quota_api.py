from httpx import AsyncClient

from api.deps import get_daily_quota_store
from core.exception.codes import ErrorCode
from core.quota import KIND_OCR, OCR_DAILY_LIMIT


async def test_quotas_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/quotas")
    assert response.status_code == 401
    assert response.json()["code"] == ErrorCode.UNAUTHORIZED


async def test_quotas_returns_defaults(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.get("/api/v1/quotas", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["ocr"]["limit"] == 3
    assert body["ocr"]["used"] == 0
    assert body["ocr"]["remaining"] == 3
    assert body["rag"]["limit"] == 7
    assert body["rag"]["used"] == 0
    assert body["rag"]["remaining"] == 7
    assert "reset_at" in body["ocr"]
    assert "reset_at" in body["rag"]


async def test_quotas_reflects_consumed_ocr(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_user,
):
    store = get_daily_quota_store()
    await store.consume(KIND_OCR, str(test_user.id), OCR_DAILY_LIMIT)

    response = await client.get("/api/v1/quotas", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["ocr"]["used"] == 1
    assert body["ocr"]["remaining"] == 2
    assert body["rag"]["used"] == 0
