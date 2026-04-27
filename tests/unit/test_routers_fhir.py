from __future__ import annotations

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

_HAPI = "http://localhost:8090/fhir"

_PATIENT = {"resourceType": "Patient", "id": "p1", "name": [{"family": "Silva"}]}
_OUTCOME_OK = {
    "resourceType": "OperationOutcome",
    "issue": [{"severity": "information", "code": "informational", "diagnostics": "OK"}],
}


@pytest.fixture
def client() -> TestClient:
    from api.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.unit
def test_fhir_read_returns_resource(client: TestClient) -> None:
    with respx.mock:
        respx.get(f"{_HAPI}/Patient/p1").mock(return_value=Response(200, json=_PATIENT))
        resp = client.get("/fhir/Patient/p1")

    assert resp.status_code == 200
    assert resp.json()["id"] == "p1"


@pytest.mark.unit
def test_fhir_read_404_returns_404(client: TestClient) -> None:
    with respx.mock:
        respx.get(f"{_HAPI}/Patient/missing").mock(return_value=Response(404, json={}))
        resp = client.get("/fhir/Patient/missing")

    assert resp.status_code == 404


@pytest.mark.unit
def test_fhir_validate_returns_outcome(client: TestClient) -> None:
    with respx.mock:
        respx.post(f"{_HAPI}/Patient/$validate").mock(return_value=Response(200, json=_OUTCOME_OK))
        resp = client.post("/fhir/Patient/$validate", json=_PATIENT)

    assert resp.status_code == 200
    assert resp.json()["resourceType"] == "OperationOutcome"


@pytest.mark.unit
def test_health_helpers_use_respx() -> None:
    """Test _check_hapi helper directly via respx."""
    import asyncio

    from api.routers.health import _check_hapi

    async def _run() -> bool:
        with respx.mock:
            respx.get(f"{_HAPI}/metadata").mock(return_value=Response(200, json={"fhirVersion": "4.0.1"}))
            return (await _check_hapi(_HAPI)).ok

    assert asyncio.run(_run()) is True


@pytest.mark.unit
def test_health_check_hapi_down() -> None:
    import asyncio

    from api.routers.health import _check_hapi

    async def _run() -> bool:
        with respx.mock:
            respx.get(f"{_HAPI}/metadata").mock(return_value=Response(500, text="error"))
            return (await _check_hapi(_HAPI)).ok

    assert asyncio.run(_run()) is False
