"""HAPI FHIR tools for the MCP server.

Four tools: validate_resource, get_resource, search_resources, expand_valueset.
All use httpx.AsyncClient against the configured HAPI base URL.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from core.settings import settings as core_settings

from ..settings import settings as mcp_settings


async def validate_resource(
    resource_json: str,
    profile_url: str | None = None,
) -> dict[str, Any]:
    """Validate a FHIR resource against BR Core using HAPI $validate.

    Args:
        resource_json: The FHIR resource as a JSON string.
        profile_url: Optional BR Core profile URL to validate against,
            e.g. 'http://hl7.org.br/fhir/r4/core/StructureDefinition/BRCorePatient'.
            If omitted, validates against base FHIR R4 only.

    Returns:
        dict with keys:
            - valid (bool): True if no errors in OperationOutcome
            - issues (list[dict]): Each issue has severity, code, details
    """
    resource = json.loads(resource_json)
    resource_type = resource.get("resourceType", "Resource")
    url = f"{core_settings.hapi_base_url}/{resource_type}/$validate"
    params = {"profile": profile_url} if profile_url else {}

    async with httpx.AsyncClient(timeout=mcp_settings.hapi_timeout) as client:
        response = await client.post(url, json=resource, params=params)
        outcome = response.json()

    issues = outcome.get("issue", [])
    has_errors = any(i.get("severity") in ("error", "fatal") for i in issues)

    return {
        "valid": not has_errors,
        "issues": [
            {
                "severity": i.get("severity"),
                "code": i.get("code"),
                "details": i.get("details", {}).get("text", ""),
                "location": i.get("location", []),
            }
            for i in issues
        ],
    }


async def get_resource(resource_type: str, resource_id: str) -> dict[str, Any]:
    """Fetch a FHIR resource by type and ID from HAPI.

    Args:
        resource_type: FHIR resource type, e.g. 'Patient', 'Observation'.
        resource_id: The logical ID of the resource.

    Returns:
        The FHIR resource as a dict, or {"error": "not_found"} if 404.
    """
    url = f"{core_settings.hapi_base_url}/{resource_type}/{resource_id}"

    async with httpx.AsyncClient(timeout=mcp_settings.hapi_timeout) as client:
        response = await client.get(url)

    if response.status_code == 404:
        return {"error": "not_found", "resource_type": resource_type, "id": resource_id}

    response.raise_for_status()
    return response.json()  # type: ignore[no-any-return]


async def search_resources(resource_type: str, params: str) -> dict[str, Any]:
    """Search for FHIR resources of a given type.

    Args:
        resource_type: FHIR resource type, e.g. 'Patient', 'Condition'.
        params: Query string parameters, e.g. 'name=João&birthdate=1980-01-01'.
            Use standard FHIR search parameters.

    Returns:
        dict with keys:
            - results (list[dict]): Matching FHIR resource dicts (up to 200).
            - truncated (bool): True if more than 200 results exist.
            - total (int): Total number of results fetched before truncation.
            - returned (int): Number of results in this response.
    """
    url = f"{core_settings.hapi_base_url}/{resource_type}"
    query = dict(pair.split("=", 1) for pair in params.split("&") if "=" in pair)
    query["_count"] = "50"

    all_results: list[dict[str, Any]] = []
    next_url: str | None = url

    async with httpx.AsyncClient(timeout=mcp_settings.hapi_timeout) as client:
        while next_url and len(all_results) < 200:
            if next_url == url:
                response = await client.get(next_url, params=query)
            else:
                response = await client.get(next_url)
            response.raise_for_status()
            bundle = response.json()

            for entry in bundle.get("entry", []):
                all_results.append(entry.get("resource", {}))

            next_url = next(
                (
                    link["url"]
                    for link in bundle.get("link", [])
                    if link.get("relation") == "next"
                ),
                None,
            )

    truncated = next_url is not None  # still a next page after hitting 200 limit
    returned = all_results[:200]
    return {
        "results": returned,
        "truncated": truncated,
        "total": len(all_results),
        "returned": len(returned),
    }


async def expand_valueset(valueset_url: str, filter: str | None = None) -> list[dict[str, Any]]:
    """Expand a ValueSet using HAPI $expand.

    Args:
        valueset_url: Canonical URL of the ValueSet,
            e.g. 'http://hl7.org.br/fhir/r4/core/ValueSet/BRRacaCor'.
        filter: Optional text filter to narrow results.

    Returns:
        List of Coding dicts with keys: system, code, display.
    """
    url = f"{core_settings.hapi_base_url}/ValueSet/$expand"
    params: dict[str, str] = {"url": valueset_url, "count": "500"}
    if filter:
        params["filter"] = filter

    async with httpx.AsyncClient(timeout=mcp_settings.hapi_timeout) as client:
        response = await client.get(url, params=params)
    response.raise_for_status()

    expansion = response.json().get("expansion", {})
    return [
        {
            "system": c.get("system", ""),
            "code": c.get("code", ""),
            "display": c.get("display", ""),
        }
        for c in expansion.get("contains", [])
    ]
