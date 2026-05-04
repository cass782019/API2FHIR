"""Unit tests for HAPI MCP tools using respx to mock HTTP."""
from __future__ import annotations

import json

import pytest
import respx
from httpx import Response
from mcp_server.tools.hapi import (
    expand_valueset,
    get_resource,
    search_resources,
    validate_resource,
)

HAPI_BASE = "http://localhost:8090/fhir"


@pytest.mark.unit
async def test_validate_resource_valid() -> None:
    resource = {"resourceType": "Patient", "id": "p1"}
    outcome = {"resourceType": "OperationOutcome", "issue": [{"severity": "information", "code": "informational", "details": {"text": "OK"}}]}

    with respx.mock:
        respx.post(f"{HAPI_BASE}/Patient/$validate").mock(return_value=Response(200, json=outcome))
        result = await validate_resource(json.dumps(resource))

    assert result["valid"] is True
    assert len(result["issues"]) == 1


@pytest.mark.unit
async def test_validate_resource_invalid() -> None:
    resource = {"resourceType": "Patient"}
    outcome = {
        "resourceType": "OperationOutcome",
        "issue": [
            {"severity": "error", "code": "required", "details": {"text": "Patient.name: minimum required = 1"}},
        ],
    }

    with respx.mock:
        respx.post(f"{HAPI_BASE}/Patient/$validate").mock(return_value=Response(200, json=outcome))
        result = await validate_resource(json.dumps(resource))

    assert result["valid"] is False
    assert result["issues"][0]["severity"] == "error"


@pytest.mark.unit
async def test_validate_resource_with_profile() -> None:
    resource = {"resourceType": "Patient", "id": "p1"}
    profile = "http://hl7.org.br/fhir/r4/core/StructureDefinition/BRCorePatient"
    outcome = {"resourceType": "OperationOutcome", "issue": []}

    with respx.mock:
        route = respx.post(f"{HAPI_BASE}/Patient/$validate").mock(return_value=Response(200, json=outcome))
        result = await validate_resource(json.dumps(resource), profile_url=profile)

    assert result["valid"] is True
    assert "profile" in str(route.calls[0].request.url)


@pytest.mark.unit
async def test_get_resource_found() -> None:
    expected = {"resourceType": "Patient", "id": "test-1", "name": [{"family": "Silva"}]}

    with respx.mock:
        respx.get(f"{HAPI_BASE}/Patient/test-1").mock(return_value=Response(200, json=expected))
        result = await get_resource("Patient", "test-1")

    assert result["id"] == "test-1"
    assert result["resourceType"] == "Patient"


@pytest.mark.unit
async def test_get_resource_not_found() -> None:
    with respx.mock:
        respx.get(f"{HAPI_BASE}/Patient/nonexistent").mock(return_value=Response(404))
        result = await get_resource("Patient", "nonexistent")

    assert result["error"] == "not_found"


@pytest.mark.unit
async def test_search_resources_single_page() -> None:
    bundle = {
        "resourceType": "Bundle",
        "total": 2,
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "p1"}},
            {"resource": {"resourceType": "Patient", "id": "p2"}},
        ],
        "link": [],
    }

    with respx.mock:
        respx.get(f"{HAPI_BASE}/Patient").mock(return_value=Response(200, json=bundle))
        result = await search_resources("Patient", "family=Silva")

    assert result["returned"] == 2
    assert result["truncated"] is False
    assert result["results"][0]["id"] == "p1"


@pytest.mark.unit
async def test_search_resources_paginated() -> None:
    # Use a distinct hostname for the next-page URL so respx routes them correctly.
    _PAGE2_URL = "http://hapi-page2.test/fhir/Patient"
    page1 = {
        "resourceType": "Bundle",
        "entry": [{"resource": {"resourceType": "Patient", "id": f"p{i}"}} for i in range(50)],
        "link": [{"relation": "next", "url": _PAGE2_URL}],
    }
    page2 = {
        "resourceType": "Bundle",
        "entry": [{"resource": {"resourceType": "Patient", "id": f"p{i}"}} for i in range(50, 60)],
        "link": [],
    }

    with respx.mock:
        respx.get(f"{HAPI_BASE}/Patient").mock(return_value=Response(200, json=page1))
        respx.get(_PAGE2_URL).mock(return_value=Response(200, json=page2))
        result = await search_resources("Patient", "family=Santos")

    assert result["returned"] == 60
    assert result["truncated"] is False


@pytest.mark.unit
async def test_search_resources_truncated_at_200() -> None:
    """When a next page exists after 200 results, truncated=True is set."""
    _PAGE2_URL = "http://hapi-truncate.test/fhir/Patient"
    page1 = {
        "resourceType": "Bundle",
        "entry": [{"resource": {"resourceType": "Patient", "id": f"p{i}"}} for i in range(200)],
        "link": [{"relation": "next", "url": _PAGE2_URL}],
    }

    with respx.mock:
        respx.get(f"{HAPI_BASE}/Patient").mock(return_value=Response(200, json=page1))
        result = await search_resources("Patient", "family=Muitos")

    assert result["returned"] == 200
    assert result["truncated"] is True
    assert result["total"] == 200


@pytest.mark.unit
async def test_expand_valueset() -> None:
    expansion = {
        "resourceType": "ValueSet",
        "expansion": {
            "contains": [
                {"system": "http://www.datasus.gov.br/cid10", "code": "E11", "display": "Diabetes mellitus não-insulinodependente"},
                {"system": "http://www.datasus.gov.br/cid10", "code": "E10", "display": "Diabetes mellitus insulinodependente"},
            ]
        },
    }

    with respx.mock:
        respx.get(f"{HAPI_BASE}/ValueSet/$expand").mock(return_value=Response(200, json=expansion))
        results = await expand_valueset("http://example.org/vs/diabetes")

    assert len(results) == 2
    assert results[0]["code"] == "E11"


@pytest.mark.unit
async def test_expand_valueset_with_filter() -> None:
    expansion = {
        "resourceType": "ValueSet",
        "expansion": {
            "contains": [{"system": "http://www.datasus.gov.br/cid10", "code": "E11", "display": "Diabetes mellitus não-insulinodependente"}]
        },
    }

    with respx.mock:
        route = respx.get(f"{HAPI_BASE}/ValueSet/$expand").mock(return_value=Response(200, json=expansion))
        results = await expand_valueset("http://example.org/vs/diabetes", filter="insulino")

    assert len(results) == 1
    assert "filter" in str(route.calls[0].request.url)
