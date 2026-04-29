from __future__ import annotations

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_infer_simple_payload(api_client) -> None:
    body = {"payload": {"id": 1, "name": "x"}, "resource_name": "thing", "method": "POST"}
    r = await api_client.post("/v1/infer-spec", json=body)
    assert r.status_code == 200
    data = r.json()
    spec = data["spec"]
    assert spec["openapi"] == "3.0.3"
    assert "/things" in spec["paths"]
    assert spec["paths"]["/things"]["post"]["operationId"] == "postThing"
    assert any("operationId" in f for f in data["fabricated"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_infer_invalid_method_returns_422(api_client) -> None:
    body = {"payload": {"id": 1}, "resource_name": "x", "method": "BOGUS"}
    r = await api_client.post("/v1/infer-spec", json=body)
    assert r.status_code == 422
    assert "Invalid HTTP method" in r.text


@pytest.mark.unit
@pytest.mark.asyncio
async def test_infer_resource_name_default(api_client) -> None:
    body = {"payload": {"id": 1}}
    r = await api_client.post("/v1/infer-spec", json=body)
    assert r.status_code == 200
    spec = r.json()["spec"]
    assert "/resources" in spec["paths"]
