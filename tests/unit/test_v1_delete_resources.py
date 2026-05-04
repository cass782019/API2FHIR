"""Unit tests for POST /v1/delete-resources."""
from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("FEATURE_ADMIN_NOAUTH", "true")
    from api.main import create_app

    return TestClient(create_app())


BASE = "http://localhost:8090/fhir"

RES_P1 = {"resource_type": "Patient", "resource_id": "p1",
           "fhir_url": f"{BASE}/Patient/p1", "status": 201}
RES_E1 = {"resource_type": "Encounter", "resource_id": "e1",
           "fhir_url": f"{BASE}/Encounter/e1", "status": 201}


@pytest.mark.unit
@respx.mock
def test_delete_all_200(client: TestClient) -> None:
    """2 recursos, HAPI 200 → success_count=2, errors vazio."""
    respx.delete(f"{BASE}/Patient/p1").mock(return_value=httpx.Response(200))
    respx.delete(f"{BASE}/Encounter/e1").mock(return_value=httpx.Response(200))
    r = client.post("/v1/delete-resources",
                    json={"resources": [RES_P1, RES_E1], "hapi_base_url": BASE})
    assert r.status_code == 200
    data = r.json()
    assert data["success_count"] == 2
    assert data["total"] == 2
    assert data["errors"] == []


@pytest.mark.unit
@respx.mock
def test_delete_204_success(client: TestClient) -> None:
    """HAPI 204 (sem body) também conta como sucesso."""
    respx.delete(f"{BASE}/Patient/p1").mock(return_value=httpx.Response(204))
    r = client.post("/v1/delete-resources",
                    json={"resources": [RES_P1], "hapi_base_url": BASE})
    assert r.json()["success_count"] == 1


@pytest.mark.unit
@respx.mock
def test_delete_404_not_success(client: TestClient) -> None:
    """404 (recurso não encontrado): entra em deleted[], não em errors[], mas success_count=0."""
    respx.delete(f"{BASE}/Patient/p1").mock(return_value=httpx.Response(404))
    r = client.post("/v1/delete-resources",
                    json={"resources": [RES_P1], "hapi_base_url": BASE})
    data = r.json()
    assert data["success_count"] == 0
    assert data["deleted"][0]["status"] == 404
    assert data["errors"] == []


@pytest.mark.unit
@respx.mock
def test_delete_500_not_success(client: TestClient) -> None:
    """5xx do HAPI: entra em deleted[] com status 500, success_count=0."""
    respx.delete(f"{BASE}/Patient/p1").mock(return_value=httpx.Response(500))
    r = client.post("/v1/delete-resources",
                    json={"resources": [RES_P1], "hapi_base_url": BASE})
    data = r.json()
    assert data["success_count"] == 0
    assert data["deleted"][0]["status"] == 500


@pytest.mark.unit
def test_delete_empty_list(client: TestClient) -> None:
    """Lista vazia → total=0, success_count=0, sem chamadas HTTP."""
    r = client.post("/v1/delete-resources",
                    json={"resources": [], "hapi_base_url": BASE})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["success_count"] == 0
    assert data["deleted"] == []
    assert data["errors"] == []


@pytest.mark.unit
@respx.mock
def test_delete_network_error(client: TestClient) -> None:
    """ConnectError vai para errors[], não para deleted[]."""
    respx.delete(f"{BASE}/Patient/p1").mock(side_effect=httpx.ConnectError("refused"))
    r = client.post("/v1/delete-resources",
                    json={"resources": [RES_P1], "hapi_base_url": BASE})
    data = r.json()
    assert data["success_count"] == 0
    assert len(data["errors"]) == 1
    assert "Patient/p1" in data["errors"][0]
    assert data["deleted"] == []


@pytest.mark.unit
@respx.mock
def test_delete_partial_success(client: TestClient) -> None:
    """1 sucesso (204) + 1 erro de rede → success_count=1, errors len=1."""
    respx.delete(f"{BASE}/Patient/p1").mock(return_value=httpx.Response(204))
    respx.delete(f"{BASE}/Encounter/e1").mock(side_effect=httpx.ConnectError("timeout"))
    r = client.post("/v1/delete-resources",
                    json={"resources": [RES_P1, RES_E1], "hapi_base_url": BASE})
    data = r.json()
    assert data["success_count"] == 1
    assert len(data["errors"]) == 1
    assert len(data["deleted"]) == 1


@pytest.mark.unit
def test_delete_schema_422(client: TestClient) -> None:
    """Body sem o campo obrigatório 'resources' → HTTP 422."""
    r = client.post("/v1/delete-resources",
                    json={"hapi_base_url": BASE})
    assert r.status_code == 422
