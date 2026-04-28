from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from swagger_lens.models import Endpoint, SwaggerSpec


def _make_spec_multi() -> SwaggerSpec:
    """3 endpoints distintos para forçar bundle não-trivial."""
    return SwaggerSpec(
        title="Bundle Validation API",
        version="1.0.0",
        base_url="https://api.test.com",
        openapi_version="3.0.3",
        endpoints=[
            Endpoint(path="/patients", method="POST", operation_id="createPatient", tags=["p"]),
            Endpoint(path="/practitioners", method="GET", operation_id="getDoctor", tags=["p"]),
            Endpoint(path="/observations", method="POST", operation_id="recordObs", tags=["o"]),
        ],
    )


def _mock_llm(resources: list[dict[str, Any]]) -> MagicMock:
    idx = 0

    async def _se(*a: Any, **k: Any) -> Any:
        nonlocal idx
        tb = MagicMock()
        tb.text = json.dumps(resources[idx % len(resources)])
        msg = MagicMock()
        msg.content = [tb]
        idx += 1
        return msg

    c = MagicMock()
    c.messages = MagicMock()
    c.messages.create = AsyncMock(side_effect=_se)
    return c


_VALID_RESOURCES = [
    {"resourceType": "Patient", "id": "p1", "gender": "female"},
    {"resourceType": "Practitioner", "id": "pr1", "active": True},
    {
        "resourceType": "Observation",
        "id": "o1",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "1234-5"}]},
        "subject": {"reference": "Patient/p1"},
    },
]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bundle_validates_with_zero_fatal_errors(hapi_base_url: str) -> None:
    """Bundle gerado passa em Bundle/$validate sem erros fatais."""
    from fhir_forge.service import convert

    spec = _make_spec_multi()
    client = _mock_llm(_VALID_RESOURCES)

    bundle = await convert(
        spec,
        "int-validate-01",
        client=client,
        model="test-model",
        hapi_base_url=hapi_base_url,
    )

    async with httpx.AsyncClient(timeout=60.0) as http:
        r = await http.post(
            f"{hapi_base_url}/Bundle/$validate",
            json=bundle,
            headers={"Content-Type": "application/fhir+json"},
        )
    oo = r.json()
    fatals = [
        i for i in oo.get("issue", []) if i.get("severity") in ("error", "fatal")
    ]
    assert fatals == [], f"Bundle has fatal validation issues: {fatals}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bundle_has_zero_dom6_warnings(hapi_base_url: str) -> None:
    """O bundle_node deve injetar narrativa que elimina todos os warnings dom-6."""
    from fhir_forge.service import convert

    spec = _make_spec_multi()
    client = _mock_llm(_VALID_RESOURCES)
    bundle = await convert(
        spec,
        "int-validate-02",
        client=client,
        model="test-model",
        hapi_base_url=hapi_base_url,
    )

    async with httpx.AsyncClient(timeout=60.0) as http:
        r = await http.post(
            f"{hapi_base_url}/Bundle/$validate",
            json=bundle,
            headers={"Content-Type": "application/fhir+json"},
        )
    oo = r.json()
    dom6 = [
        i for i in oo.get("issue", []) if "dom-6" in (i.get("diagnostics") or "")
    ]
    assert dom6 == [], f"Found {len(dom6)} dom-6 warnings (expected 0)"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bundle_full_urls_are_valid_uuid_v4(hapi_base_url: str) -> None:
    """Todo entry.fullUrl casa o regex UUID v4 lowercase."""
    from fhir_forge.service import convert

    spec = _make_spec_multi()
    client = _mock_llm([{"resourceType": "Patient", "id": "p1", "gender": "other"}])
    bundle = await convert(
        spec,
        "int-validate-03",
        client=client,
        model="test-model",
        hapi_base_url=hapi_base_url,
    )

    pat = re.compile(
        r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    for entry in bundle["entry"]:
        assert pat.match(entry["fullUrl"]), entry["fullUrl"]
