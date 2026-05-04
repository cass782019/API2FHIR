from __future__ import annotations

import json
from typing import Any, Literal

import yaml
from openapi_spec_validator import (
    OpenAPIV2SpecValidator,
    OpenAPIV30SpecValidator,
    OpenAPIV31SpecValidator,
)
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError

from .exceptions import SpecParseError
from .models import Endpoint, Parameter, SwaggerSpec


def parse_spec(
    content: str | bytes,
    fmt: Literal["yaml", "json", "auto"] = "auto",
) -> SwaggerSpec:
    """Parse an OpenAPI 2.0/3.x spec (YAML or JSON) into a typed SwaggerSpec.

    Validates against the official schema before parsing.
    Raises SpecParseError if the content is invalid.
    """
    raw = _load_raw(content, fmt)
    _validate(raw)
    return _build_spec(raw)


def _load_raw(content: str | bytes, fmt: Literal["yaml", "json", "auto"]) -> dict[str, Any]:
    text = content.decode() if isinstance(content, bytes) else content
    if fmt == "json":
        try:
            return json.loads(text)  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            raise SpecParseError(f"Invalid JSON: {exc}") from exc
    if fmt == "yaml":
        try:
            return yaml.safe_load(text)  # type: ignore[no-any-return]
        except yaml.YAMLError as exc:
            raise SpecParseError(f"Invalid YAML: {exc}") from exc
    # auto: try JSON first, then YAML
    try:
        return json.loads(text)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        return yaml.safe_load(text)  # type: ignore[no-any-return]
    except yaml.YAMLError as exc:
        raise SpecParseError(f"Content is neither valid JSON nor YAML: {exc}") from exc


def _validate(raw: dict[str, Any]) -> None:
    if not isinstance(raw, dict):
        raise SpecParseError("Spec must be a JSON object / YAML mapping")

    oas_version: str = str(raw.get("openapi") or raw.get("swagger") or "")
    if not oas_version:
        raise SpecParseError("Missing 'openapi' or 'swagger' version field")

    try:
        if oas_version.startswith("2"):
            OpenAPIV2SpecValidator(raw).validate()
        elif oas_version.startswith("3.1"):
            OpenAPIV31SpecValidator(raw).validate()
        else:
            OpenAPIV30SpecValidator(raw).validate()
    except OpenAPIValidationError as exc:
        raise SpecParseError(f"OpenAPI validation failed: {exc.message}") from exc


def _build_spec(raw: dict[str, Any]) -> SwaggerSpec:
    oas_version: str = raw.get("openapi", raw.get("swagger", "unknown"))
    info: dict[str, Any] = raw.get("info", {})
    title: str = info.get("title", "")
    version: str = info.get("version", "")

    base_url = _oas2_base_url(raw) if oas_version.startswith("2") else _oas3_base_url(raw)

    endpoints = _extract_endpoints(raw, oas_version)

    return SwaggerSpec(
        title=title,
        version=version,
        base_url=base_url,
        openapi_version=oas_version,
        endpoints=endpoints,
        raw=raw,
    )


def _oas2_base_url(raw: dict[str, Any]) -> str:
    host = raw.get("host", "localhost")
    base_path = raw.get("basePath", "/")
    schemes = raw.get("schemes", ["https"])
    scheme = schemes[0] if schemes else "https"
    return f"{scheme}://{host}{base_path}"


def _oas3_base_url(raw: dict[str, Any]) -> str:
    servers: list[dict[str, Any]] = raw.get("servers", [])
    if servers:
        return str(servers[0].get("url", "/"))
    return "/"


def _extract_endpoints(raw: dict[str, Any], oas_version: str) -> list[Endpoint]:
    paths: dict[str, Any] = raw.get("paths", {})
    endpoints: list[Endpoint] = []
    http_methods = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        path_level_params: list[dict[str, Any]] = path_item.get("parameters", [])

        for method, operation in path_item.items():
            if method not in http_methods:
                continue
            if not isinstance(operation, dict):
                continue

            op_params = _merge_params(path_level_params, operation.get("parameters", []))
            params = _parse_params(op_params)

            if oas_version.startswith("2"):
                request_body = _oas2_request_body(op_params)
            else:
                request_body = operation.get("requestBody")

            endpoints.append(
                Endpoint(
                    path=path,
                    method=method.upper(),
                    operation_id=operation.get("operationId", f"{method}_{path}"),
                    summary=operation.get("summary", ""),
                    description=operation.get("description", ""),
                    tags=operation.get("tags", []),
                    params=params,
                    request_body=request_body,
                    responses=operation.get("responses", {}),
                )
            )

    return endpoints


def _merge_params(
    path_params: list[dict[str, Any]],
    op_params: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Operation-level params override path-level by (name, in) key."""
    merged: dict[tuple[str, str], dict[str, Any]] = {
        (p["name"], p["in"]): p for p in path_params if isinstance(p, dict)
    }
    for p in op_params:
        if isinstance(p, dict):
            merged[(p["name"], p["in"])] = p
    return list(merged.values())


def _parse_params(raw_params: list[dict[str, Any]]) -> list[Parameter]:
    result: list[Parameter] = []
    for p in raw_params:
        loc = p.get("in", "")
        if loc == "body":
            continue  # OAS2 body param → handled by _oas2_request_body
        schema = p.get("schema", {})
        if not schema:
            # OAS2 inline type
            schema = {k: v for k, v in p.items() if k in ("type", "format", "enum", "items")}
        result.append(
            Parameter(
                name=p.get("name", ""),
                location=loc,
                required=p.get("required", False),
                schema=schema,
                description=p.get("description", ""),
            )
        )
    return result


def _oas2_request_body(params: list[dict[str, Any]]) -> dict[str, Any] | None:
    for p in params:
        if isinstance(p, dict) and p.get("in") == "body":
            return {"schema": p.get("schema", {}), "description": p.get("description", "")}
    return None
