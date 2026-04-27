"""Snowstorm SNOMED CT tools for the MCP server.

Two tools: find_concept, translate_code.
Uses the Snowstorm FHIR API at /fhir.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..settings import settings

_SNOWSTORM_FHIR = f"{settings.snowstorm_base_url}/fhir"
_SNOMED_SYSTEM = "http://snomed.info/sct"


async def find_concept(
    term: str,
    ecl_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Search for SNOMED CT concepts by term or ECL expression.

    Args:
        term: Free-text search term, e.g. 'diabetes mellitus tipo 2'.
        ecl_filter: Optional ECL expression to restrict results,
            e.g. '<< 73211009 |Diabetes mellitus|'.

    Returns:
        List of concept dicts with keys: system, code, display, active.
        Returns empty list if Snowstorm is unavailable or SNOMED not loaded.
    """
    try:
        async with httpx.AsyncClient(timeout=settings.snowstorm_timeout) as client:
            response = await client.get(
                f"{settings.snowstorm_base_url}/browser/MAIN/concepts",
                params={"term": term, "ecl": ecl_filter or "", "limit": 20},
            )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json()
    except httpx.ConnectError:
        return [{"error": "snowstorm_unavailable", "hint": "Is Snowstorm running? make up"}]

    items = data.get("items", []) if isinstance(data, dict) else []
    return [
        {
            "system": _SNOMED_SYSTEM,
            "code": item.get("conceptId", ""),
            "display": item.get("fsn", {}).get("term", item.get("pt", {}).get("term", "")),
            "active": item.get("active", True),
        }
        for item in items
    ]


async def translate_code(
    source_system: str,
    source_code: str,
    target_system: str,
) -> dict[str, Any] | None:
    """Translate a code from one system to another using HAPI ConceptMap $translate.

    Uses the HAPI FHIR endpoint (not Snowstorm) because ConceptMaps are stored there.

    Args:
        source_system: Source code system URI, e.g. 'http://www.datasus.gov.br/cid10'.
        source_code: The code to translate, e.g. 'E11'.
        target_system: Target code system URI, e.g. 'http://snomed.info/sct'.

    Returns:
        Coding dict with system, code, display — or None if no mapping found.
    """
    from ..settings import settings as root_settings

    url = f"{root_settings.hapi_base_url}/ConceptMap/$translate"
    params = {
        "system": source_system,
        "code": source_code,
        "targetsystem": target_system,
    }

    async with httpx.AsyncClient(timeout=settings.hapi_timeout) as client:
        response = await client.get(url, params=params)

    if response.status_code == 404:
        return None

    response.raise_for_status()
    outcome = response.json()

    for param in outcome.get("parameter", []):
        if param.get("name") == "match":
            for part in param.get("part", []):
                if part.get("name") == "concept":
                    coding = part.get("valueCoding", {})
                    return {
                        "system": coding.get("system", target_system),
                        "code": coding.get("code", ""),
                        "display": coding.get("display", ""),
                    }

    return None
