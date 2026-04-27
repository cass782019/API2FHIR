"""End-to-end tests: OpenAPI spec → FHIR Bundle via pipeline completo.

Usa:
  - Anthropic API real (chave em .env ANTHROPIC_API_KEY)
  - HAPI FHIR real em localhost:8090 para $validate
  - swagger_lens parser real
  - LangGraph completo (5 nós)

Executar:
    uv run pytest -m e2e tests/e2e/ -v -s
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.e2e

HAPI_BASE = "http://localhost:8090/fhir"
SPEC_PATH = Path("data/golden/swagger_specs/example_api.yaml")

# ─── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def check_hapi() -> None:
    """Pula todos os testes se HAPI não estiver acessível."""
    try:
        r = httpx.get(f"{HAPI_BASE}/metadata", timeout=10)
        r.raise_for_status()
    except Exception as exc:
        pytest.skip(f"HAPI não acessível em {HAPI_BASE}: {exc}")


@pytest.fixture(scope="module")
def anthropic_client() -> Any:
    """Cliente Anthropic configurado com chave do .env."""
    import anthropic
    from core.settings import settings

    key = settings.anthropic_api_key.get_secret_value()
    if not key or key.startswith("proxyllm"):
        pytest.skip("ANTHROPIC_API_KEY não configurada — use make proxy para rodar sem chave")

    return anthropic.AsyncAnthropic(api_key=key)


# ─── testes ───────────────────────────────────────────────────────────────────

def test_parse_openapi_spec() -> None:
    """Smoke: parser lê o spec de exemplo sem erros."""
    from swagger_lens.parser import parse_spec

    spec = parse_spec(SPEC_PATH.read_bytes(), fmt="auto")
    assert spec.title == "Example Healthcare API"
    assert len(spec.endpoints) >= 6
    op_ids = {e.operation_id for e in spec.endpoints}
    assert "createPatient" in op_ids
    assert "createEncounter" in op_ids
    print(f"\n  Spec: {spec.title} | {len(spec.endpoints)} endpoints")


def test_hapi_validate_patient_directly(check_hapi: None) -> None:
    """HAPI $validate aceita Patient simples sem erros fatais."""
    patient = {
        "resourceType": "Patient",
        "id": "e2e-direct-001",
        "name": [{"use": "official", "family": "Silva", "given": ["Maria"]}],
        "gender": "female",
        "birthDate": "1985-03-15",
    }
    r = httpx.post(f"{HAPI_BASE}/Patient/$validate", json=patient, timeout=15)
    assert r.status_code == 200

    outcome = r.json()
    fatal = [i for i in outcome.get("issue", []) if i.get("severity") in ("error", "fatal")]
    print(f"\n  Patient $validate: {r.status_code} | issues: {len(outcome.get('issue', []))} | fatais: {len(fatal)}")
    assert not fatal, f"Erros fatais: {fatal}"


def test_hapi_validate_encounter_directly(check_hapi: None) -> None:
    """HAPI $validate aceita Encounter simples sem erros fatais."""
    encounter = {
        "resourceType": "Encounter",
        "id": "e2e-enc-001",
        "status": "finished",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "AMB",
            "display": "ambulatory",
        },
        "subject": {"reference": "Patient/e2e-direct-001"},
    }
    r = httpx.post(f"{HAPI_BASE}/Encounter/$validate", json=encounter, timeout=15)
    assert r.status_code == 200
    fatal = [i for i in r.json().get("issue", []) if i.get("severity") in ("error", "fatal")]
    print(f"\n  Encounter $validate: {r.status_code} | fatais: {len(fatal)}")
    assert not fatal


@pytest.mark.asyncio
async def test_full_pipeline_spec_to_bundle(check_hapi: None, anthropic_client: Any) -> None:
    """Pipeline completo: spec OpenAPI → LLM mapping → HAPI validate → Bundle."""
    from swagger_lens.parser import parse_spec
    from fhir_forge.service import convert

    spec = parse_spec(SPEC_PATH.read_bytes(), fmt="auto")
    print(f"\n  Spec carregada: {spec.title} | {len(spec.endpoints)} endpoints")

    bundle = await convert(
        spec,
        job_id="e2e-full-001",
        client=anthropic_client,
        hapi_base_url=HAPI_BASE,
    )

    assert bundle["resourceType"] == "Bundle"
    entries = bundle.get("entry", [])
    assert len(entries) > 0, "Bundle vazio — pipeline não gerou recursos"

    types = [e["resource"]["resourceType"] for e in entries]
    print(f"\n  Bundle: {len(entries)} recursos — {sorted(set(types))}")
    for e in entries:
        r = e["resource"]
        print(f"    • {r['resourceType']}/{r.get('id', '?')}")


@pytest.mark.asyncio
async def test_bundle_resources_pass_hapi_validate(check_hapi: None, anthropic_client: Any) -> None:
    """Cada recurso do Bundle gerado pelo LLM passa no $validate do HAPI."""
    from swagger_lens.parser import parse_spec
    from fhir_forge.service import convert

    spec = parse_spec(SPEC_PATH.read_bytes(), fmt="auto")
    bundle = await convert(
        spec,
        job_id="e2e-validate-001",
        client=anthropic_client,
        hapi_base_url=HAPI_BASE,
    )

    fatal_errors: list[str] = []
    warnings: list[str] = []

    async with httpx.AsyncClient(timeout=30) as http:
        for entry in bundle.get("entry", []):
            resource = entry["resource"]
            rtype = resource.get("resourceType", "Unknown")
            rid = resource.get("id", "?")
            resp = await http.post(f"{HAPI_BASE}/{rtype}/$validate", json=resource)

            if resp.status_code != 200:
                fatal_errors.append(f"{rtype}/{rid}: HTTP {resp.status_code}")
                continue

            for issue in resp.json().get("issue", []):
                sev = issue.get("severity", "")
                diag = issue.get("diagnostics", issue.get("details", {}).get("text", "?"))[:120]
                if sev in ("error", "fatal"):
                    fatal_errors.append(f"{rtype}/{rid} [{sev}]: {diag}")
                elif sev == "warning":
                    warnings.append(f"{rtype}/{rid}: {diag}")

    print(f"\n  Recursos validados: {len(bundle.get('entry', []))}")
    print(f"  Warnings: {len(warnings)} | Erros fatais: {len(fatal_errors)}")
    for w in warnings[:3]:
        print(f"    WARN: {w}")

    assert not fatal_errors, "Recursos com erros fatais no HAPI:\n" + "\n".join(fatal_errors)
    print("  OK: Todos os recursos passaram no $validate HAPI")


@pytest.mark.asyncio
async def test_bundle_contains_expected_resource_types(check_hapi: None, anthropic_client: Any) -> None:
    """Bundle deve conter Patient e Encounter (recursos centrais do spec)."""
    from swagger_lens.parser import parse_spec
    from fhir_forge.service import convert

    spec = parse_spec(SPEC_PATH.read_bytes(), fmt="auto")
    bundle = await convert(
        spec,
        job_id="e2e-types-001",
        client=anthropic_client,
        hapi_base_url=HAPI_BASE,
    )

    types = {e["resource"]["resourceType"] for e in bundle.get("entry", [])}
    print(f"\n  Tipos no Bundle: {sorted(types)}")

    assert "Patient" in types, f"Esperado Patient no Bundle, mas só há: {types}"
    assert "Encounter" in types, f"Esperado Encounter no Bundle, mas só há: {types}"
