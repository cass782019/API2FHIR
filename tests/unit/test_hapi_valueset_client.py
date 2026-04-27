from __future__ import annotations

import pytest
import respx
from httpx import Response

_HAPI_BASE = "http://hapi.test/fhir"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expand_returns_codings() -> None:
    from term_mapper.hapi_valueset_client import HapiValueSetClient

    payload = {
        "expansion": {
            "contains": [
                {"system": "http://snomed.info/sct", "code": "73211009", "display": "Diabetes mellitus"},
                {"system": "http://snomed.info/sct", "code": "38341003", "display": "Hypertension"},
            ]
        }
    }
    with respx.mock:
        respx.get(f"{_HAPI_BASE}/ValueSet/$expand").mock(return_value=Response(200, json=payload))
        client = HapiValueSetClient(_HAPI_BASE)
        results = await client.expand("http://hl7.org/fhir/ValueSet/condition-code")

    assert len(results) == 2
    assert results[0].code == "73211009"
    assert results[1].code == "38341003"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expand_empty_expansion() -> None:
    from term_mapper.hapi_valueset_client import HapiValueSetClient

    with respx.mock:
        respx.get(f"{_HAPI_BASE}/ValueSet/$expand").mock(
            return_value=Response(200, json={"expansion": {"contains": []}})
        )
        client = HapiValueSetClient(_HAPI_BASE)
        results = await client.expand("http://hl7.org/fhir/ValueSet/empty")

    assert results == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expand_http_error_returns_empty() -> None:
    from term_mapper.hapi_valueset_client import HapiValueSetClient

    with respx.mock:
        respx.get(f"{_HAPI_BASE}/ValueSet/$expand").mock(return_value=Response(500, text="error"))
        client = HapiValueSetClient(_HAPI_BASE)
        results = await client.expand("http://hl7.org/fhir/ValueSet/condition-code")

    assert results == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expand_with_filter_passes_param() -> None:
    from term_mapper.hapi_valueset_client import HapiValueSetClient

    with respx.mock:
        route = respx.get(f"{_HAPI_BASE}/ValueSet/$expand").mock(
            return_value=Response(200, json={"expansion": {"contains": []}})
        )
        client = HapiValueSetClient(_HAPI_BASE)
        await client.expand("http://hl7.org/fhir/ValueSet/condition-code", filter_text="diab")

    request = route.calls.last.request
    assert "filter" in str(request.url)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lookup_returns_coding() -> None:
    from term_mapper.hapi_valueset_client import HapiValueSetClient

    payload = {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "display", "valueString": "Diabetes mellitus"},
        ],
    }
    with respx.mock:
        respx.get(f"{_HAPI_BASE}/CodeSystem/$lookup").mock(return_value=Response(200, json=payload))
        client = HapiValueSetClient(_HAPI_BASE)
        result = await client.lookup("http://snomed.info/sct", "73211009")

    assert result is not None
    assert result.code == "73211009"
    assert result.display == "Diabetes mellitus"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lookup_404_returns_none() -> None:
    from term_mapper.hapi_valueset_client import HapiValueSetClient

    with respx.mock:
        respx.get(f"{_HAPI_BASE}/CodeSystem/$lookup").mock(return_value=Response(404, text="Not Found"))
        client = HapiValueSetClient(_HAPI_BASE)
        result = await client.lookup("http://snomed.info/sct", "99999999")

    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lookup_500_returns_none() -> None:
    from term_mapper.hapi_valueset_client import HapiValueSetClient

    with respx.mock:
        respx.get(f"{_HAPI_BASE}/CodeSystem/$lookup").mock(return_value=Response(500, text="Server Error"))
        client = HapiValueSetClient(_HAPI_BASE)
        result = await client.lookup("http://snomed.info/sct", "73211009")

    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lookup_no_display_param_returns_empty_display() -> None:
    from term_mapper.hapi_valueset_client import HapiValueSetClient

    payload = {"resourceType": "Parameters", "parameter": [{"name": "name", "valueString": "SNOMED CT"}]}
    with respx.mock:
        respx.get(f"{_HAPI_BASE}/CodeSystem/$lookup").mock(return_value=Response(200, json=payload))
        client = HapiValueSetClient(_HAPI_BASE)
        result = await client.lookup("http://snomed.info/sct", "73211009")

    assert result is not None
    assert result.display == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expand_skips_entries_missing_system_or_code() -> None:
    from term_mapper.hapi_valueset_client import HapiValueSetClient

    payload = {
        "expansion": {
            "contains": [
                {"system": "http://snomed.info/sct", "code": "73211009", "display": "Diabetes"},
                {"system": "", "code": "bad-entry"},   # missing system — should be skipped
                {"code": "also-bad"},                   # no system at all
            ]
        }
    }
    with respx.mock:
        respx.get(f"{_HAPI_BASE}/ValueSet/$expand").mock(return_value=Response(200, json=payload))
        client = HapiValueSetClient(_HAPI_BASE)
        results = await client.expand("http://hl7.org/fhir/ValueSet/condition-code")

    assert len(results) == 1
    assert results[0].code == "73211009"
