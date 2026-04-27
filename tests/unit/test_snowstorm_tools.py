"""Unit tests for Snowstorm MCP tools using respx to mock HTTP."""
from __future__ import annotations

import pytest
import respx
from httpx import Response
from mcp_server.tools.snowstorm import find_concept, translate_code

SNOWSTORM_BASE = "http://localhost:8080"
HAPI_BASE = "http://localhost:8090/fhir"
SNOMED_SYSTEM = "http://snomed.info/sct"


@pytest.mark.unit
async def test_find_concept_returns_matches() -> None:
    snowstorm_response = {
        "items": [
            {
                "conceptId": "73211009",
                "fsn": {"term": "Diabetes mellitus (disorder)"},
                "pt": {"term": "Diabetes mellitus"},
                "active": True,
            },
            {
                "conceptId": "44054006",
                "fsn": {"term": "Type 2 diabetes mellitus (disorder)"},
                "pt": {"term": "Type 2 diabetes mellitus"},
                "active": True,
            },
        ]
    }

    with respx.mock:
        respx.get(f"{SNOWSTORM_BASE}/browser/MAIN/concepts").mock(
            return_value=Response(200, json=snowstorm_response)
        )
        results = await find_concept("diabetes mellitus")

    assert len(results) == 2
    assert results[0]["system"] == SNOMED_SYSTEM
    assert results[0]["code"] == "73211009"
    assert "Diabetes" in results[0]["display"]
    assert results[0]["active"] is True


@pytest.mark.unit
async def test_find_concept_with_ecl_filter() -> None:
    snowstorm_response = {"items": []}

    with respx.mock:
        route = respx.get(f"{SNOWSTORM_BASE}/browser/MAIN/concepts").mock(
            return_value=Response(200, json=snowstorm_response)
        )
        results = await find_concept("diabetes", ecl_filter="<< 73211009")

    assert results == []
    assert "ecl" in str(route.calls[0].request.url)


@pytest.mark.unit
async def test_find_concept_not_found() -> None:
    with respx.mock:
        respx.get(f"{SNOWSTORM_BASE}/browser/MAIN/concepts").mock(
            return_value=Response(404)
        )
        results = await find_concept("xyznonexistentterm123")

    assert results == []


@pytest.mark.unit
async def test_find_concept_snowstorm_unavailable() -> None:
    import httpx

    with respx.mock:
        respx.get(f"{SNOWSTORM_BASE}/browser/MAIN/concepts").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        results = await find_concept("diabetes")

    assert len(results) == 1
    assert results[0]["error"] == "snowstorm_unavailable"


@pytest.mark.unit
async def test_translate_code_found() -> None:
    outcome = {
        "resourceType": "Parameters",
        "parameter": [
            {
                "name": "result",
                "valueBoolean": True,
            },
            {
                "name": "match",
                "part": [
                    {
                        "name": "equivalence",
                        "valueCode": "equivalent",
                    },
                    {
                        "name": "concept",
                        "valueCoding": {
                            "system": SNOMED_SYSTEM,
                            "code": "44054006",
                            "display": "Type 2 diabetes mellitus",
                        },
                    },
                ],
            },
        ],
    }

    with respx.mock:
        respx.get(f"{HAPI_BASE}/ConceptMap/$translate").mock(
            return_value=Response(200, json=outcome)
        )
        result = await translate_code(
            source_system="http://www.datasus.gov.br/cid10",
            source_code="E11",
            target_system=SNOMED_SYSTEM,
        )

    assert result is not None
    assert result["code"] == "44054006"
    assert result["system"] == SNOMED_SYSTEM


@pytest.mark.unit
async def test_translate_code_not_found() -> None:
    with respx.mock:
        respx.get(f"{HAPI_BASE}/ConceptMap/$translate").mock(
            return_value=Response(404)
        )
        result = await translate_code(
            source_system="http://example.org/unknown",
            source_code="XYZ",
            target_system=SNOMED_SYSTEM,
        )

    assert result is None


@pytest.mark.unit
async def test_translate_code_no_match_in_outcome() -> None:
    outcome = {
        "resourceType": "Parameters",
        "parameter": [{"name": "result", "valueBoolean": False}],
    }

    with respx.mock:
        respx.get(f"{HAPI_BASE}/ConceptMap/$translate").mock(
            return_value=Response(200, json=outcome)
        )
        result = await translate_code(
            source_system="http://www.datasus.gov.br/cid10",
            source_code="E11",
            target_system=SNOMED_SYSTEM,
        )

    assert result is None
