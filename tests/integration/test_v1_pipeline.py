"""End-to-end integration test for /v1 atomic endpoints (detect → infer → validate).

`convert` is intentionally NOT chained here — that step needs a real LLM and
is covered by Fase 4 unit tests (mocked) and the Fase 6 smoke test (real).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_JSONAPI_DIR = Path(__file__).parent.parent.parent / "jsonAPI"
_PAYLOAD_PATH = _JSONAPI_DIR / "natural_person_response.json"
_INSURANCE_PATH = _JSONAPI_DIR / "insurance_response.json"
_MEDIAL_PATH = _JSONAPI_DIR / "medialSpecialities_response.json"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_atomic_pipeline_payload_to_validated_spec(api_client) -> None:
    """Real payload (natural_person_response.json) flows through detect→infer→validate."""
    if not _PAYLOAD_PATH.exists():
        pytest.skip(f"Sample payload not found at {_PAYLOAD_PATH}")

    payload_text = _PAYLOAD_PATH.read_text(encoding="utf-8")
    payload_dict = json.loads(payload_text)

    # 1. detect
    r1 = await api_client.post("/v1/detect", json={"content": payload_text})
    assert r1.status_code == 200
    detection = r1.json()
    assert detection["type"] == "payload", f"Expected payload, got {detection}"

    # 2. infer
    r2 = await api_client.post(
        "/v1/infer-spec",
        json={"payload": payload_dict, "resource_name": "naturalPerson", "method": "POST"},
    )
    assert r2.status_code == 200
    inf = r2.json()
    assert "spec" in inf
    assert inf["spec"]["openapi"] == "3.0.3"
    assert "/naturalPersons" in inf["spec"]["paths"]
    assert len(inf["fabricated"]) >= 5

    # 3. validate
    r3 = await api_client.post("/v1/validate-spec", json={"spec": inf["spec"]})
    assert r3.status_code == 200
    val = r3.json()
    assert val["valid"], f"Inferred spec should be valid OpenAPI 3.0.3. Errors: {val['errors']}"
    assert val["errors"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_atomic_pipeline_insurance_response(api_client) -> None:
    """insurance_response.json (dict payload) flows through detect→infer→validate."""
    if not _INSURANCE_PATH.exists():
        pytest.skip(f"Sample payload not found at {_INSURANCE_PATH}")

    payload_text = _INSURANCE_PATH.read_text(encoding="utf-8")
    payload_dict = json.loads(payload_text)

    # 1. detect — dict with no openapi/swagger field → payload
    r1 = await api_client.post("/v1/detect", json={"content": payload_text})
    assert r1.status_code == 200
    assert r1.json()["type"] == "payload"

    # 2. infer — results/total structure inferred into schema properties
    r2 = await api_client.post(
        "/v1/infer-spec",
        json={"payload": payload_dict, "resource_name": "insurance", "method": "GET"},
    )
    assert r2.status_code == 200
    inf = r2.json()
    spec = inf["spec"]
    assert spec["openapi"] == "3.0.3"
    assert "/insurances" in spec["paths"]
    schema = (
        spec["paths"]["/insurances"]["get"]
        ["responses"]["200"]["content"]["application/json"]["schema"]
    )
    # genson must have detected at least results and total
    props = schema.get("properties", {})
    assert "results" in props, f"Expected 'results' in schema properties, got: {list(props)}"
    assert "total" in props, f"Expected 'total' in schema properties, got: {list(props)}"

    # 3. validate — inferred spec must be valid OpenAPI 3.0.3
    r3 = await api_client.post("/v1/validate-spec", json={"spec": spec})
    assert r3.status_code == 200
    val = r3.json()
    assert val["valid"], f"Insurance spec validation failed: {val['errors']}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_detect_medial_specialities_array_payload(api_client) -> None:
    """medialSpecialities_response.json is a JSON array root.

    /v1/detect correctly classifies it as 'payload'.
    /v1/infer-spec currently expects a dict and returns 422 for array input —
    this is the documented limitation; the frontend shows an error-box in this case.
    """
    if not _MEDIAL_PATH.exists():
        pytest.skip(f"Sample payload not found at {_MEDIAL_PATH}")

    payload_text = _MEDIAL_PATH.read_text(encoding="utf-8")
    payload_list = json.loads(payload_text)
    assert isinstance(payload_list, list), "Fixture must be a JSON array"

    # detect: array with no openapi/swagger field → payload
    r1 = await api_client.post("/v1/detect", json={"content": payload_text})
    assert r1.status_code == 200
    assert r1.json()["type"] == "payload"

    # infer-spec: schema requires dict, not list → 422 Unprocessable Entity
    r2 = await api_client.post(
        "/v1/infer-spec",
        json={"payload": payload_list, "resource_name": "specialty", "method": "GET"},
    )
    assert r2.status_code == 422, (
        f"Expected 422 for array payload, got {r2.status_code}: {r2.text}"
    )
