from __future__ import annotations

import pytest


@pytest.mark.unit
def test_flatten_simple_inline_schema() -> None:
    from swagger_lens.flattener import flatten_schema

    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    result = flatten_schema(schema, {})
    assert result["type"] == "object"
    assert result["properties"]["name"] == {"type": "string"}


@pytest.mark.unit
def test_flatten_simple_ref() -> None:
    from swagger_lens.flattener import flatten_schema

    spec = {
        "components": {
            "schemas": {
                "Name": {"type": "string", "maxLength": 100},
            }
        }
    }
    schema = {"$ref": "#/components/schemas/Name"}
    result = flatten_schema(schema, spec)
    assert result["type"] == "string"
    assert result["maxLength"] == 100


@pytest.mark.unit
def test_flatten_nested_ref() -> None:
    from swagger_lens.flattener import flatten_schema

    spec = {
        "components": {
            "schemas": {
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                    },
                },
                "Patient": {
                    "type": "object",
                    "properties": {
                        "address": {"$ref": "#/components/schemas/Address"},
                    },
                },
            }
        }
    }
    schema = {"$ref": "#/components/schemas/Patient"}
    result = flatten_schema(schema, spec)
    assert result["properties"]["address"]["type"] == "object"
    assert "street" in result["properties"]["address"]["properties"]


@pytest.mark.unit
def test_flatten_circular_ref_does_not_loop() -> None:
    from swagger_lens.flattener import flatten_schema

    spec = {
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "child": {"$ref": "#/components/schemas/Node"},
                    },
                }
            }
        }
    }
    schema = {"$ref": "#/components/schemas/Node"}
    result = flatten_schema(schema, spec)
    # Must return without stack overflow; circular ref marked
    assert result["type"] == "object"
    assert result["properties"]["child"] == {"$circular": "#/components/schemas/Node"}


@pytest.mark.unit
def test_flatten_allof_merges_properties() -> None:
    from swagger_lens.flattener import flatten_schema

    spec = {
        "components": {
            "schemas": {
                "Base": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                }
            }
        }
    }
    schema = {
        "allOf": [
            {"$ref": "#/components/schemas/Base"},
            {"type": "object", "properties": {"name": {"type": "string"}}},
        ]
    }
    result = flatten_schema(schema, spec)
    assert "id" in result["properties"]
    assert "name" in result["properties"]


@pytest.mark.unit
def test_flatten_oneof_merges_subschemas() -> None:
    from swagger_lens.flattener import flatten_schema

    schema = {
        "oneOf": [
            {"type": "object", "properties": {"a": {"type": "string"}}},
            {"type": "object", "properties": {"b": {"type": "integer"}}},
        ]
    }
    result = flatten_schema(schema, {})
    assert "a" in result["properties"]
    assert "b" in result["properties"]


@pytest.mark.unit
def test_flatten_anyof_merges_subschemas() -> None:
    from swagger_lens.flattener import flatten_schema

    schema = {
        "anyOf": [
            {"properties": {"x": {"type": "number"}}},
            {"properties": {"y": {"type": "boolean"}}},
        ]
    }
    result = flatten_schema(schema, {})
    assert "x" in result.get("properties", {})
    assert "y" in result.get("properties", {})


@pytest.mark.unit
def test_flatten_allof_with_discriminator() -> None:
    from swagger_lens.flattener import flatten_schema

    schema = {
        "allOf": [
            {"type": "object", "properties": {"resourceType": {"type": "string"}}},
            {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "discriminator": {"propertyName": "resourceType"},
            },
        ]
    }
    result = flatten_schema(schema, {})
    assert "resourceType" in result["properties"]
    assert "id" in result["properties"]


@pytest.mark.unit
def test_flatten_unresolvable_ref_returns_marker() -> None:
    from swagger_lens.flattener import flatten_schema

    schema = {"$ref": "#/components/schemas/DoesNotExist"}
    result = flatten_schema(schema, {})
    assert "$unresolved" in result


@pytest.mark.unit
def test_flatten_items_resolved() -> None:
    from swagger_lens.flattener import flatten_schema

    spec = {
        "components": {
            "schemas": {
                "Item": {"type": "string"},
            }
        }
    }
    schema = {"type": "array", "items": {"$ref": "#/components/schemas/Item"}}
    result = flatten_schema(schema, spec)
    assert result["items"]["type"] == "string"


@pytest.mark.unit
def test_flatten_external_ref_returns_unresolved() -> None:
    from swagger_lens.flattener import flatten_schema

    schema = {"$ref": "https://example.com/schemas/Patient.json"}
    result = flatten_schema(schema, {})
    assert "$unresolved" in result
