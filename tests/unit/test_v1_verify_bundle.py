"""Testes unitários para POST /v1/verify-bundle."""
from __future__ import annotations

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Request, Response

_HAPI = "http://localhost:8090/fhir"
_STORED = [
    {
        "resource_type": "Patient",
        "resource_id": "p1",
        "fhir_url": f"{_HAPI}/Patient/p1",
        "status": 201,
    }
]
_STORED_MISSING = [
    {
        "resource_type": "Patient",
        "resource_id": "gone",
        "fhir_url": f"{_HAPI}/Patient/gone",
        "status": 201,
    }
]
_PATIENT = {"resourceType": "Patient", "id": "p1"}
_OP_OK = {"resourceType": "OperationOutcome", "issue": []}


@pytest.fixture(scope="module")
def client() -> TestClient:
    from api.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.unit
def test_verify_bundle_accessible_and_valid(client: TestClient) -> None:
    with respx.mock:
        respx.get(f"{_HAPI}/Patient/p1").mock(return_value=Response(200, json=_PATIENT))
        respx.post(f"{_HAPI}/Patient/$validate").mock(
            return_value=Response(200, json=_OP_OK)
        )
        resp = client.post(
            "/v1/verify-bundle",
            json={"stored": _STORED, "hapi_base_url": _HAPI},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["all_accessible"] is True
    assert data["all_valid"] is True
    assert data["results"][0]["get_status"] == 200
    assert data["results"][0]["valid"] is True


@pytest.mark.unit
def test_verify_bundle_resource_not_found(client: TestClient) -> None:
    with respx.mock:
        respx.get(f"{_HAPI}/Patient/gone").mock(return_value=Response(404, json={}))
        resp = client.post(
            "/v1/verify-bundle",
            json={"stored": _STORED_MISSING, "hapi_base_url": _HAPI},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["all_accessible"] is False
    assert data["results"][0]["get_status"] == 404
    assert data["results"][0]["valid"] is None


@pytest.mark.unit
def test_verify_bundle_profile_url_forwarded(client: TestClient) -> None:
    """profile_url deve ser enviado como ?profile= no POST $validate ao HAPI."""
    profile = "http://hl7.org/fhir/StructureDefinition/Patient"
    captured: dict = {}

    def capture_validate(request: Request) -> Response:
        captured["profile"] = request.url.params.get("profile")
        return Response(200, json=_OP_OK)

    with respx.mock:
        respx.get(f"{_HAPI}/Patient/p1").mock(return_value=Response(200, json=_PATIENT))
        respx.post(f"{_HAPI}/Patient/$validate").mock(side_effect=capture_validate)
        resp = client.post(
            "/v1/verify-bundle",
            json={"stored": _STORED, "hapi_base_url": _HAPI, "profile_url": profile},
        )
    assert resp.status_code == 200
    assert captured.get("profile") == profile
