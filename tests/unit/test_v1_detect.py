from __future__ import annotations

import json

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_detect_openapi_3_via_endpoint(api_client) -> None:
    spec_json = json.dumps({"openapi": "3.0.3", "info": {}, "paths": {}})
    r = await api_client.post("/v1/detect", json={"content": spec_json})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "openapi"
    assert data["version"] == "3.0.3"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_detect_swagger_2_via_endpoint(api_client) -> None:
    spec_json = json.dumps({"swagger": "2.0", "info": {}, "paths": {}})
    r = await api_client.post("/v1/detect", json={"content": spec_json})
    assert r.status_code == 200
    assert r.json() == {"type": "swagger", "version": "2.0"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_detect_payload_via_endpoint(api_client) -> None:
    payload = json.dumps({"id": 1, "name": "Maria"})
    r = await api_client.post("/v1/detect", json={"content": payload})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "payload"
    assert data["version"] is None
