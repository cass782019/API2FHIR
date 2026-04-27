from __future__ import annotations

import httpx
import structlog

from .models import Coding, ConceptMatch

log = structlog.get_logger(__name__)

# Canonical FHIR system URIs
_SNOMED_SYSTEM = "http://snomed.info/sct"
_FHIR_BASE_SUFFIX = "/fhir"


class SnowstormClient:
    """Client for the Snowstorm SNOMED CT terminology server."""

    def __init__(self, base_url: str, branch: str = "MAIN") -> None:
        self._base_url = base_url.rstrip("/")
        self._fhir_base = self._base_url + _FHIR_BASE_SUFFIX
        self._branch = branch

    async def find_concept(
        self,
        term: str,
        ecl: str | None = None,
    ) -> list[ConceptMatch]:
        """Search for SNOMED concepts matching *term*, optionally filtered by ECL expression."""
        params: dict[str, str] = {"term": term, "activeFilter": "true", "limit": "10"}
        if ecl:
            params["ecl"] = ecl

        url = f"{self._base_url}/browser/{self._branch}/concepts"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            log.warning("snowstorm_find_concept_error", term=term, status=exc.response.status_code)
            return []
        except httpx.RequestError as exc:
            log.warning("snowstorm_request_error", term=term, error=str(exc))
            return []

        results: list[ConceptMatch] = []
        for item in data.get("items", []):
            concept_id = item.get("conceptId", "")
            pt = item.get("fsn", {}).get("term", "") or item.get("pt", {}).get("term", "")
            if concept_id:
                results.append(
                    ConceptMatch(
                        coding=Coding(system=_SNOMED_SYSTEM, code=concept_id, display=pt),
                        score=1.0,
                        source="snowstorm",
                        matched_terms=[pt],
                    )
                )
        return results

    async def translate(
        self,
        system: str,
        code: str,
        target_system: str,
    ) -> Coding | None:
        """Translate a code from *system* to *target_system* via ConceptMap/$translate."""
        url = f"{self._fhir_base}/ConceptMap/$translate"
        params = {"system": system, "code": code, "targetSystem": target_system}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params)
            resp.raise_for_status()
            outcome = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            log.warning("snowstorm_translate_error", system=system, code=code, status=exc.response.status_code)
            return None
        except httpx.RequestError as exc:
            log.warning("snowstorm_translate_request_error", system=system, code=code, error=str(exc))
            return None

        # Parse Parameters resource
        for param in outcome.get("parameter", []):
            if param.get("name") == "match":
                for part in param.get("part", []):
                    if part.get("name") == "concept":
                        concept = part.get("valueCoding", {})
                        return Coding(
                            system=concept.get("system", target_system),
                            code=concept.get("code", ""),
                            display=concept.get("display", ""),
                        )
        return None
