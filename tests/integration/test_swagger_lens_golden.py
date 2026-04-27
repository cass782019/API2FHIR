from __future__ import annotations

import pathlib

import pytest

GOLDEN_DIR = pathlib.Path(__file__).parent.parent.parent / "data" / "golden" / "swagger_specs"


def _golden_specs() -> list[pathlib.Path]:
    if not GOLDEN_DIR.exists():
        return []
    return sorted(GOLDEN_DIR.glob("*.yaml")) + sorted(GOLDEN_DIR.glob("*.json"))


@pytest.mark.integration
@pytest.mark.parametrize("spec_path", _golden_specs(), ids=lambda p: p.name)
def test_golden_spec_parses_without_error(spec_path: pathlib.Path) -> None:
    from swagger_lens.parser import parse_spec

    content = spec_path.read_bytes()
    spec = parse_spec(content, fmt="auto")
    assert spec.title, f"{spec_path.name}: title should not be empty"
    assert spec.version, f"{spec_path.name}: version should not be empty"
    assert spec.openapi_version, f"{spec_path.name}: openapi_version should not be empty"


@pytest.mark.integration
def test_example_api_v3_endpoints() -> None:
    from swagger_lens.parser import parse_spec

    spec_path = GOLDEN_DIR / "example_api.yaml"
    spec = parse_spec(spec_path.read_bytes(), fmt="yaml")
    assert spec.title == "Example Healthcare API"
    assert len(spec.endpoints) >= 5
    paths = {e.path for e in spec.endpoints}
    assert "/patients" in paths
    assert "/encounters" in paths


@pytest.mark.integration
def test_example_api_v3_fhir_hints() -> None:
    from swagger_lens.extractor import extract_fhir_hints
    from swagger_lens.parser import parse_spec

    spec_path = GOLDEN_DIR / "example_api.yaml"
    spec = parse_spec(spec_path.read_bytes(), fmt="yaml")
    all_hints = [h for ep in spec.endpoints for h in extract_fhir_hints(ep)]
    assert "Patient" in all_hints
    assert "Encounter" in all_hints or "Observation" in all_hints


@pytest.mark.integration
def test_example_api_v2_parses() -> None:
    from swagger_lens.parser import parse_spec

    spec_path = GOLDEN_DIR / "example_api_v2.yaml"
    spec = parse_spec(spec_path.read_bytes(), fmt="yaml")
    assert spec.openapi_version == "2.0"
    assert "legacy.hospital.example.com" in spec.base_url
    assert len(spec.endpoints) >= 2


@pytest.mark.integration
def test_example_api_v2_portuguese_fhir_hints() -> None:
    from swagger_lens.extractor import extract_fhir_hints
    from swagger_lens.parser import parse_spec

    spec_path = GOLDEN_DIR / "example_api_v2.yaml"
    spec = parse_spec(spec_path.read_bytes(), fmt="yaml")
    all_hints = [h for ep in spec.endpoints for h in extract_fhir_hints(ep)]
    assert "Patient" in all_hints


@pytest.mark.integration
def test_example_api_v3_allof_schema_in_raw() -> None:
    """Verify allOf schemas appear in the raw spec (used by flattener downstream)."""
    from swagger_lens.parser import parse_spec

    spec_path = GOLDEN_DIR / "example_api.yaml"
    spec = parse_spec(spec_path.read_bytes(), fmt="yaml")
    patient_schema = spec.raw.get("components", {}).get("schemas", {}).get("Patient", {})
    assert "allOf" in patient_schema
