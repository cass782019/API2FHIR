from __future__ import annotations

from typing import Any


def flatten_schema(schema: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Resolve all $ref, allOf, oneOf, anyOf in *schema* using *spec* as the root document.

    Circular references are detected via a frozenset of visited ref paths and
    replaced with {"$circular": "<ref>"} to avoid infinite recursion.
    """
    return _flatten(schema, spec, frozenset())


def _flatten(
    schema: dict[str, Any],
    spec: dict[str, Any],
    visited: frozenset[str],
) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return schema

    # --- resolve $ref first ---
    if "$ref" in schema:
        ref: str = schema["$ref"]
        if ref in visited:
            return {"$circular": ref}
        resolved = _resolve_ref(ref, spec)
        if resolved is None:
            return {"$unresolved": ref}
        return _flatten(resolved, spec, visited | {ref})

    result: dict[str, Any] = {}

    # --- expand combining keywords ---
    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword in schema:
            merged = _merge_subschemas(schema[keyword], spec, visited)
            result.update(merged)

    # --- copy remaining keys (excluding combining keywords already handled) ---
    skip = {"allOf", "anyOf", "oneOf", "$ref"}
    for key, value in schema.items():
        if key in skip:
            continue
        if key == "properties" and isinstance(value, dict):
            result["properties"] = {
                prop: _flatten(prop_schema, spec, visited)
                for prop, prop_schema in value.items()
            }
        elif key in ("items", "additionalProperties") and isinstance(value, dict):
            result[key] = _flatten(value, spec, visited)
        else:
            result[key] = value

    return result


def _merge_subschemas(
    subschemas: list[Any],
    spec: dict[str, Any],
    visited: frozenset[str],
) -> dict[str, Any]:
    """Shallow-merge a list of subschemas (allOf semantics)."""
    merged: dict[str, Any] = {}
    for sub in subschemas:
        if not isinstance(sub, dict):
            continue
        flattened = _flatten(sub, spec, visited)
        if "properties" in flattened:
            existing = merged.setdefault("properties", {})
            existing.update(flattened.pop("properties"))
        merged.update(flattened)
    return merged


def _resolve_ref(ref: str, spec: dict[str, Any]) -> dict[str, Any] | None:
    """Walk JSON Pointer path in *spec* and return the referenced schema."""
    if not ref.startswith("#/"):
        return None  # external refs not supported
    parts = ref[2:].split("/")
    node: Any = spec
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    if not isinstance(node, dict):
        return None
    return node
