from __future__ import annotations

import pytest
import respx
from httpx import Response

_HAPI = "http://hapi.test/fhir"

_PATIENT = {
    "resourceType": "Patient",
    "id": "p1",
    "name": [{"use": "official", "family": "Silva"}],
}

_ENCOUNTER = {
    "resourceType": "Encounter",
    "id": "e1",
    "status": "finished",
}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_returns_resource() -> None:
    from connectors.hapi_client import HapiFhirClient

    with respx.mock:
        respx.post(f"{_HAPI}/Patient").mock(return_value=Response(201, json=_PATIENT))
        client = HapiFhirClient(_HAPI)
        result = await client.create(_PATIENT)

    assert result["id"] == "p1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_read_returns_resource() -> None:
    from connectors.hapi_client import HapiFhirClient

    with respx.mock:
        respx.get(f"{_HAPI}/Patient/p1").mock(return_value=Response(200, json=_PATIENT))
        client = HapiFhirClient(_HAPI)
        result = await client.read("Patient", "p1")

    assert result is not None
    assert result["id"] == "p1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_read_404_returns_none() -> None:
    from connectors.hapi_client import HapiFhirClient

    with respx.mock:
        respx.get(f"{_HAPI}/Patient/missing").mock(return_value=Response(404, json={}))
        client = HapiFhirClient(_HAPI)
        result = await client.read("Patient", "missing")

    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_returns_resource() -> None:
    from connectors.hapi_client import HapiFhirClient

    updated = {**_PATIENT, "name": [{"use": "official", "family": "Moralles"}]}
    with respx.mock:
        respx.put(f"{_HAPI}/Patient/p1").mock(return_value=Response(200, json=updated))
        client = HapiFhirClient(_HAPI)
        result = await client.update(updated)

    assert result["name"][0]["family"] == "Moralles"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_succeeds_on_204() -> None:
    from connectors.hapi_client import HapiFhirClient

    with respx.mock:
        respx.delete(f"{_HAPI}/Patient/p1").mock(return_value=Response(204))
        client = HapiFhirClient(_HAPI)
        await client.delete("Patient", "p1")  # should not raise


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_succeeds_on_200() -> None:
    from connectors.hapi_client import HapiFhirClient

    with respx.mock:
        respx.delete(f"{_HAPI}/Patient/p1").mock(return_value=Response(200, json={}))
        client = HapiFhirClient(_HAPI)
        await client.delete("Patient", "p1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_returns_resources() -> None:
    from connectors.hapi_client import HapiFhirClient

    bundle = {
        "resourceType": "Bundle",
        "entry": [{"resource": _PATIENT}, {"resource": _ENCOUNTER}],
        "link": [],
    }
    with respx.mock:
        respx.get(f"{_HAPI}/Patient").mock(return_value=Response(200, json=bundle))
        client = HapiFhirClient(_HAPI)
        results = await client.search("Patient", {"name": "Silva"})

    assert len(results) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_follows_next_link() -> None:
    from connectors.hapi_client import HapiFhirClient

    # Use a completely different host for the "next" URL so respx can distinguish
    # the two routes without ambiguity from query-param matching.
    next_url = "http://hapi-page2.test/fhir/Patient"
    page1 = {
        "resourceType": "Bundle",
        "entry": [{"resource": _PATIENT}],
        "link": [{"relation": "next", "url": next_url}],
    }
    page2 = {
        "resourceType": "Bundle",
        "entry": [{"resource": _ENCOUNTER}],
        "link": [],
    }
    with respx.mock:
        respx.get(f"{_HAPI}/Patient").mock(return_value=Response(200, json=page1))
        respx.get(next_url).mock(return_value=Response(200, json=page2))
        client = HapiFhirClient(_HAPI)
        results = await client.search("Patient", {})

    assert len(results) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_empty_bundle_returns_empty() -> None:
    from connectors.hapi_client import HapiFhirClient

    bundle = {"resourceType": "Bundle", "entry": [], "link": []}
    with respx.mock:
        respx.get(f"{_HAPI}/Patient").mock(return_value=Response(200, json=bundle))
        client = HapiFhirClient(_HAPI)
        results = await client.search("Patient", {})

    assert results == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_valid_resource() -> None:
    from connectors.hapi_client import HapiFhirClient

    outcome = {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": "information", "code": "informational", "diagnostics": "OK"}],
    }
    with respx.mock:
        respx.post(f"{_HAPI}/Patient/$validate").mock(return_value=Response(200, json=outcome))
        client = HapiFhirClient(_HAPI)
        result = await client.validate(_PATIENT)

    assert result.valid is True
    assert len(result.issues) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_invalid_resource() -> None:
    from connectors.hapi_client import HapiFhirClient

    outcome = {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": "error", "code": "required", "diagnostics": "Missing id"}],
    }
    with respx.mock:
        respx.post(f"{_HAPI}/Patient/$validate").mock(return_value=Response(422, json=outcome))
        client = HapiFhirClient(_HAPI)
        result = await client.validate(_PATIENT)

    assert result.valid is False
    assert result.has_errors() is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_with_profile_passes_param() -> None:
    from connectors.hapi_client import HapiFhirClient

    outcome = {"resourceType": "OperationOutcome", "issue": []}
    with respx.mock:
        route = respx.post(f"{_HAPI}/Patient/$validate").mock(return_value=Response(200, json=outcome))
        client = HapiFhirClient(_HAPI)
        await client.validate(_PATIENT, profile="http://hl7.org/fhir/StructureDefinition/Patient")

    request = route.calls.last.request
    assert "profile" in str(request.url)
