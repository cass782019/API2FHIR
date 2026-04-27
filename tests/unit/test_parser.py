from __future__ import annotations

import json

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st


OAS3_MINIMAL = {
    "openapi": "3.0.3",
    "info": {"title": "Test API", "version": "1.0.0"},
    "paths": {},
}

OAS2_MINIMAL = {
    "swagger": "2.0",
    "info": {"title": "Test API", "version": "1.0.0"},
    "paths": {},
    "host": "example.com",
    "basePath": "/",
}

OAS3_WITH_PATHS = {
    "openapi": "3.0.3",
    "info": {"title": "Health API", "version": "2.0.0"},
    "servers": [{"url": "https://api.example.com/v2"}],
    "paths": {
        "/patients": {
            "get": {
                "operationId": "listPatients",
                "summary": "List patients",
                "tags": ["patient"],
                "parameters": [
                    {
                        "name": "name",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {"200": {"description": "OK"}},
            },
            "post": {
                "operationId": "createPatient",
                "summary": "Create patient",
                "requestBody": {
                    "content": {
                        "application/json": {"schema": {"type": "object"}}
                    }
                },
                "responses": {"201": {"description": "Created"}},
            },
        },
    },
}

OAS2_WITH_BODY = {
    "swagger": "2.0",
    "info": {"title": "Legacy API", "version": "1.0.0"},
    "host": "legacy.example.com",
    "basePath": "/api",
    "schemes": ["https"],
    "paths": {
        "/patients": {
            "post": {
                "operationId": "createPatient",
                "summary": "Create patient",
                "parameters": [
                    {
                        "in": "body",
                        "name": "body",
                        "required": True,
                        "schema": {"type": "object"},
                    }
                ],
                "responses": {"201": {"description": "Created"}},
            }
        }
    },
}


@pytest.mark.unit
def test_parse_oas3_minimal_yaml() -> None:
    from swagger_lens.parser import parse_spec

    content = yaml.dump(OAS3_MINIMAL)
    spec = parse_spec(content, fmt="yaml")
    assert spec.title == "Test API"
    assert spec.version == "1.0.0"
    assert spec.openapi_version == "3.0.3"
    assert spec.endpoints == []


@pytest.mark.unit
def test_parse_oas3_minimal_json() -> None:
    from swagger_lens.parser import parse_spec

    content = json.dumps(OAS3_MINIMAL)
    spec = parse_spec(content, fmt="json")
    assert spec.title == "Test API"


@pytest.mark.unit
def test_parse_oas3_auto_detects_json() -> None:
    from swagger_lens.parser import parse_spec

    content = json.dumps(OAS3_MINIMAL)
    spec = parse_spec(content, fmt="auto")
    assert spec.openapi_version == "3.0.3"


@pytest.mark.unit
def test_parse_oas3_auto_detects_yaml() -> None:
    from swagger_lens.parser import parse_spec

    content = yaml.dump(OAS3_MINIMAL)
    spec = parse_spec(content, fmt="auto")
    assert spec.openapi_version == "3.0.3"


@pytest.mark.unit
def test_parse_oas2_minimal() -> None:
    from swagger_lens.parser import parse_spec

    content = yaml.dump(OAS2_MINIMAL)
    spec = parse_spec(content, fmt="yaml")
    assert spec.openapi_version == "2.0"
    assert "example.com" in spec.base_url


@pytest.mark.unit
def test_parse_oas3_base_url_from_servers() -> None:
    from swagger_lens.parser import parse_spec

    content = yaml.dump(OAS3_WITH_PATHS)
    spec = parse_spec(content, fmt="yaml")
    assert spec.base_url == "https://api.example.com/v2"


@pytest.mark.unit
def test_parse_oas3_endpoints_extracted() -> None:
    from swagger_lens.parser import parse_spec

    content = yaml.dump(OAS3_WITH_PATHS)
    spec = parse_spec(content, fmt="yaml")
    assert len(spec.endpoints) == 2
    methods = {e.method for e in spec.endpoints}
    assert "GET" in methods
    assert "POST" in methods


@pytest.mark.unit
def test_parse_oas3_endpoint_fields() -> None:
    from swagger_lens.parser import parse_spec

    content = yaml.dump(OAS3_WITH_PATHS)
    spec = parse_spec(content, fmt="yaml")
    get_ep = next(e for e in spec.endpoints if e.method == "GET")
    assert get_ep.operation_id == "listPatients"
    assert get_ep.summary == "List patients"
    assert get_ep.tags == ["patient"]
    assert len(get_ep.params) == 1
    assert get_ep.params[0].name == "name"
    assert get_ep.params[0].location == "query"


@pytest.mark.unit
def test_parse_oas3_post_has_request_body() -> None:
    from swagger_lens.parser import parse_spec

    content = yaml.dump(OAS3_WITH_PATHS)
    spec = parse_spec(content, fmt="yaml")
    post_ep = next(e for e in spec.endpoints if e.method == "POST")
    assert post_ep.request_body is not None


@pytest.mark.unit
def test_parse_oas2_body_param_becomes_request_body() -> None:
    from swagger_lens.parser import parse_spec

    content = yaml.dump(OAS2_WITH_BODY)
    spec = parse_spec(content, fmt="yaml")
    assert len(spec.endpoints) == 1
    ep = spec.endpoints[0]
    assert ep.request_body is not None
    assert ep.params == []  # body param should NOT appear in params


@pytest.mark.unit
def test_parse_invalid_json_raises() -> None:
    from swagger_lens.parser import SpecParseError, parse_spec

    with pytest.raises(SpecParseError, match="JSON"):
        parse_spec("{not valid json}", fmt="json")


@pytest.mark.unit
def test_parse_invalid_yaml_raises() -> None:
    from swagger_lens.parser import SpecParseError, parse_spec

    with pytest.raises(SpecParseError):
        parse_spec("key: [unclosed", fmt="yaml")


@pytest.mark.unit
def test_parse_missing_version_raises() -> None:
    from swagger_lens.parser import SpecParseError, parse_spec

    content = json.dumps({"info": {"title": "No version"}})
    with pytest.raises(SpecParseError, match="version"):
        parse_spec(content, fmt="json")


@pytest.mark.unit
def test_parse_invalid_spec_raises_fhirforge_error() -> None:
    from core.exceptions import FhirForgeError
    from swagger_lens.parser import parse_spec

    invalid = {"openapi": "3.0.3", "info": {}, "paths": {}}  # missing required info fields
    content = json.dumps(invalid)
    with pytest.raises(FhirForgeError):
        parse_spec(content, fmt="json")


@pytest.mark.unit
def test_parse_bytes_content() -> None:
    from swagger_lens.parser import parse_spec

    content = json.dumps(OAS3_MINIMAL).encode()
    spec = parse_spec(content, fmt="json")
    assert spec.title == "Test API"


@pytest.mark.unit
def test_parse_oas3_raw_preserved() -> None:
    from swagger_lens.parser import parse_spec

    content = yaml.dump(OAS3_MINIMAL)
    spec = parse_spec(content, fmt="yaml")
    assert spec.raw["info"]["title"] == "Test API"


@pytest.mark.unit
def test_parse_oas2_base_url_uses_scheme() -> None:
    from swagger_lens.parser import parse_spec

    spec_dict = {**OAS2_MINIMAL, "schemes": ["http"]}
    content = yaml.dump(spec_dict)
    spec = parse_spec(content, fmt="yaml")
    assert spec.base_url.startswith("http://")


# ── Hypothesis property tests ─────────────────────────────────────────────────


def _minimal_oas3(title: str, version: str) -> dict:  # type: ignore[type-arg]
    """Build a minimal but valid OAS 3.0.3 spec."""
    return {
        "openapi": "3.0.3",
        "info": {"title": title or "t", "version": version or "0.0.1"},
        "paths": {},
    }


@pytest.mark.unit
@settings(max_examples=200, deadline=None)
@given(
    title=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs"))),
    version=st.from_regex(r"[0-9]+\.[0-9]+\.[0-9]+", fullmatch=True),
)
def test_hypothesis_minimal_spec_never_raises(title: str, version: str) -> None:
    """parse_spec must not raise on any minimal valid OAS3 spec."""
    from swagger_lens.parser import parse_spec

    spec_dict = _minimal_oas3(title.strip() or "API", version)
    content = json.dumps(spec_dict)
    result = parse_spec(content, fmt="json")
    assert result.title is not None
    assert result.endpoints == []
