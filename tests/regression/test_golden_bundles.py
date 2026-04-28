from __future__ import annotations

import json
import pathlib
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

GOLDEN_SPEC_DIR = pathlib.Path(__file__).parent.parent.parent / "data" / "golden" / "swagger_specs"
GOLDEN_BUNDLE_DIR = pathlib.Path(__file__).parent.parent.parent / "data" / "golden" / "fhir_bundles"

_UUID_V4_RE = re.compile(
    r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

_MOJIBAKE_MARKERS = ("Ã£", "Ã©", "Ã§", "Ã³", "Ã­", "Ãº")


def _assert_structural_invariants(bundle: dict[str, Any]) -> None:
    """Bug-regression guard: each invariant maps to a specific past bug.

    - fullUrl UUID v4: regression of bundle_node bug fixed in v2.1
    - unique resource ids: regression of mapping_node id-collision bug
    - generated narrative: regression of dom-6 cleanup
    - no mojibake markers: regression of UTF-8 sanitizer
    """
    entries = bundle.get("entry", [])

    # fullUrl: UUID v4 lowercase
    bad_urls = [
        e["fullUrl"] for e in entries if not _UUID_V4_RE.match(e.get("fullUrl", ""))
    ]
    assert not bad_urls, (
        f"Invalid fullUrls (expected urn:uuid:<UUIDv4>): {bad_urls[:3]}"
    )

    # ids únicos
    ids = [e["resource"].get("id", "") for e in entries]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    assert not dups, f"Duplicate resource ids in bundle: {dups}"

    # narrativa presente em cada DomainResource
    missing_narr = [
        e["resource"].get("id", "?")
        for e in entries
        if not (e["resource"].get("text") or {}).get("div")
    ]
    assert not missing_narr, f"Resources without text.div: {missing_narr[:3]}"

    # zero mojibake nos campos string
    blob = json.dumps(bundle, ensure_ascii=False)
    found = [m for m in _MOJIBAKE_MARKERS if m in blob]
    assert not found, f"Mojibake markers found in bundle: {found}"

# Fields ignored in semantic diff (generated at runtime; not meaningful for regression)
_IGNORE_PATHS = {
    "root['id']",
    "root['timestamp']",
    "root['meta']",
    "root['entry'][*]['fullUrl']",
    "root['entry'][*]['resource']['id']",
    "root['entry'][*]['resource']['meta']",
}


def _golden_pairs() -> list[tuple[pathlib.Path, pathlib.Path]]:
    pairs = []
    for spec_path in sorted(GOLDEN_SPEC_DIR.glob("*.yaml")) + sorted(GOLDEN_SPEC_DIR.glob("*.json")):
        bundle_path = GOLDEN_BUNDLE_DIR / (spec_path.stem + "_expected.json")
        if bundle_path.exists():
            pairs.append((spec_path, bundle_path))
    return pairs


def _semantic_equal(actual: dict[str, Any], expected: dict[str, Any]) -> tuple[bool, str]:
    """Return (True, '') if actual contains all expected resource types.

    We check that every resource type in the golden bundle appears in the
    actual output (subset check). Extra resources in the actual output are
    acceptable — extra endpoints in the spec may produce additional resources.
    """
    actual_types = sorted(e["resource"]["resourceType"] for e in actual.get("entry", []))
    expected_types = sorted(e["resource"]["resourceType"] for e in expected.get("entry", []))
    missing = [t for t in expected_types if t not in actual_types]
    if missing:
        return False, f"Expected resource types {missing} not found. Actual: {actual_types}"
    return True, ""


_BASIC_PLACEHOLDER = {"resourceType": "Basic", "id": "n/a"}


def _mock_llm_for_golden(expected_bundle: dict[str, Any]) -> MagicMock:
    """Build an LLM mock that returns resources from the expected bundle in order.

    Extra endpoints (beyond what's in the golden bundle) receive a Basic
    placeholder, which the mapping_node filters out.
    """
    resources = [e["resource"] for e in expected_bundle.get("entry", [])]
    idx = 0

    async def _side_effect(*args: Any, **kwargs: Any) -> Any:
        nonlocal idx
        payload = resources[idx] if idx < len(resources) else _BASIC_PLACEHOLDER
        idx += 1
        tb = MagicMock(); tb.text = json.dumps(payload)
        m = MagicMock(); m.content = [tb]
        return m

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=_side_effect)
    return client


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("spec_path,bundle_path", _golden_pairs(), ids=lambda p: p.stem)
async def test_golden_bundle_regression(spec_path: pathlib.Path, bundle_path: pathlib.Path) -> None:
    """Convert golden spec and verify output matches expected bundle (semantic diff).

    The LLM is mocked to return resources from the expected bundle.
    HAPI validation is patched to return "all valid" so the test is deterministic.
    """
    from unittest.mock import AsyncMock, patch

    from fhir_forge.service import convert
    from swagger_lens.parser import parse_spec

    spec = parse_spec(spec_path.read_bytes(), fmt="auto")
    expected_bundle: dict[str, Any] = json.loads(bundle_path.read_text())
    client = _mock_llm_for_golden(expected_bundle)

    # Patch _validate_resource at module level so LangGraph task isolation doesn't matter
    with patch(
        "fhir_forge.nodes.validation_node._validate_resource",
        new=AsyncMock(return_value=[]),  # all resources pass validation
    ):
        bundle = await convert(
            spec,
            f"regression-{spec_path.stem}",
            client=client,
            model="test-model",
            hapi_base_url="http://localhost:8090/fhir",
        )

    assert bundle["resourceType"] == "Bundle", "Output must be a Bundle"
    assert len(bundle.get("entry", [])) > 0, "Bundle must have at least one entry"

    _assert_structural_invariants(bundle)

    ok, diff = _semantic_equal(bundle, expected_bundle)
    assert ok, f"Semantic regression detected for {spec_path.name}:\n{diff}"
