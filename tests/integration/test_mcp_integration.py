"""Integration tests for MCP tools against a real HAPI FHIR testcontainer."""
from __future__ import annotations

import json

import pytest

from mcp_server.tools.hapi import get_resource, search_resources, validate_resource


@pytest.mark.integration
async def test_validate_patient_valid(hapi_base_url: str) -> None:
    """A minimal valid Patient should pass $validate."""
    import os
    os.environ["HAPI_BASE_URL"] = hapi_base_url

    from mcp_server import settings as mcp_settings_module
    mcp_settings_module.settings.hapi_base_url = hapi_base_url

    resource = {
        "resourceType": "Patient",
        "id": "integration-patient-1",
        "name": [{"use": "official", "family": "Silva", "given": ["João"]}],
        "gender": "male",
        "birthDate": "1980-01-15",
    }
    result = await validate_resource(json.dumps(resource))

    assert result["valid"] is True, f"Expected valid but got issues: {result['issues']}"


@pytest.mark.integration
async def test_validate_patient_invalid(hapi_base_url: str) -> None:
    """A Patient with an invalid gender value should fail $validate."""
    resource = {
        "resourceType": "Patient",
        "id": "bad-patient",
        "gender": "not-a-valid-gender",
    }
    result = await validate_resource(json.dumps(resource))

    assert result["valid"] is False
    assert any(i["severity"] == "error" for i in result["issues"])


@pytest.mark.integration
async def test_create_and_get_resource(hapi_base_url: str) -> None:
    """Create a Patient via HAPI REST, then retrieve it via get_resource."""
    import httpx

    patient = {
        "resourceType": "Patient",
        "name": [{"family": "Integration", "given": ["Test"]}],
        "gender": "unknown",
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(f"{hapi_base_url}/Patient", json=patient)
        assert r.status_code == 201
        created_id = r.json()["id"]

    result = await get_resource("Patient", created_id)
    assert result["id"] == created_id
    assert result["resourceType"] == "Patient"


@pytest.mark.integration
async def test_get_resource_not_found(hapi_base_url: str) -> None:
    result = await get_resource("Patient", "does-not-exist-xyz")
    assert result["error"] == "not_found"


@pytest.mark.integration
async def test_search_resources(hapi_base_url: str) -> None:
    """Create 2 patients with the same family name, then search."""
    import httpx

    async with httpx.AsyncClient() as client:
        for i in range(2):
            patient = {
                "resourceType": "Patient",
                "name": [{"family": "Testável", "given": [f"Paciente{i}"]}],
            }
            r = await client.post(f"{hapi_base_url}/Patient", json=patient)
            assert r.status_code == 201

    results = await search_resources("Patient", "family=Testável")
    assert len(results) >= 2
