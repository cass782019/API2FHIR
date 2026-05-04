"""Testes unitários para POST /v1/store-bundle."""
from __future__ import annotations

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

_HAPI = "http://localhost:8090/fhir"

_BUNDLE_2 = {
    "resourceType": "Bundle",
    "type": "collection",
    "entry": [
        {"resource": {"resourceType": "Patient", "id": "p1"}},
        {"resource": {"resourceType": "Encounter", "id": "e1", "status": "finished"}},
    ],
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    from api.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.unit
def test_store_bundle_all_success(client: TestClient) -> None:
    with respx.mock:
        respx.put(f"{_HAPI}/Patient/p1").mock(return_value=Response(201))
        respx.put(f"{_HAPI}/Encounter/e1").mock(return_value=Response(201))
        resp = client.post(
            "/v1/store-bundle",
            json={"bundle": _BUNDLE_2, "hapi_base_url": _HAPI},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success_count"] == 2
    assert data["errors"] == []
    assert data["total"] == 2


@pytest.mark.unit
def test_store_bundle_skips_entry_without_id(client: TestClient) -> None:
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": {"resourceType": "Patient"}}],
    }
    resp = client.post(
        "/v1/store-bundle",
        json={"bundle": bundle, "hapi_base_url": _HAPI},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["success_count"] == 0
    assert len(data["errors"]) == 1


@pytest.mark.unit
def test_store_bundle_hapi_500_recorded(client: TestClient) -> None:
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": {"resourceType": "Patient", "id": "p-err"}}],
    }
    with respx.mock:
        respx.put(f"{_HAPI}/Patient/p-err").mock(return_value=Response(500))
        resp = client.post(
            "/v1/store-bundle",
            json={"bundle": bundle, "hapi_base_url": _HAPI},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["stored"][0]["status"] == 500
    assert data["success_count"] == 0
