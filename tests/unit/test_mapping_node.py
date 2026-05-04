from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from swagger_lens.models import Endpoint, SwaggerSpec


def _make_state(endpoints: list[Endpoint] | None = None) -> dict:
    if endpoints is None:
        endpoints = [
            Endpoint(
                path="/patients",
                method="POST",
                operation_id="createPatient",
                summary="Create a new patient",
                tags=["patient"],
            )
        ]
    spec = SwaggerSpec(
        title="Test API",
        version="1.0.0",
        base_url="https://api.example.com",
        openapi_version="3.0.3",
        endpoints=endpoints,
    )
    return {
        "swagger_spec": spec,
        "endpoints_to_process": [ep.operation_id for ep in endpoints],
        "fhir_resources": [],
        "invalid_resources": [],
        "validation_errors": [],
        "retry_count": 0,
        "job_id": "test-job-01",
        "trace_id": "",
        "warnings": [],
    }


def _make_mock_client(response_json: dict) -> MagicMock:
    """Build an AsyncAnthropic mock that returns the given dict as LLM text."""
    text_block = MagicMock()
    text_block.text = json.dumps(response_json)

    message = MagicMock()
    message.content = [text_block]

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=message)
    return client


_PATIENT_RESOURCE = {
    "resourceType": "Patient",
    "id": "createPatient-example",
    "name": [{"use": "official", "family": "Silva", "given": ["Maria"]}],
    "gender": "female",
    "birthDate": "1985-03-15",
}

_ENCOUNTER_RESOURCE = {
    "resourceType": "Encounter",
    "id": "createEncounter-example",
    "status": "finished",
    "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
    "subject": {"reference": "Patient/p1"},
}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mapping_node_returns_fhir_resource() -> None:
    from fhir_forge.nodes.mapping_node import mapping_node

    state = _make_state()
    client = _make_mock_client(_PATIENT_RESOURCE)
    result = await mapping_node(state, client=client, model="test-model")
    assert len(result["fhir_resources"]) == 1
    assert result["fhir_resources"][0]["resourceType"] == "Patient"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mapping_node_clears_endpoints_to_process() -> None:
    from fhir_forge.nodes.mapping_node import mapping_node

    state = _make_state()
    client = _make_mock_client(_PATIENT_RESOURCE)
    result = await mapping_node(state, client=client, model="test-model")
    assert result["endpoints_to_process"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mapping_node_skips_basic_placeholder() -> None:
    from fhir_forge.nodes.mapping_node import mapping_node

    state = _make_state()
    client = _make_mock_client({"resourceType": "Basic", "id": "n/a"})
    result = await mapping_node(state, client=client, model="test-model")
    assert result["fhir_resources"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mapping_node_handles_multiple_endpoints() -> None:
    from fhir_forge.nodes.mapping_node import mapping_node

    eps = [
        Endpoint(path="/patients", method="POST", operation_id="createPatient", tags=["patient"]),
        Endpoint(path="/encounters", method="POST", operation_id="createEncounter", tags=["encounter"]),
    ]
    state = _make_state(eps)

    # Alternate responses
    text1 = MagicMock(); text1.text = json.dumps(_PATIENT_RESOURCE)
    text2 = MagicMock(); text2.text = json.dumps(_ENCOUNTER_RESOURCE)
    msg1 = MagicMock(); msg1.content = [text1]
    msg2 = MagicMock(); msg2.content = [text2]

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=[msg1, msg2])

    result = await mapping_node(state, client=client, model="test-model")
    assert len(result["fhir_resources"]) == 2
    types = {r["resourceType"] for r in result["fhir_resources"]}
    assert types == {"Patient", "Encounter"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mapping_node_malformed_json_skips_resource() -> None:
    """When LLM returns non-JSON, the endpoint is skipped (not a hard failure)."""
    from fhir_forge.nodes.mapping_node import mapping_node

    state = _make_state()
    text_block = MagicMock(); text_block.text = "not valid json at all"
    message = MagicMock(); message.content = [text_block]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=message)

    result = await mapping_node(state, client=client, model="test-model")
    assert result["fhir_resources"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mapping_node_missing_resource_type_skips() -> None:
    from fhir_forge.nodes.mapping_node import mapping_node

    state = _make_state()
    client = _make_mock_client({"id": "no-resource-type", "field": "value"})
    result = await mapping_node(state, client=client, model="test-model")
    assert result["fhir_resources"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mapping_node_strips_markdown_fences() -> None:
    """LLM occasionally wraps JSON in markdown fences."""
    from fhir_forge.nodes.mapping_node import mapping_node

    state = _make_state()
    text_block = MagicMock()
    text_block.text = "```json\n" + json.dumps(_PATIENT_RESOURCE) + "\n```"
    message = MagicMock(); message.content = [text_block]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=message)

    result = await mapping_node(state, client=client, model="test-model")
    assert len(result["fhir_resources"]) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mapping_node_unknown_operation_id_ignored() -> None:
    from fhir_forge.nodes.mapping_node import mapping_node

    state = _make_state()
    state["endpoints_to_process"] = ["nonExistentOpId"]
    client = _make_mock_client(_PATIENT_RESOURCE)
    result = await mapping_node(state, client=client, model="test-model")
    assert result["fhir_resources"] == []
    # LLM should NOT have been called
    client.messages.create.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mapping_node_overrides_id_with_slug() -> None:
    """LLM-provided id is overwritten by a slug derived from operation_id."""
    from fhir_forge.nodes.mapping_node import mapping_node

    state = _make_state(
        [Endpoint(path="/x", method="POST", operation_id="bookTime", tags=[])]
    )
    client = _make_mock_client({"resourceType": "Appointment", "id": "whatever-LLM-said"})
    result = await mapping_node(state, client=client, model="test-model")
    assert len(result["fhir_resources"]) == 1
    assert result["fhir_resources"][0]["id"] == "booktime"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mapping_node_dedupes_colliding_ids() -> None:
    """Endpoints whose slugified ids would collide get -2, -3 suffixes."""
    from fhir_forge.nodes.mapping_node import mapping_node

    # Distinct operation_ids that all slugify to the same value ("booktime"):
    eps = [
        Endpoint(path="/a", method="POST", operation_id="bookTime", tags=[]),
        Endpoint(path="/b", method="POST", operation_id="BOOKTIME", tags=[]),
        Endpoint(path="/c", method="POST", operation_id="BookTime", tags=[]),
    ]
    state = _make_state(eps)

    res = {"resourceType": "Appointment", "id": "ignored"}
    msgs = []
    for _ in range(3):
        tb = MagicMock()
        tb.text = json.dumps(res)
        msg = MagicMock()
        msg.content = [tb]
        msgs.append(msg)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=msgs)

    result = await mapping_node(state, client=client, model="test-model")
    ids = [r["id"] for r in result["fhir_resources"]]
    assert ids == ["booktime", "booktime-2", "booktime-3"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mapping_node_repairs_mojibake_in_llm_output() -> None:
    from fhir_forge.nodes.mapping_node import mapping_node

    state = _make_state(
        [Endpoint(path="/p", method="POST", operation_id="getDoctor", tags=[])]
    )
    client = _make_mock_client(
        {
            "resourceType": "Practitioner",
            "id": "p",
            "name": [{"family": "JoÃ£o", "given": ["mÃ©dico"]}],
        }
    )
    result = await mapping_node(state, client=client, model="test-model")
    name = result["fhir_resources"][0]["name"][0]
    assert name["family"] == "João"
    assert name["given"] == ["médico"]


_COVERAGE_RESOURCE = {
    "resourceType": "Coverage",
    "id": "createInsurance-example",
    "status": "active",
    "type": {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/coverage-type",
                "code": "pay",
                "display": "pay",
            }
        ]
    },
    "subscriber": {"reference": "Patient/patient-example"},
    "subscriberId": "INS-000000001",
    "beneficiary": {"reference": "Patient/patient-example"},
    "payor": [
        {
            "identifier": {"system": "http://www.ans.gov.br/", "value": "000000"},
            "display": "Operadora Exemplo",
        }
    ],
    "period": {"start": "2024-01-01"},
}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mapping_node_coverage_resource() -> None:
    """Coverage few-shot produces a resource with type.coding and payor."""
    from fhir_forge.nodes.mapping_node import mapping_node

    state = _make_state(
        [Endpoint(path="/insurances", method="POST", operation_id="createInsurance", tags=["insurance"])]
    )
    client = _make_mock_client(_COVERAGE_RESOURCE)
    result = await mapping_node(state, client=client, model="test-model")
    assert len(result["fhir_resources"]) == 1
    r = result["fhir_resources"][0]
    assert r["resourceType"] == "Coverage"
    assert "type" in r
    assert "coding" in r["type"]
    assert r["type"]["coding"][0]["code"] == "pay"
    assert "payor" in r
    assert r["payor"][0]["display"] == "Operadora Exemplo"
