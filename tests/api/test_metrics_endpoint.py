from httpx import AsyncClient


async def test_metrics_endpoint_exposes_prometheus_text(client: AsyncClient):
    # hit a known route so at least one request is recorded
    await client.get("/")
    response = await client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "http_requests_total" in body or "http_request" in body
