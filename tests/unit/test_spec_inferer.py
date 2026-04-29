from __future__ import annotations

import json

import pytest


@pytest.mark.unit
def test_detect_openapi_3() -> None:
    from spec_inferer.detector import detect_spec_type

    spec = json.dumps({"openapi": "3.0.3", "info": {}, "paths": {}})
    result = detect_spec_type(spec)
    assert result["type"] == "openapi"
    assert result["version"] == "3.0.3"


@pytest.mark.unit
def test_detect_swagger_2() -> None:
    from spec_inferer.detector import detect_spec_type

    spec = json.dumps({"swagger": "2.0", "info": {}, "paths": {}})
    result = detect_spec_type(spec)
    assert result["type"] == "swagger"
    assert result["version"] == "2.0"


@pytest.mark.unit
def test_detect_payload_dict() -> None:
    from spec_inferer.detector import detect_spec_type

    payload = json.dumps({"id": 1, "name": "x"})
    result = detect_spec_type(payload)
    assert result["type"] == "payload"
    assert result["version"] is None


@pytest.mark.unit
def test_detect_payload_invalid_json() -> None:
    from spec_inferer.detector import detect_spec_type

    result = detect_spec_type("not valid json or yaml {{{")
    # YAML aceita quase tudo como string; só "payload" se não for dict
    assert result["type"] == "payload"


@pytest.mark.unit
def test_detect_yaml_input() -> None:
    from spec_inferer.detector import detect_spec_type

    yaml_text = "openapi: '3.0.3'\ninfo: {}\npaths: {}\n"
    result = detect_spec_type(yaml_text)
    assert result["type"] == "openapi"
    assert result["version"] == "3.0.3"


@pytest.mark.unit
def test_detect_dict_input_directly() -> None:
    from spec_inferer.detector import detect_spec_type

    result = detect_spec_type({"openapi": "3.1.0"})
    assert result["type"] == "openapi"
    assert result["version"] == "3.1.0"


@pytest.mark.unit
def test_infer_minimal_payload() -> None:
    from spec_inferer.inferer import infer_openapi_from_payload

    result = infer_openapi_from_payload({"id": 1, "name": "x"})
    spec = result["spec"]
    assert spec["openapi"] == "3.0.3"
    assert spec["info"]["title"]
    schema = spec["paths"]["/resources"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["type"] == "object"
    assert schema["properties"]["id"]["type"] == "integer"
    assert schema["properties"]["name"]["type"] == "string"


@pytest.mark.unit
def test_infer_fabricated_fields_listed() -> None:
    from spec_inferer.inferer import infer_openapi_from_payload

    result = infer_openapi_from_payload({"id": 1})
    fab = result["fabricated"]
    assert "info.title" in fab
    assert any("operationId" in f for f in fab)
    assert any("tags" in f for f in fab)
    assert len(fab) >= 5


@pytest.mark.unit
def test_infer_resource_name_override() -> None:
    from spec_inferer.inferer import infer_openapi_from_payload

    result = infer_openapi_from_payload({"id": 1}, resource_name="naturalPerson")
    spec = result["spec"]
    assert "/naturalPersons" in spec["paths"]
    op = spec["paths"]["/naturalPersons"]["post"]
    assert op["operationId"] == "postNaturalPerson"


@pytest.mark.unit
def test_infer_handles_null_fields() -> None:
    """Crítico: payload real (natural_person_response.json) tem dezenas de nulls."""
    from spec_inferer.inferer import infer_openapi_from_payload

    result = infer_openapi_from_payload({"x": None, "y": "ok"})
    schema = result["spec"]["paths"]["/resources"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    # x veio só como null → type:string + nullable:true
    assert schema["properties"]["x"]["nullable"] is True
    assert schema["properties"]["y"]["type"] == "string"


@pytest.mark.unit
def test_infer_payload_array_root() -> None:
    from spec_inferer.inferer import infer_openapi_from_payload

    result = infer_openapi_from_payload([{"a": 1}, {"a": 2}])
    schema = result["spec"]["paths"]["/resources"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["type"] == "array"
    assert schema["items"]["properties"]["a"]["type"] == "integer"


@pytest.mark.unit
def test_inferred_spec_validates_as_openapi_3_0() -> None:
    """Pipeline interno coerente: inferer output é aceito por validate_spec."""
    from spec_inferer.inferer import infer_openapi_from_payload
    from spec_inferer.validator import validate_spec

    payload = {"id": 1, "name": "x", "active": None, "tags": ["a", "b"]}
    inf = infer_openapi_from_payload(payload, resource_name="thing")
    val = validate_spec(inf["spec"])
    assert val["valid"], val["errors"]


@pytest.mark.unit
def test_validate_valid_spec() -> None:
    from spec_inferer.validator import validate_spec

    spec = {
        "openapi": "3.0.3",
        "info": {"title": "t", "version": "0.1.0"},
        "paths": {},
    }
    result = validate_spec(spec)
    assert result["valid"], result["errors"]
    assert result["errors"] == []


@pytest.mark.unit
def test_validate_invalid_spec() -> None:
    from spec_inferer.validator import validate_spec

    # spec sem 'paths' nem 'info' — inválido
    result = validate_spec({"openapi": "3.0.3"})
    assert not result["valid"]
    assert len(result["errors"]) >= 1


@pytest.mark.unit
def test_to_openapi_3_0_schema_handles_mixed_types() -> None:
    """Genson pode emitir type=['string', 'integer'] (sem null) → oneOf."""
    from spec_inferer.inferer import _to_openapi_3_0_schema

    out = _to_openapi_3_0_schema({"type": ["string", "integer"]})
    assert "oneOf" in out
    assert {"type": "string"} in out["oneOf"]
    assert {"type": "integer"} in out["oneOf"]


@pytest.mark.unit
def test_to_openapi_3_0_schema_handles_only_null_array() -> None:
    """Type=['null'] sem outros → nullable sem type explícito."""
    from spec_inferer.inferer import _to_openapi_3_0_schema

    out = _to_openapi_3_0_schema({"type": ["null"]})
    assert out.get("nullable") is True
    assert "type" not in out


@pytest.mark.unit
def test_to_openapi_3_0_schema_passthrough_non_dict() -> None:
    from spec_inferer.inferer import _to_openapi_3_0_schema

    assert _to_openapi_3_0_schema("string-leaf") == "string-leaf"
    assert _to_openapi_3_0_schema(42) == 42


@pytest.mark.unit
def test_detect_yaml_error_is_payload() -> None:
    """Texto que falha YAML também → payload (cobre except YAMLError)."""
    from spec_inferer.detector import detect_spec_type

    # texto com aspas desbalanceadas — falha JSON e YAML
    result = detect_spec_type('{"a": "b\n"unterminated')
    assert result["type"] == "payload"
