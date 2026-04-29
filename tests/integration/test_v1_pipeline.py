"""End-to-end integration test for /v1 atomic endpoints (detect → infer → validate).

`convert` is intentionally NOT chained here — that step needs a real LLM and
is covered by Fase 4 unit tests (mocked) and the Fase 6 smoke test (real).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_PAYLOAD_PATH = Path(__file__).parent.parent.parent / "jsonAPI" / "natural_person_response.json"


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
