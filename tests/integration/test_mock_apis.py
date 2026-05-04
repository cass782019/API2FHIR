"""Smoke tests para o serviço mock-apis (requer docker compose up -d mock-apis)."""
from __future__ import annotations

import os

import httpx
import pytest

MOCK_APIS_BASE = os.getenv("MOCK_APIS_BASE", "http://localhost:8085")

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def check_mock_apis() -> None:
    try:
        httpx.get(f"{MOCK_APIS_BASE}/health", timeout=3).raise_for_status()
    except Exception:
        pytest.skip("mock-apis não disponível — rode: docker compose up -d mock-apis")


def test_health() -> None:
    r = httpx.get(f"{MOCK_APIS_BASE}/health")
    assert r.json() == {"status": "ok", "apis": 5}


def test_natural_person_returns_json() -> None:
    r = httpx.get(f"{MOCK_APIS_BASE}/api/natural-person/667")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    assert len(data) > 0


def test_insurances_returns_list_with_total() -> None:
    r = httpx.get(f"{MOCK_APIS_BASE}/api/insurances")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert data["total"] >= 1


def test_medical_specialties_returns_array() -> None:
    r = httpx.get(f"{MOCK_APIS_BASE}/api/medical-specialties")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1


def test_schedules_appointments_returns_apt001() -> None:
    r = httpx.get(f"{MOCK_APIS_BASE}/api/schedules/appointments")
    assert r.status_code == 200
    data = r.json()
    assert data["results"][0]["id"] == "APT-001"
    assert data["total"] == 1


def test_schedules_physicians_returns_dr_exemplo() -> None:
    r = httpx.get(f"{MOCK_APIS_BASE}/api/schedules/physicians")
    assert r.status_code == 200
    data = r.json()
    assert data["results"][0]["physicianCode"] == 1
    assert "Dr. Exemplo" in data["results"][0]["physicianName"]


def test_schedules_openapi_is_swagger_20() -> None:
    r = httpx.get(f"{MOCK_APIS_BASE}/api/schedules/openapi.json")
    assert r.status_code == 200
    assert r.json()["swagger"] == "2.0"
