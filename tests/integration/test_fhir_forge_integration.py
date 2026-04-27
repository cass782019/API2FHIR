from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from swagger_lens.models import Endpoint, SwaggerSpec


def _make_spec() -> SwaggerSpec:
    return SwaggerSpec(
        title="Integration Test API",
        version="1.0.0",
        base_url="https://api.test.com",
        openapi_version="3.0.3",
        endpoints=[
            Endpoint(
                path="/patients",
                method="POST",
                operation_id="createPatient",
                summary="Create patient",
                tags=["patient"],
            )
        ],
    )


def _mock_llm_client(resource: dict) -> MagicMock:
    tb = MagicMock(); tb.text = json.dumps(resource)
    msg = MagicMock(); msg.content = [tb]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=msg)
    return client


_VALID_PATIENT = {
    "resourceType": "Patient",
    "id": "integration-patient-01",
    "name": [{"use": "official", "family": "Silva", "given": ["Maria"]}],
    "gender": "female",
    "birthDate": "1985-03-15",
}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_convert_returns_bundle(hapi_base_url: str) -> None:
    from fhir_forge.service import convert

    spec = _make_spec()
    client = _mock_llm_client(_VALID_PATIENT)

    bundle = await convert(
        spec,
        "int-job-001",
        client=client,
        model="test-model",
        hapi_base_url=hapi_base_url,
    )

    assert bundle["resourceType"] == "Bundle"
    assert isinstance(bundle["entry"], list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_convert_bundle_has_at_least_one_entry(hapi_base_url: str) -> None:
    from fhir_forge.service import convert

    spec = _make_spec()
    client = _mock_llm_client(_VALID_PATIENT)

    bundle = await convert(
        spec,
        "int-job-002",
        client=client,
        model="test-model",
        hapi_base_url=hapi_base_url,
    )

    # Patient should pass HAPI validation (or end up included via max-retry path)
    assert len(bundle["entry"]) >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_convert_bundle_entry_has_resource_type(hapi_base_url: str) -> None:
    from fhir_forge.service import convert

    spec = _make_spec()
    client = _mock_llm_client(_VALID_PATIENT)

    bundle = await convert(
        spec,
        "int-job-003",
        client=client,
        model="test-model",
        hapi_base_url=hapi_base_url,
    )

    for entry in bundle["entry"]:
        assert "resource" in entry
        assert "resourceType" in entry["resource"]
