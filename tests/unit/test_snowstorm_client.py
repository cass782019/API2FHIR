from __future__ import annotations

import pytest
import respx
from httpx import Response

_SNOWSTORM_BASE = "http://snowstorm.test"
_SNOMED = "http://snomed.info/sct"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_concept_returns_matches() -> None:
    from term_mapper.snowstorm_client import SnowstormClient

    payload = {
        "items": [
            {
                "conceptId": "73211009",
                "fsn": {"term": "Diabetes mellitus (disorder)"},
                "pt": {"term": "Diabetes mellitus"},
            }
        ]
    }
    with respx.mock:
        respx.get(f"{_SNOWSTORM_BASE}/browser/MAIN/concepts").mock(
            return_value=Response(200, json=payload)
        )
        client = SnowstormClient(_SNOWSTORM_BASE)
        results = await client.find_concept("diabetes")

    assert len(results) == 1
    assert results[0].coding.code == "73211009"
    assert results[0].coding.system == _SNOMED
    assert results[0].source == "snowstorm"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_concept_empty_items() -> None:
    from term_mapper.snowstorm_client import SnowstormClient

    with respx.mock:
        respx.get(f"{_SNOWSTORM_BASE}/browser/MAIN/concepts").mock(
            return_value=Response(200, json={"items": []})
        )
        client = SnowstormClient(_SNOWSTORM_BASE)
        results = await client.find_concept("zzz_nonexistent")

    assert results == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_concept_http_error_returns_empty() -> None:
    from term_mapper.snowstorm_client import SnowstormClient

    with respx.mock:
        respx.get(f"{_SNOWSTORM_BASE}/browser/MAIN/concepts").mock(
            return_value=Response(500, text="Internal Server Error")
        )
        client = SnowstormClient(_SNOWSTORM_BASE)
        results = await client.find_concept("diabetes")

    assert results == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_translate_returns_coding() -> None:
    from term_mapper.snowstorm_client import SnowstormClient

    payload = {
        "parameter": [
            {
                "name": "match",
                "part": [
                    {
                        "name": "concept",
                        "valueCoding": {
                            "system": "http://loinc.org",
                            "code": "2093-3",
                            "display": "Cholesterol",
                        },
                    }
                ],
            }
        ]
    }
    with respx.mock:
        respx.get(f"{_SNOWSTORM_BASE}/fhir/ConceptMap/$translate").mock(
            return_value=Response(200, json=payload)
        )
        client = SnowstormClient(_SNOWSTORM_BASE)
        result = await client.translate(_SNOMED, "73211009", "http://loinc.org")

    assert result is not None
    assert result.code == "2093-3"
    assert result.system == "http://loinc.org"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_translate_404_returns_none() -> None:
    from term_mapper.snowstorm_client import SnowstormClient

    with respx.mock:
        respx.get(f"{_SNOWSTORM_BASE}/fhir/ConceptMap/$translate").mock(
            return_value=Response(404, text="Not Found")
        )
        client = SnowstormClient(_SNOWSTORM_BASE)
        result = await client.translate(_SNOMED, "99999", "http://loinc.org")

    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_translate_no_match_returns_none() -> None:
    from term_mapper.snowstorm_client import SnowstormClient

    with respx.mock:
        respx.get(f"{_SNOWSTORM_BASE}/fhir/ConceptMap/$translate").mock(
            return_value=Response(200, json={"parameter": []})
        )
        client = SnowstormClient(_SNOWSTORM_BASE)
        result = await client.translate(_SNOMED, "73211009", "http://loinc.org")

    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_find_concept_with_ecl_passes_param() -> None:
    from term_mapper.snowstorm_client import SnowstormClient

    with respx.mock:
        route = respx.get(f"{_SNOWSTORM_BASE}/browser/MAIN/concepts").mock(
            return_value=Response(200, json={"items": []})
        )
        client = SnowstormClient(_SNOWSTORM_BASE)
        await client.find_concept("hypertension", ecl="<404684003")

    request = route.calls.last.request
    assert "ecl" in str(request.url)
