from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from swagger_lens.models import Endpoint, SwaggerSpec


def _make_spec(endpoints: list[Endpoint] | None = None) -> SwaggerSpec:
    if endpoints is None:
        endpoints = [
            Endpoint(
                path="/patients",
                method="POST",
                operation_id="createPatient",
                summary="Create patient",
                tags=["patient"],
            )
        ]
    return SwaggerSpec(
        title="Test API",
        version="1.0.0",
        base_url="https://api.test.com",
        openapi_version="3.0.3",
        endpoints=endpoints,
    )


def _mock_llm_client(resource: dict) -> MagicMock:
    tb = MagicMock(); tb.text = json.dumps(resource)
    msg = MagicMock(); msg.content = [tb]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=msg)
    return client


_PATIENT = {
    "resourceType": "Patient",
    "id": "p1",
    "name": [{"use": "official", "family": "Silva"}],
    "gender": "male",
    "birthDate": "1990-01-01",
}

_HAPI_VALID = {"resourceType": "OperationOutcome", "issue": [{"severity": "information", "diagnostics": "OK"}]}
_HAPI_INVALID = {
    "resourceType": "OperationOutcome",
    "issue": [{"severity": "error", "diagnostics": "Missing required field"}],
}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_valid_resources_go_to_bundle() -> None:
    """If all resources pass validation, the graph reaches bundle_node."""
    from fhir_forge.service import convert

    spec = _make_spec()
    client = _mock_llm_client(_PATIENT)

    with patch(
        "fhir_forge.nodes.validation_node._validate_resource",
        new=AsyncMock(return_value=[]),
    ):
        bundle = await convert(
            spec,
            "job-valid-01",
            client=client,
            model="test-model",
            hapi_base_url="http://localhost:8090/fhir",
        )

    assert bundle["resourceType"] == "Bundle"
    assert len(bundle["entry"]) >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_resource_below_max_retries_calls_fix() -> None:
    """First attempt fails; fix_node is called; second validation passes."""
    from fhir_forge.service import convert

    spec = _make_spec()

    # LLM: first call from mapping_node, second call from fix_node
    tb1 = MagicMock(); tb1.text = json.dumps(_PATIENT)
    tb2 = MagicMock(); tb2.text = json.dumps(_PATIENT)  # fixed = same valid resource
    msg1 = MagicMock(); msg1.content = [tb1]
    msg2 = MagicMock(); msg2.content = [tb2]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=[msg1, msg2])

    call_count = 0

    async def _hapi_side_effect(resource: dict, hapi_base_url: str) -> list[str]:
        nonlocal call_count
        call_count += 1
        return ["Missing required field"] if call_count == 1 else []

    with patch(
        "fhir_forge.nodes.validation_node._validate_resource",
        new=AsyncMock(side_effect=_hapi_side_effect),
    ):
        bundle = await convert(
            spec,
            "job-retry-01",
            client=client,
            model="test-model",
            hapi_base_url="http://localhost:8090/fhir",
        )

    assert bundle["resourceType"] == "Bundle"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_max_retries_forces_bundle_with_warnings() -> None:
    """After 3 retries, graph must produce a Bundle anyway (with warnings)."""
    from fhir_forge.graph import build_graph
    from langgraph.checkpoint.memory import MemorySaver

    spec = _make_spec()

    tb = MagicMock(); tb.text = json.dumps(_PATIENT)
    msg = MagicMock(); msg.content = [tb]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=msg)

    with patch(
        "fhir_forge.nodes.validation_node._validate_resource",
        new=AsyncMock(return_value=["Missing required field"]),
    ):
        compiled = build_graph(
            client=client,
            model="test-model",
            hapi_base_url="http://localhost:8090/fhir",
            checkpointer=MemorySaver(),
        )
        initial: dict = {
            "swagger_spec": spec,
            "endpoints_to_process": ["createPatient"],
            "fhir_resources": [],
            "invalid_resources": [],
            "validation_errors": [],
            "retry_count": 3,  # already at max — bundle forced on first validation
            "job_id": "job-maxretry-01",
            "trace_id": "",
            "warnings": [],
        }
        config = {"configurable": {"thread_id": "job-maxretry-01"}}
        final = await compiled.ainvoke(initial, config=config)

    assert "_bundle" in final
    assert final["_bundle"]["resourceType"] == "Bundle"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_spec_produces_empty_bundle() -> None:
    from fhir_forge.service import convert

    spec = SwaggerSpec(
        title="Empty API",
        version="1.0.0",
        base_url="https://empty.example.com",
        openapi_version="3.0.3",
        endpoints=[],
    )
    client = _mock_llm_client(_PATIENT)

    bundle = await convert(
        spec,
        "job-empty-01",
        client=client,
        model="test-model",
        hapi_base_url="http://localhost:8090/fhir",
    )

    assert bundle["resourceType"] == "Bundle"
    assert bundle["entry"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bundle_has_required_fields() -> None:
    from fhir_forge.service import convert

    spec = _make_spec()
    client = _mock_llm_client(_PATIENT)

    with patch(
        "fhir_forge.nodes.validation_node._validate_resource",
        new=AsyncMock(return_value=[]),
    ):
        bundle = await convert(
            spec,
            "job-fields-01",
            client=client,
            model="test-model",
            hapi_base_url="http://localhost:8090/fhir",
        )

    assert "resourceType" in bundle
    assert "type" in bundle
    assert bundle["type"] == "collection"
    assert "entry" in bundle
