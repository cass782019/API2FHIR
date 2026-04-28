from __future__ import annotations

import re
from typing import Any

import pytest

_UUID_V4_RE = re.compile(
    r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _state(
    resources: list[dict[str, Any]],
    retry_count: int = 0,
    invalid: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "swagger_spec": None,
        "endpoints_to_process": [],
        "fhir_resources": resources,
        "invalid_resources": invalid or [],
        "validation_errors": [],
        "retry_count": retry_count,
        "job_id": "01TESTJOB",
        "trace_id": "",
        "warnings": [],
    }


@pytest.mark.unit
def test_full_url_is_valid_uuid_v4() -> None:
    from fhir_forge.nodes.bundle_node import bundle_node

    out = bundle_node(_state([{"resourceType": "Patient", "id": "p1"}]))
    bundle = out["_bundle"]
    for entry in bundle["entry"]:
        assert _UUID_V4_RE.match(entry["fullUrl"]), entry["fullUrl"]


@pytest.mark.unit
def test_full_urls_unique_even_with_duplicate_ids() -> None:
    """Mesmo se dois resources tiverem o mesmo id, fullUrls devem ser distintos."""
    from fhir_forge.nodes.bundle_node import bundle_node

    out = bundle_node(
        _state(
            [
                {"resourceType": "Patient", "id": "dup"},
                {"resourceType": "Practitioner", "id": "dup"},
            ]
        )
    )
    fulls = [e["fullUrl"] for e in out["_bundle"]["entry"]]
    assert len(fulls) == 2
    assert fulls[0] != fulls[1]


@pytest.mark.unit
def test_bundle_metadata_shape() -> None:
    from fhir_forge.nodes.bundle_node import bundle_node

    out = bundle_node(_state([{"resourceType": "Patient", "id": "p1"}]))
    b = out["_bundle"]
    assert b["resourceType"] == "Bundle"
    assert b["type"] == "collection"
    assert b["id"].startswith("forge-")
    assert "timestamp" in b
    assert b["meta"]["tag"][0]["code"] == "generated"


@pytest.mark.unit
def test_invalid_resources_appended_when_max_retries() -> None:
    """Cobre o branch retry_count >= 3 (linhas 16-20) — sem teste hoje."""
    from fhir_forge.nodes.bundle_node import bundle_node

    state = _state(
        [{"resourceType": "Patient", "id": "ok"}],
        retry_count=3,
        invalid=[{"resourceType": "Encounter", "id": "broken"}],
    )
    out = bundle_node(state)
    types = [e["resource"]["resourceType"] for e in out["_bundle"]["entry"]]
    assert types == ["Patient", "Encounter"]
    assert any("max retries" in w for w in out["warnings"])


@pytest.mark.unit
def test_empty_resources_yields_empty_entries() -> None:
    from fhir_forge.nodes.bundle_node import bundle_node

    out = bundle_node(_state([]))
    assert out["_bundle"]["entry"] == []
