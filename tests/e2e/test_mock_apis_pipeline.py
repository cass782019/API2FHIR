"""E2E: mock APIs → detect → infer → validate → convert → store-bundle → HAPI."""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import httpx
import pytest

MOCK_APIS_BASE = os.getenv("MOCK_APIS_BASE", "http://localhost:8085")
API_BASE = os.getenv("API_BASE", "http://localhost:8000")
HAPI_BASE = os.getenv("HAPI_BASE", "http://localhost:8090/fhir")

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module", autouse=True)
def check_services() -> None:
    """Skipa todos os testes se qualquer serviço necessário estiver indisponível."""
    checks = [
        (f"{MOCK_APIS_BASE}/health", "mock-apis"),
        (f"{HAPI_BASE}/metadata", "HAPI"),
        (f"{API_BASE}/health", "API"),
    ]
    for url, name in checks:
        try:
            httpx.get(url, timeout=5).raise_for_status()
        except Exception:
            pytest.skip(f"{name} não disponível em {url}")


# ── Helpers de unwrap ─────────────────────────────────────────────────────────

def _results0(data: dict[str, Any]) -> dict[str, Any]:
    return data["results"][0]  # type: ignore[return-value]


def _first(data: Any) -> dict[str, Any]:
    return data[0]  # type: ignore[return-value]


# ── Parâmetros: 1 linha por API mock ─────────────────────────────────────────

_MOCK_API_PARAMS = [
    pytest.param(
        {
            "endpoint": "/api/natural-person/667",
            "resource_name": "naturalPerson",
            "unwrap": None,
        },
        id="natural_person",
    ),
    pytest.param(
        {
            "endpoint": "/api/insurances",
            "resource_name": "insurance",
            "unwrap": _results0,
        },
        id="insurance",
    ),
    pytest.param(
        {
            "endpoint": "/api/medical-specialties",
            "resource_name": "medicalSpecialty",
            "unwrap": _first,
        },
        id="medical_specialties",
    ),
    pytest.param(
        {
            "endpoint": "/api/schedules/appointments",
            "resource_name": "appointment",
            "unwrap": _results0,
        },
        id="appointments",
    ),
    pytest.param(
        {
            "endpoint": "/api/schedules/physicians",
            "resource_name": "physician",
            "unwrap": _results0,
        },
        id="physicians",
    ),
]


# ── Teste parametrizado — 7 passos ───────────────────────────────────────────

@pytest.mark.parametrize("params", _MOCK_API_PARAMS)
def test_mock_api_full_pipeline(params: dict[str, Any]) -> None:
    """Pipeline completo: mock API → detect → infer → validate → convert → store → HAPI GET."""
    endpoint: str = params["endpoint"]
    resource_name: str = params["resource_name"]
    unwrap: Callable[[Any], dict[str, Any]] | None = params["unwrap"]

    # 1. GET payload da mock API
    r = httpx.get(f"{MOCK_APIS_BASE}{endpoint}", timeout=10)
    assert r.status_code == 200, f"mock-apis {endpoint} retornou {r.status_code}"
    raw = r.json()
    payload = unwrap(raw) if unwrap else raw

    # 2. detect → payload
    det = httpx.post(
        f"{API_BASE}/v1/detect",
        json={"content": json.dumps(payload)},
        timeout=10,
    ).json()
    assert det["type"] == "payload", f"detect retornou {det['type']!r}"

    # 3. infer-spec → OpenAPI 3.0.3
    infer = httpx.post(
        f"{API_BASE}/v1/infer-spec",
        json={"payload": payload, "resource_name": resource_name, "method": "GET"},
        timeout=60,
    ).json()
    spec = infer["spec"]
    assert spec.get("openapi") == "3.0.3", f"infer-spec retornou {spec.get('openapi')!r}"

    # 4. validate-spec
    val = httpx.post(
        f"{API_BASE}/v1/validate-spec",
        json={"spec": spec},
        timeout=10,
    ).json()
    assert val["valid"] is True, f"validate-spec falhou: {val.get('errors')}"

    # 5. convert → bundle
    conv = httpx.post(
        f"{API_BASE}/v1/convert",
        json={"spec": json.dumps(spec), "options": {"async_mode": False}},
        timeout=180,
    ).json()
    bundle = conv.get("bundle")
    assert bundle is not None, f"convert não retornou bundle: {conv}"
    entries = bundle.get("entry", [])
    assert len(entries) >= 1, "Bundle sem entries"

    # 6. store-bundle → HAPI
    store = httpx.post(
        f"{API_BASE}/v1/store-bundle",
        json={"bundle": bundle, "hapi_base_url": HAPI_BASE},
        timeout=60,
    ).json()
    assert store["success_count"] >= 1, f"store-bundle falhou: {store}"

    # 7. GET do HAPI — verificar persistência
    first_stored = store["stored"][0]
    hapi_get = httpx.get(first_stored["fhir_url"], timeout=10)
    assert hapi_get.status_code == 200, (
        f"HAPI GET {first_stored['fhir_url']} retornou {hapi_get.status_code}"
    )
    assert hapi_get.json().get("resourceType") is not None


# ── Teste extra: Swagger 2.0 completo (schedules) ────────────────────────────

def test_schedules_spec_converts_directly() -> None:
    """schedules_1.json (Swagger 2.0) converte sem infer-spec."""

    # 1. fetch spec via mock-apis
    r = httpx.get(f"{MOCK_APIS_BASE}/api/schedules/openapi.json", timeout=10)
    assert r.status_code == 200
    spec_text = r.text

    # 2. detect → swagger
    det = httpx.post(f"{API_BASE}/v1/detect", json={"content": spec_text}, timeout=10).json()
    assert det["type"] == "swagger", f"Esperado 'swagger', obteve {det['type']!r}"

    # 3. convert diretamente
    conv = httpx.post(
        f"{API_BASE}/v1/convert",
        json={"spec": spec_text, "options": {"async_mode": False}},
        timeout=180,
    ).json()
    bundle = conv.get("bundle")
    assert bundle is not None
    n = len(bundle.get("entry", []))
    assert n >= 1, "Bundle vazio (0 entries)"

    # 4. store no HAPI
    store = httpx.post(
        f"{API_BASE}/v1/store-bundle",
        json={"bundle": bundle, "hapi_base_url": HAPI_BASE},
        timeout=60,
    ).json()
    assert store["success_count"] >= 1, f"store-bundle falhou: {store}"
