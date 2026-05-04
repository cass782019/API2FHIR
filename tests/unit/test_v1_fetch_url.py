"""Testes unitários para POST /v1/fetch-url."""
from __future__ import annotations

import json

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

_SWAGGER_SPEC = json.dumps({
    "swagger": "2.0",
    "info": {"title": "Test API", "version": "1.0"},
    "paths": {},
})

_PAYLOAD_JSON = json.dumps({
    "results": [{"id": 1, "name": "Paciente Exemplo"}],
    "total": 1,
})


@pytest.fixture(scope="module")
def client() -> TestClient:
    from api.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.unit
def test_fetch_url_detects_swagger_spec(client: TestClient) -> None:
    with respx.mock:
        respx.get("http://mock-server/swagger.json").mock(
            return_value=Response(
                200,
                text=_SWAGGER_SPEC,
                headers={"content-type": "application/json"},
            )
        )
        resp = client.post("/v1/fetch-url", json={"url": "http://mock-server/swagger.json"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "swagger"
    assert data["version"] == "2.0"
    assert data["url"] == "http://mock-server/swagger.json"


@pytest.mark.unit
def test_fetch_url_detects_payload(client: TestClient) -> None:
    with respx.mock:
        respx.get("http://mock-server/api/patients").mock(
            return_value=Response(
                200,
                text=_PAYLOAD_JSON,
                headers={"content-type": "application/json"},
            )
        )
        resp = client.post("/v1/fetch-url", json={"url": "http://mock-server/api/patients"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "payload"
    assert data["version"] is None
    assert "results" in data["content"]


@pytest.mark.unit
def test_fetch_url_remote_404_returns_502(client: TestClient) -> None:
    with respx.mock:
        respx.get("http://mock-server/not-found").mock(
            return_value=Response(404, text="Not Found")
        )
        resp = client.post("/v1/fetch-url", json={"url": "http://mock-server/not-found"})
    assert resp.status_code == 502


@pytest.mark.unit
def test_fetch_url_forbidden_scheme(client: TestClient) -> None:
    resp = client.post("/v1/fetch-url", json={"url": "ftp://some-server/file.json"})
    assert resp.status_code == 422
